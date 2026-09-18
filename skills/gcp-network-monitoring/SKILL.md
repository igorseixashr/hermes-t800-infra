---
name: gcp-network-monitoring
description: "Monitor GCP Partner Interconnects, Cloud Routers, BGP peers, HA/Classic VPN tunnels via gcloud + Cloud Asset Inventory + Cloud Monitoring REST API across multi-project organizations."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GCP, Networking, Interconnect, CloudRouter, VPN, BGP, CloudMonitoring, corp, MultiProject]
    related_skills: [aws-network-monitoring, azure-network-monitoring, native-mcp]
---

# GCP Network Monitoring — Interconnects, Cloud Routers, VPN

Operational playbook to inventory and monitor GCP network connectivity (Partner/Dedicated Interconnects, Cloud Routers + BGP peers, HA VPN, Classic VPN tunnels) across **all projects** in a GCP Organization. Uses gcloud CLI + Cloud Asset Inventory (org-wide) + Cloud Monitoring REST API.

## When to use this skill

Whenever the user asks about:
- Cloud Interconnect occupation / utilization / saturation
- Cloud Router BGP session state, learned routes, advertised routes
- VPN tunnel status, IKE state, BGP over VPN
- Cross-project network inventory in GCP
- "Algum interconnect saturando?", "BGP peer caiu?", "VPN tunnel UP?"

## Prerequisites

- gcloud CLI v500+ (Rocky 9: install via `dnf` from `packages.cloud.google.com/yum/repos/cloud-sdk-el9-x86_64`)
- Authenticated: `gcloud auth login --no-launch-browser --update-adc`
  - Use the `4/0Aeo...` verification code returned by the Google OAuth page
  - `--update-adc` also configures Application Default Credentials (needed by gcloud-mcp)
- IAM role: at minimum `roles/compute.networkViewer` (corp uses `roles/compute.networkAdmin` distributed via SA)
- jq + python3 (preinstalled on Rocky 9)
- Org-wide IAM: `roles/cloudasset.viewer` for `cloudasset` API queries (the killer feature for cross-project discovery)
- gcloud-mcp registered as `gcp_mcp` in `~/.hermes/config.yaml`

## corp-specific defaults

- **Organization:** `corp.io` (id `1053327236318`)
- **Total projects:** ~750 real (filter `NOT projectId:sys-*` to exclude 38k Apps Script noise projects)
- **Hub project for Interconnects + Routers:** `transit-network-228018`
- **Default region(s):** `us-east1`, `us-central1`
- **5 Partner Interconnect attachments** (all Megaport):
  - 2x us-east1 (DigitalRealty ATL13, 1Gbps each, red+blue) → `cr-us-east-1-megaport`
  - 2x us-central1 (Equinix CH4, 1Gbps each, red+blue) → `cr-us-central1-megaport`
  - 1x us-east1 (Atlanta, 10Gbps, datasync) → `cr-datasync-atl-10g` (peer ASN 33282 = Google! Cross-project peering via Megaport)
- **8 Cloud Routers in transit project**, 38 total org-wide (most are `cloud-nat-router-*`)
- **VPN deployment:**
  - HA VPN: `tau-rex` + `stg-tau-rex` (us-central1)
  - Classic VPN: `keycloak-prd` + `keycloak-nonprd` (us-east1, peers Azure 40.118.210.85)
- **Pin default project + ADC quota project:**
  ```bash
  gcloud config set project transit-network-228018
  gcloud auth application-default set-quota-project transit-network-228018
  ```

## Step 1 — Cross-project inventory (Cloud Asset Inventory)

GCP doesn't have a single API like Azure Resource Graph, but **Cloud Asset Inventory** provides an org-wide alternative. Critical for finding resources without iterating 750 projects.

```bash
# All Interconnect attachments + Interconnects org-wide (one call, no project loop!)
gcloud asset search-all-resources \
  --scope=organizations/1053327236318 \
  --asset-types=compute.googleapis.com/InterconnectAttachment,compute.googleapis.com/Interconnect \
  --page-size=500 --format=json

# All Cloud Routers
gcloud asset search-all-resources \
  --scope=organizations/1053327236318 \
  --asset-types=compute.googleapis.com/Router \
  --page-size=500 --format=json

# All VPN gateways and tunnels
gcloud asset search-all-resources \
  --scope=organizations/1053327236318 \
  --asset-types=compute.googleapis.com/VpnGateway,compute.googleapis.com/TargetVpnGateway,compute.googleapis.com/VpnTunnel \
  --page-size=500 --format=json
```

