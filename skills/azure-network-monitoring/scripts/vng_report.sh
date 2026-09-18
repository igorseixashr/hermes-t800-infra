#!/usr/bin/env bash
# 24h Virtual Network Gateway (VNG) health report — ALL VNGs in the tenant.
# Auto-picks ExpressRoute vs VPN metrics by gateway type. Includes BGP peer status when enableBgp=true.
# Usage: bash vng_report.sh [hours_back]  # default: 24
set -uo pipefail
HOURS=${1:-24}
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
START=$(date -u -d "${HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)
OUT=${OUT:-/tmp/azreport/vng_health.json}
mkdir -p "$(dirname "$OUT")"

VNGS=$(az graph query -q "Resources
  | where type =~ 'Microsoft.Network/virtualNetworkGateways'
  | project id, name, subscriptionId, resourceGroup, location,
            gwType=tostring(properties.gatewayType),
            sku=tostring(properties.sku.name),
            enableBgp=tobool(properties.enableBgp),
            provisioningState=tostring(properties.provisioningState)" \
  --first 1000 -o json | jq -c '.data[]')

echo "[" > "$OUT"
first=1
echo "$VNGS" | while IFS= read -r line; do
  ID=$(echo "$line" | jq -r '.id')
  NAME=$(echo "$line" | jq -r '.name')
  GTYPE=$(echo "$line" | jq -r '.gwType')
  BGP_EN=$(echo "$line" | jq -r '.enableBgp')
  echo "  → $NAME [$GTYPE]" >&2

  BGP_STATUS="null"
  if [[ "$BGP_EN" == "true" ]]; then
    BGP_STATUS=$(az network vnet-gateway list-bgp-peer-status --ids "$ID" -o json 2>/dev/null || echo "null")
  fi

  if [[ "$GTYPE" == "ExpressRoute" ]]; then
    METRIC_NAMES="ExpressRouteGatewayCpuUtilization ExpressRouteGatewayBitsPerSecond \
                  ExpressRouteGatewayPacketsPerSecond \
                  ExpressRouteGatewayCountOfRoutesAdvertisedToPeer \
                  ExpressRouteGatewayCountOfRoutesLearnedFromPeer"
  else
    METRIC_NAMES="TunnelAverageBandwidth TunnelEgressBytes TunnelIngressBytes \
                  TunnelIngressPacketDropCount TunnelEgressPacketDropCount AverageBandwidth"
  fi

  METRICS=$(az monitor metrics list --resource "$ID" \
    --metrics $METRIC_NAMES \
    --start-time "$START" --end-time "$END" \
    --interval PT1H --aggregation Average Maximum \
    -o json 2>/dev/null || echo '{}')

  [[ $first -eq 0 ]] && echo "," >> "$OUT"
  first=0
  jq -n --argjson info "$line" --argjson bgp "$BGP_STATUS" --argjson m "$METRICS" \
    '{info: $info, bgp: $bgp, metrics: $m}' >> "$OUT"
done
echo "]" >> "$OUT"
echo "✓ VNG report: $OUT ($(wc -c < $OUT) bytes) | window: $START → $END" >&2
