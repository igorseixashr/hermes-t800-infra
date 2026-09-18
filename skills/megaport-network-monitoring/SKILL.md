---
name: megaport-network-monitoring
description: "Monitor Megaport (NaaS) Ports, MCRs, MVEs, VXCs, BGP sessions, IPsec tunnels, and cross-cloud correlation (AWS DX, Azure ExpressRoute, GCP Partner Interconnect) via REST API at api.megaport.com."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Megaport, Networking, NaaS, MCR, VXC, BGP, AWS, Azure, GCP, ExpressRoute, DirectConnect, Interconnect, corp, MultiCloud]
    related_skills: [aws-network-monitoring, azure-network-monitoring, gcp-network-monitoring]
---

# Megaport Network-as-a-Service Monitoring

Operational playbook to inventory and monitor Megaport NaaS connectivity (physical Ports, MCRs, MVEs, VXCs to AWS/Azure/GCP/Internet/cross-MCR) via the public REST API at `api.megaport.com`. Includes cross-cloud correlation so a single Megaport VXC maps directly to the AWS DX connection, Azure ExpressRoute circuit, or GCP Partner Interconnect attachment on the other side.

## When to use this skill

Whenever the user asks about:
- Megaport connectivity status, "estão todas as VXCs UP?", "alguma conexão caída?"
- Status do MCR / BGP / túneis IPsec
- Inventário das portas físicas, MCRs, MVEs
- Correlação Megaport ↔ cloud provider ("qual ExpressRoute corresponde a essa VXC?", "essa VXC vai pra qual DX?")
- Capacidade / utilização das portas (rate limit em uso vs port speed)
- Relatórios de saúde NaaS / cross-cloud
- "Algo mudou no Megaport recentemente?" (activity log)

## Prerequisites

- Megaport API Key generated in the Portal: **Tools → API Key Generator** (role `Read Only` is enough for monitoring; principle of least privilege)
- Credentials stored in `~/.bashrc.d/megaport.env` (chmod 600) — sourced automatically by the existing `~/.bashrc.d/*` loop:
  ```
  export MEGAPORT_CLIENT_ID="..."
  export MEGAPORT_CLIENT_SECRET="..."
  export MEGAPORT_AUTH_URL="https://auth-m2m.megaport.com/oauth2/token"
  export MEGAPORT_API_URL="https://api.megaport.com"
  ```
- `curl`, `python3`, `jq` (preinstalled on Rocky 9)
- Optional for correlation: AWS CLI / Azure CLI / gcloud authenticated in the matching cloud accounts (see related skills)

## Authentication (OAuth2 client_credentials)

Megaport uses **OAuth2 client_credentials grant**, not API key in header. Token TTL is whatever was configured on the API key (default 1440 min = 24h).

```bash
source ~/.bashrc.d/megaport.env

curl -sS -X POST "$MEGAPORT_AUTH_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -u "$MEGAPORT_CLIENT_ID:$MEGAPORT_CLIENT_SECRET" \
  --data-urlencode "grant_type=client_credentials" \
  -o /tmp/megaport_token.json

TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/megaport_token.json'))['access_token'])")
```

Response shape:
```json
{ "access_token": "eyJraWQi...", "expires_in": 86400, "token_type": "Bearer" }
```

All subsequent calls: `Authorization: Bearer $TOKEN`.

## Core endpoints (validated against corp tenant May/2026)

| Endpoint | Method | Purpose | Read-Only OK? |
|---|---|---|---|
| `GET /v2/products` | GET | **Inventory all top-level products** (Ports, MCRs, MVEs) + their `associatedVxcs[]` | ✅ |
| `GET /v2/product/{productUid}` | GET | **Detailed status** of one service (Port/MCR/MVE/VXC) including `up`, `provisioningStatus`, `resources.csp_connection` with **AWS connectionId / Azure service_key / GCP pairingKey** | ✅ |
| `GET /v3/products/mcrs/{uid}/ipsec` | GET | IPsec tunnels on an MCR (max 30 per MCR, count, details) — Oct/2025 endpoint | ✅ |
| `GET /v3/activity` | GET | Tenant activity log (logins, API key generation, service changes) | ✅ |
| `GET /v3/locations` | GET | Megaport datacenter catalog (~400KB, use to resolve `locationId`) | ✅ |
| `GET /v2/employee` | GET | Tenant users | ❌ (admin only — 404 with read-only) |
| Looking Glass routes API | n/a | **Not exposed in the public API on read-only keys** — Portal UI only (the docs mention "a public API is available" but the endpoint requires elevated perms). For BGP state, use `resources.csp_connection.bgp_status` from `/v2/product/{vxc_uid}` instead | partial |
| Maintenance/outage events | n/a | **Not on the read-only API**. The portal Service Status page is the only surface. Email notifications come from `noreply@megaport.com`. | ❌ |

