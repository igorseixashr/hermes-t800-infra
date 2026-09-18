---
name: azure-network-monitoring
description: "Monitor Azure ExpressRoute circuits and Virtual Network Gateways health/utilization across subscriptions via az CLI + Resource Graph + Azure Monitor."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Azure, Networking, ExpressRoute, VNG, VPN, Monitoring, BGP, corp]
    related_skills: [native-mcp]
---

# Azure Network Monitoring — ExpressRoute & VNG Health

Operational playbook to inventory and monitor ExpressRoute circuits and Virtual Network Gateways across **all** Azure subscriptions in the tenant. Uses Azure CLI + Resource Graph (cross-subscription) + Azure Monitor metrics.

## When to use this skill

Whenever the user asks about:
- ExpressRoute capacity / occupation / bandwidth utilization
- VNG (VPN or ExpressRoute Gateway) health
- BGP peering status
- Tunnel drops / packet drops
- Cross-subscription network inventory in Azure
- "Quanto está sendo usado do meu link?", "Algum VNG com problema?"

## Prerequisites

- `az` CLI installed (Rocky 9 / RHEL 9: install via `dnf` from `packages-microsoft-prod`)
- Authenticated: `az login --use-device-code` (for headless terminals — captures device code from log file)
- Resource Graph extension: `az extension add --name resource-graph --only-show-errors`
- Azure MCP Server registered in Hermes (`azure_mcp` in `~/.hermes/config.yaml`) — optional, the playbook works with raw `az` too

## corp-specific defaults

- **Subscription with ALL ExpressRoute circuits:** `network-transit-PROD` (id `38263051-7203-454f-acc6-277d3d283b0a`, tenant Linx SA)
- **All circuits live in RG:** `rg_network_connections`
- **All circuits via:** Megaport MCR (Premium_MeteredData SKU)
- **Tenants:** Linx SA + corp PAGAMENTOS S.A.
- Pin default with: `az account set --subscription 38263051-7203-454f-acc6-277d3d283b0a`

## Step 1 — Cross-subscription inventory (Resource Graph)

```bash
# All ExpressRoute circuits in the tenant
az graph query -q "Resources
  | where type =~ 'Microsoft.Network/expressRouteCircuits'
  | project name, subscriptionId, resourceGroup, location,
            sku=tostring(sku.name),
            bandwidth=toint(properties.serviceProviderProperties.bandwidthInMbps),
            provider=tostring(properties.serviceProviderProperties.serviceProviderName),
            peeringLocation=tostring(properties.serviceProviderProperties.peeringLocation),
            provisioningState=tostring(properties.provisioningState),
            spState=tostring(properties.serviceProviderProvisioningState)
  | order by subscriptionId, name" --first 1000 -o json

# All Virtual Network Gateways (VPN + ExpressRoute Gateways)
az graph query -q "Resources
  | where type =~ 'Microsoft.Network/virtualNetworkGateways'
  | project id, name, subscriptionId, resourceGroup, location,
            gwType=tostring(properties.gatewayType),
            sku=tostring(properties.sku.name),
            vpnType=tostring(properties.vpnType),
            enableBgp=tobool(properties.enableBgp),
            activeActive=tobool(properties.activeActive),
            provisioningState=tostring(properties.provisioningState)" --first 1000 -o json
```

**IMPORTANT:** ExpressRoute bandwidth lives in `serviceProviderProperties.bandwidthInMbps` (NOT in `properties.bandwidthInMbps`, which is null for MCR/provider-managed circuits).

## Step 2 — ExpressRoute key metrics

Available metrics on `Microsoft.Network/expressRouteCircuits`:

| Metric | Unit | What it tells you |
|---|---|---|
| `BitsInPerSecond` | bps | Inbound traffic (Azure → on-prem perspective) |
| `BitsOutPerSecond` | bps | Outbound traffic |
| `IngressBandwidthUtilization` | % | Inbound % (Premium tier only, recent) |
| `EgressBandwidthUtilization` | % | Outbound % (Premium tier only, recent) |
| `BgpAvailability` | % | BGP session availability — alert if <99.9% |
| `ArpAvailability` | % | ARP availability — alert if <99.9% |
| `QosDropBitsInPerSecond` | bps | Drops inbound — should be 0 |
| `QosDropBitsOutPerSecond` | bps | Drops outbound — should be 0 |
| `GlobalReachBitsInPerSecond` | bps | Only when Global Reach is enabled |
| `FastPathRoutesCountForCircuit` | count | FastPath routes |

```bash
# 24h ocupação + saúde
RID="/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Network/expressRouteCircuits/<NAME>"
az monitor metrics list --resource "$RID" \
  --metrics BitsInPerSecond BitsOutPerSecond ArpAvailability BgpAvailability \
            QosDropBitsInPerSecond QosDropBitsOutPerSecond \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time   $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --interval PT1H --aggregation Average Maximum -o json
```

