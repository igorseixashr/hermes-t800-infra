---
name: aws-network-monitoring
description: "Monitor AWS Direct Connect, Transit Gateways, Cloud WAN, and Site-to-Site VPN health/utilization across multi-account organizations via AWS CLI + CloudWatch + parallel cross-account queries."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [AWS, Networking, DirectConnect, TransitGateway, CloudWAN, VPN, BGP, CloudWatch, corp, MultiAccount, SSO]
    related_skills: [azure-network-monitoring, native-mcp]
---

# AWS Network Monitoring — Direct Connect, TGW, Cloud WAN

Operational playbook to inventory and monitor AWS network connectivity (Direct Connect, Transit Gateways, Cloud WAN core network, Site-to-Site VPN) across **all accounts** in an Organization. Uses AWS SSO + CLI v2 + CloudWatch + parallel queries.

## When to use this skill

Whenever the user asks about:
- Direct Connect occupation / saturation / link health
- Transit Gateway throughput, drops, attachments
- Cloud WAN core network state, segments, attachments
- BGP status of VIFs / VPNs
- Cross-account network inventory in AWS
- "Algum DX está saturando?", "Cloud WAN saudável?", "TGW com drops?"

## Prerequisites

- AWS CLI v2 (Rocky 9: `curl awscli-exe-linux-x86_64.zip → sudo bash ./aws/install`)
  - **Note:** `/tmp` is `noexec` on Rocky — invoke installer via `sudo bash /tmp/aws/install`, never `sudo /tmp/aws/install`.