`parentFullResourceName` field in each result tells you the project. Group by project to get the inventory split.

**IMPORTANT:** if `cloudasset` returns 0 results, the API is not enabled or the user lacks `roles/cloudasset.viewer` at org level. Falling back to per-project `gcloud compute interconnects list` works but is 10-100x slower.

## Step 2 — Interconnect attachment details

```bash
PROJECT=transit-network-228018
gcloud compute interconnects attachments list --project=$PROJECT --format=json
# Per-attachment describe (gives bandwidth, BGP IPs, VLAN tag, partner metadata)
gcloud compute interconnects attachments describe <NAME> --project=$PROJECT --region=<REGION> --format=json
```

Key fields:
- `type`: `PARTNER` (Megaport-style) or `DEDICATED` (direct peering w/ Google)
- `bandwidth`: `BPS_50M`, `BPS_100M`, `BPS_500M`, `BPS_1G`, `BPS_2G`, `BPS_5G`, `BPS_10G`, `BPS_50G` (need to map to bytes/sec for utilization%)
- `state`: `ACTIVE` / `PENDING_PARTNER` / `DEFUNCT`
- `edgeAvailabilityDomain`: `AVAILABILITY_DOMAIN_1` (red) or `_2` (blue) — for HA pair
- `cloudRouterIpAddress` + `customerRouterIpAddress`: BGP /29 link IPs
- `pairingKey`: identifier shared with Megaport portal
- `partnerMetadata.partnerName` + `interconnectName`: human-readable partner location

## Step 3 — Cloud Router + BGP runtime status

```bash
# List
gcloud compute routers list --project=$PROJECT --format=json

# Describe (config: BGP ASN, peers, advertise mode, advertised prefixes)
gcloud compute routers describe <NAME> --project=$PROJECT --region=<REGION> --format=json

# RUNTIME status (BGP peer state, learned routes, uptime) — KEY for monitoring
gcloud compute routers get-status <NAME> --project=$PROJECT --region=<REGION> --format=json
```

`get-status` returns under `result.bgpPeerStatus[]`:
- `status`: `UP` / `DOWN` / `UNKNOWN` (NOT `Established` like Cisco)
- `numLearnedRoutes`: BGP prefixes received from peer
- `uptime`: human-readable BGP session uptime
- `linkedVpnTunnel` or `linkedInterconnectAttachment`: which underlying transport

## Step 4 — Cloud Monitoring (REST API direct)