## Step 3 — Per-circuit detail and BGP table

```bash
# Circuit details (peerings, ASNs, VLANs, prefixes)
az network express-route show --ids "$RID"

# Peering stats
az network express-route get-stats --ids "$RID" --peering-name AzurePrivatePeering

# ARP table (verifica L2 com o provider)
az network express-route list-arp-tables --ids "$RID" --peering-name AzurePrivatePeering --path primary
az network express-route list-arp-tables --ids "$RID" --peering-name AzurePrivatePeering --path secondary

# Route table (rotas BGP)
az network express-route list-route-tables --ids "$RID" --peering-name AzurePrivatePeering --path primary
az network express-route list-route-tables-summary --ids "$RID" --peering-name AzurePrivatePeering --path primary
```

## Step 4 — VNG health (different metrics by gateway type)

### ExpressRoute Gateway (gatewayType=ExpressRoute)
| Metric | Unit | Threshold |
|---|---|---|
| `ExpressRouteGatewayCpuUtilization` | % | 🟢 <70% / 🟡 70-85% / 🔴 >85% (resize) |
| `ExpressRouteGatewayBitsPerSecond` | bps | Compare to gateway SKU limit (Standard 1G, HighPerformance 2G, UltraPerformance 10G, ErGw1AZ 1G, ErGw2AZ 2G, ErGw3AZ 10G) |
| `ExpressRouteGatewayPacketsPerSecond` | pps | |
| `ExpressRouteGatewayCountOfRoutesAdvertisedToPeer` | count | Watch the 1000-prefix limit |
| `ExpressRouteGatewayCountOfRoutesLearnedFromPeer` | count | Same limit |

### VPN Gateway (gatewayType=Vpn)
| Metric | Unit | Use |
|---|---|---|
| `TunnelAverageBandwidth` | bps | per-tunnel |
| `TunnelEgressBytes` / `TunnelIngressBytes` | bytes | volume |
| `TunnelIngressPacketDropCount` / `TunnelEgressPacketDropCount` | count | should be 0 |
| `TunnelIngressPacketDropMismatchSelectorCount` | count | misconfig of traffic selectors |
| `AverageBandwidth` | bps | gateway aggregate |

```bash
# VNG metrics (auto-pick the right metrics by type)
GW_TYPE=$(az network vnet-gateway show --ids "$VNG_ID" --query gatewayType -o tsv)
if [[ "$GW_TYPE" == "ExpressRoute" ]]; then
  METRICS="ExpressRouteGatewayCpuUtilization ExpressRouteGatewayBitsPerSecond \
           ExpressRouteGatewayPacketsPerSecond \
           ExpressRouteGatewayCountOfRoutesAdvertisedToPeer \
           ExpressRouteGatewayCountOfRoutesLearnedFromPeer"
else
  METRICS="TunnelAverageBandwidth TunnelEgressBytes TunnelIngressBytes \
           TunnelIngressPacketDropCount TunnelEgressPacketDropCount AverageBandwidth"
fi
az monitor metrics list --resource "$VNG_ID" --metrics $METRICS \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --interval PT1H --aggregation Average Maximum -o json
```

## Step 5 — BGP peer status (when enableBgp=true)

```bash
# Live BGP peers for the gateway (real-time, not cached)
az network vnet-gateway list-bgp-peer-status --ids "$VNG_ID" -o json

# Routes the gateway LEARNED from a specific peer
az network vnet-gateway list-learned-routes --ids "$VNG_ID" -o json

# Routes the gateway ADVERTISES to a specific peer (requires --peer)
PEER_IP=$(az network vnet-gateway list-bgp-peer-status --ids "$VNG_ID" --query "value[0].neighbor" -o tsv)
az network vnet-gateway list-advertised-routes --ids "$VNG_ID" --peer "$PEER_IP" -o json
```

## Step 6 — Connection state (the actual hop ER↔VNG)

ExpressRoute circuits and VNGs are tied via **`Microsoft.Network/connections`**. Always include:

```bash
az graph query -q "Resources
  | where type =~ 'Microsoft.Network/connections'
  | project name, subscriptionId, resourceGroup,
            connType=tostring(properties.connectionType),
            connState=tostring(properties.connectionStatus),
            ingressBytes=tolong(properties.ingressBytesTransferred),
            egressBytes=tolong(properties.egressBytesTransferred),
            peer=tostring(properties.peer.id),
            vng=tostring(properties.virtualNetworkGateway1.id)
  | order by connState, name" --first 1000 -o json
```

`connectionStatus`: `Connected` ✅ / `Connecting` 🟡 / `NotConnected` 🔴 / `Unknown`.

## Pitfalls