- AWS SSO configured (`~/.aws/config` with `[sso-session <name>]`)
- Authenticated: `aws sso login --sso-session <name> --use-device-code`
  - **Note:** Default `aws sso login` uses PKCE with localhost callback (won't work on headless terminals). MUST use `--use-device-code` flag.
- jq + python3 (preinstalled on Rocky 9)
- All ~50+ accounts have `AWSNetworkAdministratorV2` role (the corp standard)
- AWS API MCP Server registered as `aws_mcp` in `~/.hermes/config.yaml`

## corp-specific defaults

- **SSO session:** `corp` → `https://d-906789a408.awsapps.com/start` (region `us-east-1`)
- **Total accounts:** 100 in the Organization
- **Network-relevant accounts:** ~18 with `network`/`shared`/`transit`/`hub` in name
- **Default role:** `AWSNetworkAdministratorV2` (95/100 accounts)
- **Default region:** `sa-east-1` (per profile); used 3 main regions: `sa-east-1`, `us-east-1`, `us-east-2`
- **CloudWAN:** 1 core network `core-network-0a607a0921ccdc3ae` in `global-network-004ecef77378d7c81` ("Cloud WAN corp"), edges in `us-east-1` and `us-east-2`, 16 segments, 106 attachments
- **Direct Connects:** 18 connections across 3 accounts (`corp-network-prod`, `rsfn-network`, `network-production-4588`)
- **Transit Gateways:** 49 visible (25 unique IDs, multiple shared via RAM)
- **Naming convention key DX accounts:**
  - `corp-network-prod` (823512721299) → 8 DX (production)
  - `rsfn-network` (651684790312) → 8 DX (RSFN/SPB redundancy)
  - `network-production-4588` (730335354588) → 2 DX (newer)

### Token Expired?
- `references/headless-sso-login.md` — refresh SSO tokens without a local browser.
- `references/corp-rsfn-guardrails.md` — mandatory parameters and SCP `p-sgjwr2g2` details for the RSFN account.
- `references/rsfn-network-account.md` — general account details.

## Step 1 — Setup SSO from scratch

```bash
mkdir -p ~/.aws
cat > ~/.aws/config <<'EOF'
[sso-session corp]
sso_start_url = https://d-906789a408.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access
EOF

# Login with device-code (required for headless terminals)
aws sso login --sso-session corp --use-device-code
# → Visit https://d-906789a408.awsapps.com/start/#/device, enter code shown
```

## Step 2 — Auto-generate profiles for all accounts

```python
# From Python — uses SSO token to enumerate accounts and generate profiles
import json, subprocess, os, glob, re

cache_dir = os.path.expanduser('~/.aws/sso/cache')
files = sorted(glob.glob(f'{cache_dir}/*.json'), key=os.path.getmtime, reverse=True)
for f in files:
    d = json.load(open(f))
    if 'accessToken' in d:
        token = d['accessToken']
        break

env = {**os.environ, 'AWS_PAGER': ''}
accs = []
nt = None
while True:
    cmd = ['aws', 'sso', 'list-accounts', '--access-token', token, '--region', 'us-east-1', '--max-results', '100', '--output', 'json']
    if nt: cmd += ['--next-token', nt]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    d = json.loads(r.stdout)
    accs.extend(d.get('accountList', []))
    nt = d.get('nextToken')
    if not nt: break

# For each account, list available roles and pick the best
def pick_role(roles):
    for pref in ['AWSNetworkAdministratorV2', 'AWSPowerUser', 'AWSAdministrator', 'AWSReadOnly']:
        if pref in roles: return pref
    return roles[0] if roles else None

# Parallel role listing
from concurrent.futures import ThreadPoolExecutor
def get_roles(acc):
    r = subprocess.run(['aws', 'sso', 'list-account-roles', '--access-token', token,
                        '--region', 'us-east-1', '--account-id', acc['accountId'], '--output', 'json'],
                       capture_output=True, text=True, env=env)
    rl = json.loads(r.stdout).get('roleList', [])
    return acc, [r['roleName'] for r in rl]

with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(get_roles, accs))

# Generate ~/.aws/config profiles
def slugify(name):
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    return s[:50] or 'unnamed'

# (full code in scripts/setup_profiles.py)
```

The skill ships `scripts/setup_profiles.py` ready to run.

## Step 3 — Cross-account inventory (parallel)

The fastest way to find resources across 50+ accounts is to **probe in parallel** (not sequential `aws account set`). AWS has no equivalent of Azure Resource Graph, so we parallelize ourselves.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

REGIONS = ['sa-east-1', 'us-east-1', 'us-east-2']
NETWORK_ACCOUNTS = ['aws-network', 'corp-network-prod', 'rsfn-network',
                    'network-production-4588', 'network-non-production',
                    'shared', 'shared-production', 'network-hub-gsn',
                    'network-homolog', 'corp-network-non-prod']

def probe(profile, region):
    """Count DX/TGW/VPN/CloudWAN per account+region"""
    env = {**os.environ, 'AWS_PAGER': ''}
    out = {'profile': profile, 'region': region}
    for cmd_label, cmd in [
        ('dx',   ['directconnect', 'describe-connections']),
        ('tgw',  ['ec2', 'describe-transit-gateways', '--filters', 'Name=state,Values=available']),
        ('vpn',  ['ec2', 'describe-vpn-connections', '--filters', 'Name=state,Values=available']),
        ('cwan', ['networkmanager', 'list-core-networks']),
    ]:
        r = subprocess.run(['aws', '--profile', profile, '--region', region, *cmd, '--output', 'json'],
                          capture_output=True, text=True, env=env, timeout=20)
        # ... parse and count
    return out

# All combinations in parallel
with ThreadPoolExecutor(max_workers=15) as ex:
    futs = [ex.submit(probe, p, r) for p in NETWORK_ACCOUNTS for r in REGIONS]
    results = [f.result() for f in as_completed(futs)]
```

**See `scripts/inventory.py` for full implementation.**

## Step 4 — Direct Connect metrics (KEY: connection vs VIF dimensions)

**IMPORTANT pitfall:** `AWS/DX` namespace has metrics under TWO different dimension sets:

| Metric type | Dimensions | Use for |
|---|---|---|
| **Connection-level** | `ConnectionId` only | Standalone (non-hosted) DX — gets `ConnectionBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress` |
| **VIF-level** | `ConnectionId` + `VirtualInterfaceId` (BOTH together!) | Hosted DX (Megaport, Equinix, partner-managed) — gets `VirtualInterfaceBpsEgress/Ingress` |

**Hosted DXes don't publish `ConnectionBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress`** — they only have `ConnectionState` and the VIF-level metrics. If you query VIF metrics with only `Name=VirtualInterfaceId,...` you get all zeros — you MUST pass BOTH dimensions:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DX --metric-name VirtualInterfaceBpsEgress \
  --dimensions Name=ConnectionId,Value=dxcon-xxx Name=VirtualInterfaceId,Value=dxvif-xxx \
  --start-time ... --end-time ... --period 3600 --statistics Average Maximum
```

**Available DX metrics:**
- Connection: `ConnectionState`, `ConnectionBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress + VirtualInterfaceBpsEgress/Ingress`, `ConnectionPpsEgress/Ingress`, `ConnectionLightLevelTx/Rx`, `ConnectionErrorCount`, `ConnectionEncryptionState`
- VIF: `VirtualInterfaceBpsEgress/Ingress`, `VirtualInterfacePpsEgress/Ingress`, `VirtualInterfaceBgpStatus`, `VirtualInterfaceBgpPrefixesAccepted/Advertised`

Light level healthy range: **-14 dBm to 0 dBm** (negative is normal — it's optical loss). Anything outside is a fiber/optic problem.

Run `scripts/dx_report.sh` for the full 24h report.

## Step 5 — Transit Gateway metrics

Available in `AWS/TransitGateway` namespace, dimension `TransitGateway` (NOT `TransitGatewayId`):

| Metric | Use |
|---|---|
| `BytesIn` / `BytesOut` | Total throughput per period (use Sum statistic) |
| `PacketsIn` / `PacketsOut` | Packet rate |
| `PacketDropCountBlackhole` | Blackholed traffic — alert when > 0 |
| `PacketDropCountNoRoute` | No-route drops — usually means missing route in TGW route table |
| `BytesDropCountBlackhole` / `BytesDropCountNoRoute` | Same as above but in bytes |

**Key concepts:**
- TGW is a regional resource — same Org may have many TGWs (one per region per "hub" account)
- Same TGW can be SHARED across accounts via AWS RAM. Listing it from each account counts duplicates. **Deduplicate by `TransitGatewayId`** before plotting.
- TGW route tables are separate resources with their own associations/propagations — query via `describe-transit-gateway-route-tables`
- **East-west FW-inspection topology** is common at corp: TGW has multiple ingress RTs (one per peering, default-routed to a Connect attachment toward FortiGate/PAN) plus matching egress RTs (one per FW Connect, statically pointing to destination peerings). When `PacketDropCountNoRoute > 0` on this kind of TGW, the gap is almost always missing destination CIDRs in the egress RTs. See `references/tgw-noroute-drops-investigation.md` for the systematic walk-through (validated on `tgw-banking-hub` May 2026).

Run `scripts/tgw_report.sh` for the full 24h report.

## Step 6 — Cloud WAN

```bash
# Discover (only needed in 1 region — list-core-networks is global-aware)
aws --profile <hub-account> --region us-east-1 networkmanager describe-global-networks
aws --profile <hub-account> --region us-east-1 networkmanager list-core-networks

# Core details (segments, edges)
aws --profile <hub-account> --region us-east-1 networkmanager get-core-network --core-network-id <id>

# Attachments (VPCs, TGWs, VPNs, Connect)
aws --profile <hub-account> --region us-east-1 networkmanager list-attachments --core-network-id <id>

# Policy (current + previous versions)
aws --profile <hub-account> --region us-east-1 networkmanager list-core-network-policy-versions --core-network-id <id>
aws --profile <hub-account> --region us-east-1 networkmanager get-core-network-policy --core-network-id <id> --alias LIVE

# Routes (per segment per edge location)
aws --profile <hub-account> --region us-east-1 networkmanager get-network-routes \
    --global-network-id <id> --route-table-identifier 'CoreNetworkSegmentEdge={CoreNetworkId=<id>,SegmentName=Production,EdgeLocation=us-east-1}'

# Telemetry events
aws --profile <hub-account> --region us-east-1 networkmanager get-network-telemetry --global-network-id <id>
```

Cloud WAN itself doesn't have CloudWatch metrics like TGW — visibility is via:
- Attachment state (`AVAILABLE` / `PENDING_ATTACHMENT_ACCEPTANCE` / `REJECTED` / `FAILED`)
- Per-attachment TGW metrics (when type=TGW)
- VPC Flow Logs on attached VPCs
- Network Manager events

## Step 7 — Site-to-Site VPN metrics

Namespace `AWS/VPN`, dimensions `VpnId` + `TunnelIpAddress`:

| Metric | Use |
|---|---|
| `TunnelState` | 0=DOWN, 1=UP — both tunnels per VPN |
| `TunnelDataIn` / `TunnelDataOut` | Throughput (Sum bytes per period) |

Each VPN has 2 tunnels — both should ideally be UP for redundancy.

## Pitfalls

1. **`aws sso login` defaults to PKCE with localhost callback** — useless on headless boxes. Always use `--use-device-code`. The CLI even hints this in its output: "If you are unable to open the URL on this device, run this command again with the '--use-device-code' option."

2. **`/tmp` mounted noexec on Rocky 9** — `sudo /tmp/aws/install` fails with "Permission denied". Use `sudo bash /tmp/aws/install` to bypass.

3. **DX hosted vs standalone metrics**: connection-level Bps metrics are MISSING for hosted DXes (Megaport, Equinix sub-tenants). You'll see `ConnectionState=1` but `ConnectionBpsEgress` returns 0 datapoints. Query VIF-level metrics with BOTH `ConnectionId` AND `VirtualInterfaceId` dimensions instead.

4. **Same TGW appears in multiple profiles via RAM share** — querying each account-region combination produces duplicates. Always deduplicate by `TransitGatewayId` before reporting. Same for SSO `list-accounts` results — paginate but watch for max-results=100 implicit cap.

5. **`networkmanager list-core-networks` is global-ish** — same core network appears identically when queried from any region. Don't multiply count.

6. **Bash subshells lose `first=0` state** — `while read … done < <(...)` runs in a subshell. If you build JSON arrays incrementally with `[[ $first -eq 0 ]] && echo ","`, the comma logic breaks because state doesn't propagate back. Use `mapfile`, named pipes, or build the array in Python/jq instead.

7. **`networkmanager` API is in `us-east-1` only for some operations** — `list-core-networks` works in any region but returns the same result. Stick to `us-east-1` for consistency.

8. **CloudWatch period must be ≥ 60s** and at least 60-300s for `get-metric-statistics` not to return empty. Use 3600 (1h buckets) for 24h reports.

9. **Role priority:** corp has `AWSNetworkAdministratorV2` in 95/100 accounts. Some sandbox/billing-only accounts have only `AWSBilling` — those won't allow describe-* calls. Skip them gracefully.

10. **`aws configure sso` interactive flow** asks for register-scopes, region, etc. If you write `~/.aws/config` directly, only need `[sso-session <name>]` block + per-profile `sso_session = <name>`, `sso_account_id`, `sso_role_name`.

11. **Subprocess timeout** — when querying 50+ accounts × 3 regions in parallel, set per-call `timeout=20` and retry transient throttling. AWS STS limit per region is high but per-account assume-role can throttle.

12. **`AWS_API_MCP_PROFILE_NAME` is the env var the AWS API MCP Server reads** — not `AWS_PROFILE`. Set both for safety.

## Consuming inventory.py from external scripts

The `scripts/inventory.py` here writes to a **file** (via `--out PATH`), not stdout. Same convention as `gcp-network-monitoring`. The Megaport equivalent uses `--json` for stdout — different convention across the 4 cloud monitoring skills.

```bash
local outfile=$(mktemp --suffix=.json)
python3 inventory.py --out "$outfile" >&2
cat "$outfile"
```

Output shape: `{results: [{profile, region, dx, tgw, vpn, cwan}, ...]}` — one entry per `(profile, region)` combination. Counts (`dx`, `tgw`, etc.) may be either an int or a dict `{count: N, ...}` depending on whether `dx_details` was collected — handle both shapes when parsing.

## Reference scripts (this skill ships them)

- `scripts/setup_profiles.py` — auto-generate ~/.aws/config from SSO list-accounts
- `scripts/inventory.py` — cross-account inventory of DX/TGW/VPN/CloudWAN
- `scripts/dx_report.py` — DX 24h utilization + VIF metrics (handles hosted vs standalone)
- `scripts/tgw_report.py` — TGW 24h throughput + drop counts, dedup by TGW id
- `scripts/cwan_audit.sh` — CloudWAN attachments + segments audit

## Investigation references

- `references/tgw-noroute-drops-investigation.md` — full playbook for `PacketDropCountNoRoute > 0` debugging: blackhole-vs-noroute split, RT topology dump, source→destination matrix, Flow Log health checks (catches the `DeliverLogsStatus=FAILED` trap), Connect BGP HA verification, common root-cause patterns. Use this whenever a TGW shows non-zero NoRoute drops.

## Operational notes — known patterns

### Rollback drop spikes are benign
corp's network is migrating from a TGW-based mesh to **CloudWAN**. Several VPCs are dual-attached during the migration. When a rollback happens (CloudWAN → legacy TGW path) for a VPC whose old TGW attachment doesn't propagate to the right RTs anymore, you'll see a **discrete 1-hour spike of NoRoute drops** on the legacy TGW, then it goes silent again when the rollback is reversed.

**Signature of a rollback drop spike (NOT an incident):**
- Concentrated in 1 hour (not continuous)
- Pure `PacketDropCountNoRoute`, zero `Blackhole`
- Small packet size (~80-100 B/packet) → TCP SYN/RST retransmission storms
- Affected TGW is otherwise idle or near-idle
- The VPC behind the drops is dual-attached (TGW + CloudWAN) — confirm via `networkmanager list-attachments` in the CloudWAN account

**Before raising an incident**, always:
1. Check if the affected VPC has a CloudWAN attachment (account `network-production-4588`, core network `core-network-0a607a0921ccdc3ae`).
2. Ask the network team if there was a rollback in that window.
3. Only escalate if drops are continuous OR the VPC is NOT in CloudWAN.

Confirmed rollback example (May 2026): `tgw-0ccee636f9eb1f1cd` (rsfn-useast1-production-transit-gateway) showed 53,691 NoRoute drops at 02:49Z. The VPC `rsfn-production` (10.30.0.0/16) was rolled back from CloudWAN segment `ProductionIsolated` to the legacy TGW path for ~1h, then reverted. **No action needed for this pattern.**

## corp topology snapshot (May 2026)

### Direct Connect (18 connections)
- **corp-network-prod (8 DX):** 4 in sa-east-1 (EQX-RJ2, AST-SP4-TVT, AST-SP4-EQX), 2 in us-east-1 (Megaport DR-ATL13), 2 in us-east-2 (Megaport EQX-CH4/CORESITE-CHI)
- **rsfn-network (8 DX):** redundancy for RSFN (SPB), all sa-east-1 (4 production + 4 backup)
- **network-production-4588 (2 DX):** QTS Atlanta (us-east-1), QTS Chicago (us-east-2) — these have classic connection-level metrics

### Transit Gateways (25 unique)
- **Top by throughput:** `TGW_EAST-US-1_CORP-CSP_PARTNERS` (22 TB/24h), `TGW_EAST-US-1_SPOKE_VPC-FW-NEW` (7.9 TB), `tgw-banking-hub` (7.7 TB)

### Cloud WAN
- 1 core network: `core-network-0a607a0921ccdc3ae` ("Cloud WAN corp")
- Edges: `us-east-1`, `us-east-2`
- 16 segments: Production, Staging, ProductionPCI, ProductionPCIEgressOnly, ProductionIsolated, StagingIsolated, SharedTools, SharedServicesProduction, SharedServicesStaging, SharedIsolated, SecurityProduction, SecurityStaging, TransitNetworks, TransitNetworksRSFN, PartnersProduction, PartnersStaging
- 106 attachments (100 VPC + 6 TGW Route Tables) — 92 in us-east-1, 14 in us-east-2
