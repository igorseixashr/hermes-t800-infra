#!/usr/bin/env bash
# Audit network connections (ExpressRoute ↔ VNG links).
# Shows connection state and traffic counters per link.
set -uo pipefail
OUT=${OUT:-/tmp/azreport/connections_audit.json}
mkdir -p "$(dirname "$OUT")"

az graph query -q "Resources
  | where type =~ 'Microsoft.Network/connections'
  | project name, subscriptionId, resourceGroup, location,
            connType=tostring(properties.connectionType),
            connState=tostring(properties.connectionStatus),
            ingressBytes=tolong(properties.ingressBytesTransferred),
            egressBytes=tolong(properties.egressBytesTransferred),
            peerId=tostring(properties.peer.id),
            vngId=tostring(properties.virtualNetworkGateway1.id),
            tunnelConnectionStatus=tostring(properties.tunnelConnectionStatus)
  | order by connState, name" --first 1000 -o json > "$OUT"

echo "✓ Connections audit: $OUT" >&2
echo >&2
echo "Summary:" >&2
jq -r '.data | group_by(.connState) | .[] | "  \(.[0].connState): \(length)"' "$OUT" >&2
echo >&2
echo "Per-connection state:" >&2
jq -r '.data[] | "  [\(.connState)] \(.name) (\(.connType)) — in=\((.ingressBytes/1e9*100|round)/100)GB out=\((.egressBytes/1e9*100|round)/100)GB"' "$OUT" >&2