> **The `bgp_status` field inside each VXC's `csp_connection` IS the BGP state** (1=UP, 0=DOWN per peer IP). That's how this skill checks BGP health without Looking Glass.

## Product types

| productType | What it is | Speed unit |
|---|---|---|
| `MEGAPORT` | Physical port (1G/10G/100G fibre into a Megaport DC) | Mbps in `portSpeed` |
| `MCR2` | Megaport Cloud Router (virtual L3 router with BGP, MCR generation 2) | Mbps |
| `MVE` | Megaport Virtual Edge (VM-form NFV appliance — Cisco/Fortinet/PAN/etc) | Mbps |
| `VXC` | Virtual Cross Connect (the actual circuit between two endpoints) | `rateLimit` Mbps |
| `IX` | Internet Exchange peering port | Mbps |

## Provisioning state vs operational state — READ THIS

There are **two different "up" signals** and they can disagree:

| Field | Where | Meaning |
|---|---|---|
| `provisioningStatus` | top-level of any product | Lifecycle state: `DEPLOYABLE` → `CONFIGURED` → `LIVE` → `CANCELLED` → `DECOMMISSIONED` (or `FAILED`) |
| `up` | top-level (boolean) | **Operational** — service is UP and passing traffic (`true`) or DOWN (`false`) |
| `resources.vll.up` | inside VXC resources | Internal L2 transport link state (1=up, 0=down) |
| `resources.csp_connection.bgp_status` | inside VXC resources (MCR side) | dict `{peer_ip: 1|0}` per BGP neighbor |

A VXC with `provisioningStatus=LIVE` but `up=false` means the circuit is configured and billing but data plane is broken — alert on this combo.

## Cross-cloud correlation (the killer feature)

The `bEnd.connectType` of each VXC tells you what cloud it lands in, and the `resources.csp_connection` array carries the **exact identifier on the cloud side**:

| connectType | `csp_connection` identifier | Correlates to (cloud side) |
|---|---|---|
| `AWSHC` | `connectionId` (e.g. `dxcon-fh1mcdyj`) + `ownerAccount` (12-digit AWS account ID) | `aws directconnect describe-connections --connection-id dxcon-...` in that account |
| `AZURE` | `service_key` (UUID, e.g. `7499111a-30f9-...`) + `vlan` | ExpressRoute Circuit `.serviceKey` field in Azure (the Azure-side property) |
| `GOOGLE` | `pairingKey` (e.g. `5dc1fdf5-.../us-east1/1`) | `gcloud compute interconnects attachments describe --format='value(pairingKey)'` |
| `TRANSIT` | n/a — Megaport Internet ISP | Internet (no cloud-side equivalent) |
| `VROUTER` | n/a — terminates on another Megaport MCR | Cross-MCR private link inside Megaport |
| `DEFAULT` | n/a — Port-to-Port (DCI / private cross-connect) | Customer-managed |

**Workflow for full correlation:**

1. `scripts/inventory.py` → list all Megaport products + VXCs, extract `connectionId`/`service_key`/`pairingKey` per VXC.
2. For each cloud-side identifier, run the matching cloud CLI to fetch the cloud-side resource (DX in target account, ExpressRoute circuit by serviceKey, Interconnect attachment by pairingKey).
3. Join on UID/key → produce unified report.

