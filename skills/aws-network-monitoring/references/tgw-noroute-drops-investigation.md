# Investigating TGW PacketDropCountNoRoute — debugging playbook

When CloudWatch shows `PacketDropCountNoRoute > 0` on a Transit Gateway, this is the systematic walk to find the root cause. Tested against the corp `tgw-banking-hub` incident (8038 drops in 1h, 22:57Z, 7-may-2026).

## Step 0 — Separate Blackhole vs NoRoute first

```bash
aws cloudwatch get-metric-statistics --namespace AWS/TransitGateway \
  --metric-name PacketDropCountBlackhole --dimensions Name=TransitGateway,Value=<tgw-id> \
  --period 3600 --statistics Sum --start-time ... --end-time ...

aws cloudwatch get-metric-statistics --namespace AWS/TransitGateway \
  --metric-name PacketDropCountNoRoute --dimensions Name=TransitGateway,Value=<tgw-id> \
  --period 3600 --statistics Sum --start-time ... --end-time ...
```

- **Blackhole > 0** = there IS a route, but the route's target is a blackhole (intentional drop). Look for `state=blackhole` routes in the RTs.
- **NoRoute > 0** = no matching route in the RT consulted at the moment of forwarding. This playbook covers NoRoute.

Also pull `BytesDropCountNoRoute` to compute average packet size:
- ~64 bytes → TCP SYN/SYN-ACK/RST or empty ACK → connection-establishment failures (the smoking gun for "service tries to connect to host across segments")
- ~1500 bytes → MTU-sized → real bulk traffic that started flowing then died
- Variable → mixed flows

## Step 1 — Pull TGW topology (attachments + route tables)

```bash
TGW=tgw-xxxxxxxxxxxxxxxxx
PROFILE=...
REGION=...

# 1a. TGW config (ASN, default-association/propagation flags)
aws --profile $PROFILE --region $REGION ec2 describe-transit-gateways \
  --transit-gateway-ids $TGW --output json

# 1b. All attachments grouped by type
aws --profile $PROFILE --region $REGION ec2 describe-transit-gateway-attachments \
  --filters Name=transit-gateway-id,Values=$TGW --output json

# 1c. All route tables
aws --profile $PROFILE --region $REGION ec2 describe-transit-gateway-route-tables \
  --filters Name=transit-gateway-id,Values=$TGW --output json
```

Naming heuristic at corp: RTs prefixed `rt-tgw-X-to-fgt` are **ingress** (peering→FW), prefixed `rt-fgt-to-tgw-X` are **egress** (FW→destination). If you see this naming, the TGW is an east-west firewall-inspection hub (Connect attachments to FortiGate/PAN/etc.) — drops are usually in the EGRESS RTs.

## Step 2 — For each RT, dump (associations, propagations, ALL routes)

```bash
for RT in $(aws ... describe-transit-gateway-route-tables ... --query 'TransitGatewayRouteTables[].TransitGatewayRouteTableId' -o text); do
  # Who associates → this RT (i.e. who consults it for forwarding decisions)
  aws ... ec2 get-transit-gateway-route-table-associations --transit-gateway-route-table-id $RT
  # Who propagates routes INTO this RT (dynamic via attachment)
  aws ... ec2 get-transit-gateway-route-table-propagations --transit-gateway-route-table-id $RT
  # All static + propagated routes
  aws ... ec2 search-transit-gateway-routes \
    --transit-gateway-route-table-id $RT \
    --filters Name=type,Values=static,propagated --max-results 100
done
```

**Important:** `search-transit-gateway-routes` returns max 100 routes per call — paginate via `--filters` if hitting the limit. Default `--filters Name=state,Values=active` excludes blackhole and pending — pass `Name=type,Values=static,propagated` to see everything.

## Step 3 — Build the source-→-destination matrix

This is the heart of the playbook for east-west FW-inspection topology.

For each peering attachment (or any "ingress" point), trace:
  1. Which RT it associates to (call it `RT_in_X`)
  2. What `RT_in_X` says — usually `0.0.0.0/0 → connect-attach-to-FW-X`
  3. Which RT does FW-X's connect attachment associate to (call it `RT_out_X`)
  4. List the destination CIDRs in `RT_out_X` — these are the ONLY destinations reachable from origin X after FW inspection

Then build the matrix: rows = ingress points, columns = egress destinations, cells = "is there a covering route in `RT_out_X` for this destination's CIDRs?"

Cells with **no covering route** are the buckets where NoRoute drops will land.

Pseudocode (adapt to actual RTs):
```python
ingress_points = {'Production', 'Homolog', 'GSN', 'RSFN'}
destinations = {'Production': [...cidrs...], 'Homolog': [...], ...}
rt_out_by_origin = {'Production': 'rt-fgt-to-tgw-production', ...}

for src in ingress_points:
    rt = rt_out_by_origin[src]
    routes_in_rt = search_transit_gateway_routes(rt)
    for dst, dst_cidrs in destinations.items():
        if src == dst: continue
        covered = any(cidr_covered_by(c, routes_in_rt) for c in dst_cidrs)
        print(src, '→', dst, '✅' if covered else '❌ DROP')
```

## Step 4 — Validate Flow Logs are actually flowing

This was the trap on `tgw-banking-hub`: the flow log was `FlowLogStatus=ACTIVE` but `DeliverLogsStatus=FAILED` with destination pointing to a wrong log group (an ECS Container Insights one). Flow logs were never being delivered.

