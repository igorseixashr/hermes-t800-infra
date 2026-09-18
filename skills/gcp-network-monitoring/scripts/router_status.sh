#!/usr/bin/env bash
# BGP peer runtime status across all Cloud Routers in a project.
# Default: transit-network-228018. Override via env or arg.
set -uo pipefail
PROJECT="${1:-${GCP_PROJECT:-transit-network-228018}}"

ROUTERS=$(gcloud compute routers list --project="$PROJECT" --format='value(name,region.basename())')

while IFS=$'\t' read -r NAME REGION; do
  [ -z "$NAME" ] && continue
  echo "━━━ [$REGION] $NAME ━━━"
  gcloud compute routers get-status "$NAME" --project="$PROJECT" --region="$REGION" --format=json 2>/dev/null | \
    python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    peers = d.get('result', {}).get('bgpPeerStatus', [])
    if not peers:
        print('  (no BGP peers)')
    for p in peers:
        st = p.get('status','?')
        icon = '🟢' if st == 'UP' else '🔴'
        name = p.get('name','?')
        ip = p.get('ipAddress','?')
        peer_ip = p.get('peerIpAddress','?')
        learned = p.get('numLearnedRoutes','?')
        uptime = p.get('uptime','?')
        link = p.get('linkedInterconnectAttachment') or p.get('linkedVpnTunnel') or 'unknown'
        link_short = (link or '').split('/')[-1] if link else '?'
        print(f'  {icon} {name[:50]:<52} state={st:<6} {ip:<22} ↔ {peer_ip:<22} learned={learned:<3} uptime={uptime}')
        print(f'      via: {link_short}')
except Exception as e:
    print(f'  ERR: {e}')
"
  echo
done <<< "$ROUTERS"