**`gcloud monitoring` does NOT have time-series query** — must use REST API directly. Pattern:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -sH "Authorization: Bearer $TOKEN" \
  "https://monitoring.googleapis.com/v3/projects/$PROJECT/timeSeries?\
filter=metric.type%20%3D%20%22interconnect.googleapis.com%2Fnetwork%2Fattachment%2Fsent_bytes_count%22%20\
AND%20resource.labels.attachment%20%3D%20%22ATTACHMENT_NAME%22\
&interval.startTime=2026-01-01T00:00:00Z\
&interval.endTime=2026-01-02T00:00:00Z\
&aggregation.alignmentPeriod=3600s\
&aggregation.perSeriesAligner=ALIGN_RATE"
```

Key metrics for `resource.type=interconnect_attachment`:
| Metric | Unit | What it tells you |
|---|---|---|
| `interconnect.googleapis.com/network/attachment/sent_bytes_count` | bytes (DELTA) | Egress (use ALIGN_RATE → bytes/s, *8 = bps) |
| `interconnect.googleapis.com/network/attachment/received_bytes_count` | bytes (DELTA) | Ingress |
| `interconnect.googleapis.com/network/attachment/sent_packets_count` | count (DELTA) | Egress packet rate |
| `interconnect.googleapis.com/network/attachment/received_packets_count` | count | Ingress packet rate |
| `interconnect.googleapis.com/network/attachment/egress_dropped_packets_count` | count | **Egress drops** — alert when > 0 |
| `interconnect.googleapis.com/network/attachment/ingress_dropped_packets_count` | count | **Ingress drops** |
| `interconnect.googleapis.com/network/attachment/capacity` | bps | Configured bandwidth |

For `resource.type=interconnect` (the underlying physical circuit, only on DEDICATED):
| Metric | Use |
|---|---|
| `interconnect.googleapis.com/network/interconnect/operational` | Link UP=1, DOWN=0 |
| `interconnect.googleapis.com/network/interconnect/link/rx_power` | Light level RX (dBm) |
| `interconnect.googleapis.com/network/interconnect/link/tx_power` | Light level TX (dBm) |
| `interconnect.googleapis.com/network/interconnect/dropped_packets_count` | Physical link drops |

For VPN: `resource.type=vpn_gateway` and `vpn_tunnel`:
| Metric | Use |
|---|---|
| `vpn.googleapis.com/tunnel_established` | Tunnel UP=1, DOWN=0 |
| `vpn.googleapis.com/network/sent_bytes_count` | Egress |
| `vpn.googleapis.com/network/received_bytes_count` | Ingress |

For Cloud Router BGP:
| Metric | Use |
|---|---|
| `router.googleapis.com/bgp/sent_routes_count` | Routes advertised to peer |
| `router.googleapis.com/bgp/received_routes_count` | Routes learned from peer |
| `router.googleapis.com/bgp/bfd/session_up` | BFD session state (when configured) |
| `router.googleapis.com/nat/sent_bytes_count` | Cloud NAT throughput |

## Step 5 — VPN tunnel state

```bash
gcloud compute vpn-tunnels list --project=$PROJECT --format=json
gcloud compute vpn-gateways list --project=$PROJECT --format=json          # HA VPN
gcloud compute target-vpn-gateways list --project=$PROJECT --format=json   # Classic VPN
```

Tunnel `status` values:
- `ESTABLISHED` 🟢 — IKE+IPsec up, traffic flowing
- `WAITING_FOR_FULL_CONFIG` 🟡 — config incomplete on one side
- `FIRST_HANDSHAKE` 🟡 — IKE just started
- `NEGOTIATION_FAILURE` 🔴 — IKE/PSK/proposal mismatch
- `NO_INCOMING_PACKETS` 🔴 — local side OK, but peer not sending — **likely peer-side outage or misconfigured**
- `REJECTED` 🔴 — peer rejecting connection
- `DEPROVISIONING` / `PROVISIONING` — transient

The `detailedStatus` field has human-readable reasons.

## Pitfalls

1. **Org-wide visibility requires `cloudasset` API + IAM**. Without it, you must iterate every project (slow, hits rate limits). Enable in your hub project: `gcloud services enable cloudasset.googleapis.com --project=<hub>` and grant `roles/cloudasset.viewer` at org level.

2. **`gcloud projects list` returns Apps Script auto-projects (`sys-*`)** — corp has 38k of them, polluting any naive iteration. ALWAYS filter `--filter='NOT projectId:sys-* AND lifecycleState:ACTIVE'`.

3. **`gcloud monitoring` lacks `time-series` subcommand** — common confusion. Use REST API direct (`curl -H "Authorization: Bearer $(gcloud auth print-access-token)"`).

4. **Resource labels are NOT documented in metric descriptors** — query the resource descriptor separately:
   ```bash
   curl -sH "Authorization: Bearer $TOKEN" \
     "https://monitoring.googleapis.com/v3/projects/$PROJECT/monitoredResourceDescriptors/interconnect_attachment"
   ```
   For `interconnect_attachment` the label key is `attachment` (NOT `attachment_name` like you'd guess from `gcloud compute interconnects attachments list`).

5. **DELTA metrics need ALIGN_RATE** to convert to per-second. Without it, you get raw bytes-per-period that vary with `alignmentPeriod`.

6. **Bandwidth in bytes/sec, traffic in bits/sec** — `sent_bytes_count` aligned with ALIGN_RATE returns bytes/s. Multiply by 8 for bps utilization%.

7. **`Interconnect` (physical) vs `InterconnectAttachment` (VLAN)** — Partner Interconnect customers (Megaport, Equinix Fabric) only see attachments. The physical `Interconnect` resource is owned by the partner, NOT visible to your account. Don't confuse them. corp has 0 Dedicated Interconnects, 5 Partner attachments.

8. **`gcloud compute interconnects attachments list` doesn't accept `--regions=`** (plural — that's for some other commands). Use either no filter (lists all regions) or `--filter='region:us-east1'`.

9. **Cloud Router BGP peer status field is `UP`** — NOT `Established` (Cisco) or `Connected` (Azure). Don't reuse health-check logic from other clouds blindly.

10. **`NO_INCOMING_PACKETS` on classic VPN is silent for days** — there's no metric alarm by default. The tunnel shows up as live in `gcloud compute vpn-tunnels list` but isn't actually working. Run `get-status` periodically or set up dedicated CM alert on `vpn.googleapis.com/tunnel_established`.

11. **`gcloud auth login` PKCE requires browser callback** — useless on headless. ALWAYS use `--no-launch-browser`. The CLI prints a URL; user pastes the resulting `4/0Aeo...` code back. Same dance as az/aws-sso.

12. **ADC quota-project ≠ active project** generates warnings on every gcloud call. Fix once with `gcloud auth application-default set-quota-project <project>`.

## Consuming inventory.py from external scripts

The `scripts/inventory.py` here writes to a **file** (via `--out PATH`), not stdout. This differs from the Megaport equivalent which has `--json` for stdout. When orchestrating from a shell wrapper that expects stdout, pipe through a temp file:

```bash
local outfile=$(mktemp --suffix=.json)
python3 inventory.py --out "$outfile" >&2  # progress goes to stderr
cat "$outfile"  # JSON goes to stdout
```

The output is in **Cloud Asset Inventory shape**, NOT gcloud-direct shape:

- Top-level keys: `{interconnects, routers, vpns}` — flat lists
- VPN gateways, target VPN gateways, AND VPN tunnels are ALL inside `vpns[]` — discriminate via `assetType.endswith('/VpnTunnel')` etc
- Interconnect attachments and physical Interconnects both in `interconnects[]` — discriminate via `assetType`
- Fields: `displayName` (not `name`), `location` (not `region`), `state` (not `status`)
- Peer IP nested in `additionalAttributes.peerIp`
- Project ID extracted from `parentFullResourceName` (`//cloudresourcemanager.googleapis.com/projects/<id>` → split on `/`)

