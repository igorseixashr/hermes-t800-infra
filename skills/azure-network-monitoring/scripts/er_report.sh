#!/usr/bin/env bash
# 24h ExpressRoute health & occupation report — ALL circuits in the tenant.
# Output: JSON aggregating circuit info + Azure Monitor metrics.
# Usage: bash er_report.sh [hours_back]   # default: 24
set -uo pipefail
HOURS=${1:-24}
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
START=$(date -u -d "${HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)
OUT=${OUT:-/tmp/azreport/er_metrics.json}
mkdir -p "$(dirname "$OUT")"

# Discover all circuits cross-subscription
CIRCUITS=$(az graph query -q "Resources
  | where type =~ 'Microsoft.Network/expressRouteCircuits'
  | project id, name, subscriptionId, resourceGroup, location" \
  --first 1000 -o json | jq -c '.data[]')

echo "[" > "$OUT"
first=1
echo "$CIRCUITS" | while IFS= read -r line; do
  ID=$(echo "$line" | jq -r '.id')
  NAME=$(echo "$line" | jq -r '.name')
  echo "  → $NAME" >&2

  INFO=$(az network express-route show --ids "$ID" -o json 2>/dev/null)

  METRICS=$(az monitor metrics list \
    --resource "$ID" \
    --metrics BitsInPerSecond BitsOutPerSecond ArpAvailability BgpAvailability \
              QosDropBitsInPerSecond QosDropBitsOutPerSecond \
    --start-time "$START" --end-time "$END" \
    --interval PT1H \
    --aggregation Average Maximum \
    -o json 2>/dev/null || echo '{}')

  [[ $first -eq 0 ]] && echo "," >> "$OUT"
  first=0
  jq -n --arg name "$NAME" --argjson info "$INFO" --argjson m "$METRICS" \
    '{circuit: $name, info: $info, metrics: $m}' >> "$OUT"
done
echo "]" >> "$OUT"
echo "✓ ExpressRoute report: $OUT ($(wc -c < $OUT) bytes) | window: $START → $END" >&2