1. **`hermes mcp add` argparse breaks on `@scoped` packages** — `--args -y @azure/mcp@latest server start` is parsed as multiple args and fails. Workaround: edit `~/.hermes/config.yaml` directly. Pattern that works:
   ```yaml
   azure_mcp:
     command: npx
     args:
     - -y
     - "@azure/mcp@latest"
     - server
     - start
     env:
       AZURE_CONFIG_DIR: /home/hermes/.azure
   ```

2. **Cloud CLI device codes go to `/dev/tty`, not stdout** — `az login --use-device-code` (Azure) and `aws sso login --use-device-code` (AWS) both write the URL+code straight to the terminal device, so background processes see nothing. Universal capture pattern that works for both:
   ```bash
   script -qfc 'az login --use-device-code' /tmp/azlogin.log    # Azure
   script -qfc 'aws sso login --sso-session <name> --use-device-code' /tmp/aws_sso.log    # AWS
   ```
   Then `cat` the log after ~5s to extract the code. The `setterm: terminal xterm does not support --blank` warning from `script` is harmless.

3. **AWS SSO without `--use-device-code` enters PKCE-with-127.0.0.1-callback mode**, which is unusable from a remote/headless host (the callback would have to land on the agent host's loopback, but the user's browser is elsewhere). `--no-browser` does NOT switch it to device-code — it still uses PKCE, just suppresses the browser open. Always use `--use-device-code` for headless. AWS CLI helpfully prints "run this command again with the '--use-device-code' option" when it detects the situation.

4. **`az login` ends with an interactive subscription picker** when the account has multiple subs — send Enter (empty input via `mcp_process action=submit data=""`) to accept the default and exit cleanly.

4. **ExpressRoute bandwidth NOT in `properties.bandwidthInMbps`** for provider-managed (Megaport, Equinix) circuits — it's in `properties.serviceProviderProperties.bandwidthInMbps`. The other field is `null`.

5. **MCR/Megaport circuits can burst above provisioned bandwidth** — peak metrics may show >100% utilization vs the Azure-side bandwidth value. Real ceiling is the Megaport MCR config; cross-check with the Megaport portal before alarming.

6. **VPN Gateway "Basic" SKU has NO BGP support and NO connection metrics** — won't show tunnel data. To inspect, you'd need to upgrade SKU.

7. **BgpAvailability/ArpAvailability stay 100% even when one of the two sub-interfaces is down** — they aggregate. To detect single-leg outages you need to look at `peer.connectionStatus` per connection or set up Connection Monitor extension.

8. **Resource Graph queries are eventually consistent** — newly-created resources may take 1-5 minutes to appear. For real-time, use `az ... list --subscription <id>` instead.

9. **`--aggregation` accepts space-separated values, not comma-separated** — `--aggregation Average Maximum` works; `--aggregation Average,Maximum` fails silently.

10. **Reports against ALL subs may hit throttling** — Azure Resource Graph: 15 req/5s per user. For 50+ subs, batch the inventory query (single graph call covers all subs in one shot — that's the whole point of using Resource Graph instead of looping `az account set`).

11. **Rocky 9 / RHEL 9 mount `/tmp` with `noexec`** by default — installers extracted there fail with `Permission denied` even when the file has +x and you have sudo. Symptom: `sudo: unable to execute ./script: Permission denied`. Workaround: invoke the interpreter explicitly (`sudo bash /tmp/installer.sh`) or extract to `/var/tmp` (which is exec by default) or `/opt`. Verify with `mount | grep '/tmp '` — look for `noexec` flag.

12. **Cloud-CLI auth playbook for this Hermes box (cross-provider)** — see `references/headless-cloud-auth.md` for the full pattern (Azure + AWS device-code, log capture, killing stale OIDC flows, multi-account picker handling).

## Reference scripts (this skill ships them)

- `scripts/er_report.sh` — 24h ExpressRoute health + occupation report (all circuits in tenant)
- `scripts/vng_report.sh` — 24h VNG health report (all VNGs in tenant)
- `scripts/connections_audit.sh` — connection-state audit (ER↔VNG links)

Run them as: `bash <skill_dir>/scripts/er_report.sh > /tmp/er_24h.json`

## Quick reference — corp topology snapshot (May 2026)

- 3 ExpressRoute circuits (all in `network-transit-PROD` / `rg_network_connections`):
  - `ER_MCR-EQX-CH4-CORESITE-CHI_AZ-CENTRAL-US_EQX-CH4` — Megaport @ Chicago, 1 Gbps, centralus
  - `ER_MCR-DR-ATL13-AZ-EAST-US_EQX-AT1` — Megaport @ Atlanta, 1 Gbps, eastus
  - `ER_MCR-DR-ATL13-AZ-EAST-US2_EQX-AT1` — Megaport @ Atlanta, 2 Gbps, eastus2
- 9 VNGs across 5 subs (transit hubs in `network-transit-PROD` are UltraPerformance ER Gateways)
- All BGP peers Azure ASN `12076` (Microsoft) ↔ Peer ASN `65310`/`65320` (private)
