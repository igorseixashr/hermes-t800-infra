#!/usr/bin/env bash
# VPN tunnel + gateway audit across multiple GCP projects.
# Reports any tunnel that is NOT in ESTABLISHED state.
set -uo pipefail
PROJECTS="${@:-tau-rex stg-tau-rex keycloak-prd keycloak-nonprd transit-network-228018}"

echo "=== VPN audit across projects: $PROJECTS ==="
echo

TOTAL_TUNNELS=0
BAD_TUNNELS=0

for PROJ in $PROJECTS; do
  echo "--- Project: $PROJ ---"

  # HA VPN gateways
  HA=$(gcloud compute vpn-gateways list --project="$PROJ" --format='value(name,region.basename(),network.basename())' 2>/dev/null)
  if [ -n "$HA" ]; then
    echo "  HA VPN Gateways:"
    while IFS=$'\t' read -r NAME REGION NET; do
      [ -z "$NAME" ] && continue
      echo "    [$REGION] $NAME (network: $NET)"
    done <<< "$HA"
  fi

  # Classic VPN gateways
  CL=$(gcloud compute target-vpn-gateways list --project="$PROJ" --format='value(name,region.basename(),network.basename())' 2>/dev/null)
  if [ -n "$CL" ]; then
    echo "  Classic VPN Gateways:"
    while IFS=$'\t' read -r NAME REGION NET; do
      [ -z "$NAME" ] && continue
      echo "    [$REGION] $NAME (network: $NET)"
    done <<< "$CL"
  fi

  # Tunnels
  TNS=$(gcloud compute vpn-tunnels list --project="$PROJ" --format='value(name,region.basename(),status,peerIp,detailedStatus)' 2>/dev/null)
  if [ -n "$TNS" ]; then
    echo "  Tunnels:"
    while IFS=$'\t' read -r NAME REGION STATUS PEER DETAIL; do
      [ -z "$NAME" ] && continue
      TOTAL_TUNNELS=$((TOTAL_TUNNELS + 1))
      if [ "$STATUS" = "ESTABLISHED" ]; then
        ICON="🟢"
      else
        ICON="🔴"
        BAD_TUNNELS=$((BAD_TUNNELS + 1))
      fi
      printf "    %s [%s] %-35s status=%-22s peer=%-18s\n" "$ICON" "$REGION" "${NAME:0:35}" "$STATUS" "$PEER"
      [ "$STATUS" != "ESTABLISHED" ] && [ -n "$DETAIL" ] && echo "        └─ $DETAIL"
    done <<< "$TNS"
  fi
  echo
done

echo "=== Summary ==="
echo "  Total tunnels: $TOTAL_TUNNELS"
echo "  Not ESTABLISHED: $BAD_TUNNELS"
[ "$BAD_TUNNELS" -gt 0 ] && echo "  ⚠️  Investigation needed for non-established tunnels above"