**Important: Asset Inventory shows provisioning state, NOT runtime state.** A tunnel stuck in `NO_INCOMING_PACKETS` (like corp's `keycloak-prd`) will appear here with `state: ESTABLISHED`. For runtime checks, you still need `gcloud compute routers get-status` per router.

## Reference scripts (this skill ships them)

- `scripts/inventory.py` — org-wide discovery via Cloud Asset Inventory (IC, Routers, VPN)
- `scripts/ic_report.py` — 24h Interconnect attachments utilization + drops via Monitoring REST API
- `scripts/router_status.sh` — BGP peer status across all routers + counts learned routes
- `scripts/vpn_audit.sh` — VPN tunnel status across multi-project, flag anything not ESTABLISHED

## corp topology snapshot (May 2026)

### Interconnect attachments (5, all Partner/Megaport, all `transit-network-228018`)
- `con-us-central1-megaport-equinix-ch4-vlan-a-red` 1Gbps Equinix CH4 ord-zone1
- `con-us-central1-megaport-equinix-ch4-vlan-b-blue` 1Gbps Equinix CH4 ord-zone2
- `con-us-east1-megaport-digitalrealty-atl13-vlan-a-red` 1Gbps DR ATL13 atl-zone1
- `con-us-east1-megaport-digitalrealty-atl13-vlan-b-blue` 1Gbps DR ATL13 atl-zone2
- `interconnect-gcp-datasync-mega-a` **10Gbps** datasync (peer ASN 33282 = Google → cross-project peering via Megaport)

### BGP peers (5 active, all UP)
- ASN 65349 ↔ peer ASN 65320/65321 (us-central1, on-prem)
- ASN 65348 ↔ peer ASN 65310/65311 (us-east1, on-prem)
- ASN 65347 ↔ peer ASN 33282 (Google datasync 10G)

### VPN
- HA VPN: `tau-rex` (4 tunnels ESTABLISHED), `stg-tau-rex` (2 tunnels)
- Classic VPN: `keycloak-prd` (2 tunnels NO_INCOMING_PACKETS — **broken, peer Azure 40.118.210.85**)
- Classic VPN: `keycloak-nonprd`, `transit-network-228018` (gateways but no active tunnels)