Example for AWS (uses `aws-network-monitoring` skill's cross-account assume-role pattern):
```bash
# From the Megaport JSON: ownerAccount=823512721299, connectionId=dxcon-fh1mcdyj
aws sts assume-role --role-arn arn:aws:iam::823512721299:role/corp-Network-ReadOnly ...
aws --profile assumed directconnect describe-connections --connection-id dxcon-fh1mcdyj
```

Example for Azure (ExpressRoute circuit serviceKey is globally unique in your tenant):
```bash
az network express-route list --query "[?serviceKey=='7499111a-30f9-40f6-b4f9-dd7ef653f7b0']" -o json
```

Example for GCP (pairingKey of the customer-side InterconnectAttachment):
```bash
gcloud asset search-all-resources \
  --scope=organizations/1053327236318 \
  --asset-types=compute.googleapis.com/InterconnectAttachment \
  --format=json | jq '.[] | select(.additionalAttributes.pairingKey == "5dc1fdf5-...")'
```

## Step-by-step report workflow

1. **Auth once** → save token (24h TTL).
2. **`scripts/inventory.py`** → snapshot of every Port / MCR / VXC with up/status/rate.
3. **`scripts/vxc_status_report.py`** → per-VXC health (up flag, BGP status, A-End/B-End locations, csp_connection identifier per provider).
4. **`scripts/mcr_status.py`** → MCRs with ASN, port speed in use, BGP peer count, IPsec tunnel count.
| `GET /v2/product/{uid}/telemetry` | GET | **Utilization telemetry** (bits/s) | ❌ (returns 404 for read-only keys) |

> **Telemetry endpoint is not available for standard Read-Only API keys.** If utilization metrics are required, correlate the VXC `csp_connection` identifier (AWS connectionId, Azure service_key, or GCP pairingKey) with the respective cloud provider's monitoring API (e.g., `az monitor metrics list`).

## Pitfalls

1. **Token expires (default 24h)** — re-auth or you'll start getting 401. Treat the token file as cache and refresh when older than `expires_in - 5min`.

2. **`/v2/products` doesn't list VXCs at the top level** — VXCs are nested inside each parent Port/MCR's `associatedVxcs[]` array. The SAME VXC appears in **both** its A-End parent and B-End parent — always deduplicate by `productUid` when counting.

3. **Read-only API key has limits** — `/v2/employee`, `/v2/outages`, `/v2/product/{uid}/telemetry`, looking-glass endpoints all return 404 with read-only role. For monitoring this is fine; for change ops you need Company Admin.

4. **`csp_connection` shape changes between list view and detail view** — in `/v2/products` it's a **dict**, in `/v2/product/{uid}` it's a **list** of dicts (one per "side" — VROUTER side and cloud side both appear). Code must handle both.

5. **`connectType=VROUTER` is the MCR side**, NOT the cloud side. The cloud-side connectType is on `bEnd.connectType` or as a separate entry in the `csp_connection` list (`AWSHC` / `AZURE` / `GOOGLE`).

6. **BGP status field is per-peer-IP**, not per-VXC: `bgp_status = {"10.255.0.2": 1, "10.255.0.3": 1}`. A VXC can have multiple BGP peers (e.g., AWS DX with redundant amazonIpAddresses). One down = degraded redundancy, not full outage.

7. **`provisioningStatus=LIVE` ≠ traffic flowing** — check the boolean `up` flag AND `resources.vll.up` AND `bgp_status` for the full picture. A LIVE circuit with `up=false` is configured and billed but broken on data plane.

8. **Provider tag for ExpressRoute is by `service_key`** — that's the Azure-side `serviceKey` property of the `Microsoft.Network/expressRouteCircuits` resource, NOT the Megaport-internal UID. Search Azure with `--query "[?serviceKey=='...']"`.

9. **corp diversity convention: `red` and `blue`** — every HA pair has a red+blue. The `diversityZone` field on each VXC and Port reflects this. Alert if both members of a red/blue pair are down simultaneously.

10. **`/v3/locations` is huge (~400KB, 800+ locations worldwide)** — cache locally; only ~6 are relevant for corp (QTS-ATL, QTS-CHI, DR-ATL13, EQX-CH4, EQX-SP4, ASCT-SP4, EQX-RJ2).

11. **Auth endpoint is on `auth-m2m.megaport.com`**, NOT `api.megaport.com`. Easy to typo. Production vs staging:
    - Prod auth: `auth-m2m.megaport.com/oauth2/token`
    - Staging auth: `auth-m2m-staging.megaport.com/oauth2/token`

12. **API keys are environment-specific** — a prod key won't work against staging and vice-versa.

13. **Telemetry API (404 issue)**: The `GET /v2/product/{uid}/telemetry` endpoint is restricted to Company Admin/Standard roles and **returns 404 for standard Read-Only API keys**. **DO NOT ATTEMPT TO USE THIS.** For utilization metrics, rely exclusively on cloud-native tools (Azure Monitor/AWS CloudWatch/GCP Monitoring) using the cloud-side identifier found in the VXC's `csp_connection` field (e.g., `service_key` for Azure ExpressRoute).

## corp-specific topology snapshot (May 2026)

### 6 Physical Ports
- `MEGAPORT-100G-QTS-ATL-RED-PORT` / `-BLUE-PORT` (QTS Atlanta, 100G each, diversity red+blue)
- `MEGAPORT-100G-QTS-CHI-RED-PORT` / `-BLUE-PORT` (QTS Chicago, 100G each)
- `MEGAPORT-10G-ASCT-SP4` (Ascenty SP4, 10G, blue)
- `MEGAPORT-10G-EQX-RJ2` (Equinix RJ2, 10G, no zone — DCI to SP)

### 5 MCRs (all gen 2)
- `MCR-DR-ATL13-RED` / `-BLUE` (Digital Realty ATL13, 10G each, ASN 65310/65311)
- `MCR-EQX-CH4-BLUE` (Equinix CH4, 10G, ASN region us-central)
- `MCR-EQX-SP4-RED` (Equinix SP4, **5G**, Brazil)
- `MCR-CORESITE-CHI-RED` (CoreSite CH1, 10G)

### 34 VXCs (all LIVE/up at last snapshot)
- **4 AWS DX** (AWSHC): ATL13-red, ATL13-blue, CH4-blue, CoreSite-CH1 → all 1Gbps each
- **6 Azure ExpressRoute** (AZURE): ATL13-red×2 (East-US + East-US2), ATL13-blue×2, CH4-blue, CoreSite-CH1
- **5 GCP Interconnect** (GOOGLE): ATL13-red, ATL13-blue, CH4-blue, CoreSite-CH1, **datasync 10G (Port→Google directly, ASN 33282 cross-project)**
- **4 Megaport Internet TRANSIT**: ATL→DR-ATL13, ATL→EQX-AT1, CHI→DR-CHI2, CHI→EQX-CH4 (all 10Gbps)
- **10 cross-MCR VROUTER** (private inter-MCR backbone): RED↔BLUE pairs, ATL↔CHI, ATL↔SP, CH4↔SP
- **5 DEFAULT** (port-to-port DCI): QTS-ATL↔QTS-CHI red/blue 10G, ASCT-SP4↔EQX-RJ2 2G, MCR-ZONE↔QTS-ATL/CHI uplinks

### BGP ASN map (Megaport side)
- MCR-DR-ATL13-RED: ASN 65310
- MCR-DR-ATL13-BLUE: ASN 65311 (inferred from naming)
- AWS peers: as configured per VXC
- GCP datasync peer: ASN 33282 (Google)

## Reference scripts (this skill ships them)

- `scripts/inventory.py` — auth + `/v2/products` → JSON snapshot of Ports/MCRs/VXCs with status summary
- `scripts/vxc_status_report.py` — per-VXC health report, BGP state, csp identifiers, A/B-End locations
- `scripts/mcr_status.py` — MCRs with ASN, IPsec tunnel count, VXC count, diversity zone
- `scripts/correlate_cross_cloud.py` — extracts cloud-side identifiers (connectionId/service_key/pairingKey) per VXC for joining with AWS/Azure/GCP CLI outputs

All scripts:
- Read credentials from `~/.bashrc.d/megaport.env` (source automatic via shell, or read os.environ in Python)
- Cache token in `/tmp/megaport_token.json` and re-auth automatically when expired
- Print human-readable tables AND emit JSON when `--json` flag is passed (machine-readable for piping)