```bash
aws ... ec2 describe-flow-logs --filter Name=resource-id,Values=$TGW --output json
```

Check **all** these fields:
- `FlowLogStatus` — must be `ACTIVE` (not `INACTIVE` or `FAILED-CREATING`)
- `DeliverLogsStatus` — must be `SUCCESS` (NOT `FAILED`)
- `DeliverLogsErrorMessage` — must be empty/null
- `LogGroupName` — must match a `/aws/vpcflowlogs/...` or `/aws/transitgateway/...` log group THAT EXISTS and has recent log streams

Verify destination has recent data:
```bash
aws ... logs describe-log-streams --log-group-name "<LogGroupName>" \
  --order-by LastEventTime --descending --limit 3
# Last event timestamp should be within minutes
```

Once Flow Log is healthy, query the drops via CloudWatch Logs Insights:
```
fields @timestamp, srcaddr, dstaddr, srcport, dstport, protocol, `tcp-flags`,
       `tgw-src-vpc-id`, `tgw-dst-vpc-id`, `packets-lost-no-route`
| filter `packets-lost-no-route` > 0
| stats sum(`packets-lost-no-route`) as drops by srcaddr, dstaddr, dstport, protocol
| sort drops desc
| limit 50
```

Make sure the log format string includes `${packets-lost-no-route}`, `${packets-lost-blackhole}`, etc. — those are NOT in the default v2 format.

## Step 5 — Check Connect (BGP) peer health while you're there

When the TGW uses Connect attachments to a FW, dump all BGP peers:
```bash
for ATT in <list-of-connect-attachment-ids>; do
  aws ... ec2 describe-transit-gateway-connect-peers \
    --filters Name=transit-gateway-attachment-id,Values=$ATT \
    --query 'TransitGatewayConnectPeers[*].{id:TransitGatewayConnectPeerId,state:State,bgp:ConnectPeerConfiguration.BgpConfigurations[*].{peer:PeerAddress,asn:PeerAsn,status:BgpStatus}}'
done
```

For each Connect attachment AWS provisions **2 BGP peers** (one per AZ — that's the HA). On corp's `tgw-banking-hub` we found that in all 3 Connect attachments, ONE peer was UP and the OTHER was DOWN. That breaks HA: a failure of the active FortiGate node will not failover. Flag this finding even when it's not the immediate drop cause.

## Step 6 — Common root-cause patterns for NoRoute

| Pattern | Tell-tale | Fix |
|---|---|---|
| **East-west FW gap** | Many RTs, naming `rt-fgt-to-X`, drops on tiny packets, isolated peaks | Add destination CIDRs to RT_out_X for the new flow |
| **CIDR overlap surprise** | Two routes for partially-overlapping CIDRs (e.g. 10.8.64.0/18 → A and 10.8.64.0/19 → B); longest-prefix wins so /19 traffic goes to B unexpectedly | Resplit the prefixes or pick one target |
| **Recently added VPC attachment** | Drops start at attachment creation time | The new VPC's CIDRs aren't yet in the egress RTs of all peering points that talk to it |
| **Route propagation broken** | `propagations` show `enabled` but `search-transit-gateway-routes` shows fewer routes | Disable+re-enable the propagation; sometimes need to detach+reattach |
| **Misnamed default RT** | TGW has `DefaultRouteTableAssociation=enable` and a new attachment landed in the default RT instead of the segregated one | Re-associate the attachment to the correct RT |
| **AWS RAM share missing** | The TGW is shared via RAM but the consumer account's attachment didn't propagate routes back | Verify RAM resource share + permission model |

## Time-of-day clue

If the drop spike is concentrated in a **single hour** with thousands of packets averaging ~64 bytes, it's almost always an application/service that **started a connection attempt** (TCP SYN with retries) toward an unreachable destination. Cross-reference with deployment events / k8s rollouts at that timestamp.

If the drop is **constant low rate** (e.g. 5-10/min always), it's usually broadcast/discovery noise (mDNS, NBT, etc.) or a misconfigured monitoring agent.

## What to deliver to the user after the investigation

1. The drop pattern (single spike vs constant) and packet-size signature
2. The matrix of routable origin→destination pairs and the gaps
3. BGP Connect peer health (HA status)
4. Flow Log health and a query they can run to identify exact src/dst once logs flow
5. Recommended action ordering (ALWAYS fix Flow Logs first if broken — without them subsequent investigations are blind)

## corp-specific findings (May 2026 — keep for reference)

- `tgw-banking-hub` (`tgw-078adb7b420592823` in account 783816934837 / us-east-1):
  - 7 RTs in classic east-west pattern: `rt-tgw-{production,gsn,homolog}-to-fgt` (ingress) + `rt-fgt-to-tgw-{production,gsn,homolog}` (egress) + `rt-vpc-network-hub-gsn`
  - 4 peerings: Production (917431122166), GSN-corp (823512721299), RSFN-SA (651684790312), Homolog (287122279835)
  - 3 FortiGate clusters via Connect attachments — every cluster has 1 of 2 BGP peers DOWN
  - Flow log `fl-032822e0742dec4d5` is broken (delivers to ECS log group, not VPC flow log group)
  - Egress RT gaps: Homolog→{Prod,RSFN,GSN,Hub}, Production→{Homolog,Hub}, GSN→{Prod,Homolog,RSFN}
- Similar east-west pattern likely repeats in `tgw-payments-firewall-prd` (3504 drops/24h) and `rsfn-useast1-production-transit-gateway` (53691 drops/24h) — when investigating those, run this same playbook.
