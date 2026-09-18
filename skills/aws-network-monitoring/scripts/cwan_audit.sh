#!/usr/bin/env bash
# Cloud WAN audit — segments, attachments, edges, policy.
# Default: corp's core network. Override with env vars CWAN_PROFILE / CWAN_CORE_ID / CWAN_GLOBAL_ID
set -uo pipefail
PROFILE="${CWAN_PROFILE:-network-production-4588}"
REGION="${CWAN_REGION:-us-east-1}"
CORE_ID="${CWAN_CORE_ID:-core-network-0a607a0921ccdc3ae}"
GLOBAL_ID="${CWAN_GLOBAL_ID:-global-network-004ecef77378d7c81}"
OUT_DIR="${OUT_DIR:-/tmp/azreport}"
mkdir -p "$OUT_DIR"

echo "=== Cloud WAN Audit ==="
echo "Core: $CORE_ID  |  Global: $GLOBAL_ID"
echo

# Core network detail (segments + edges)
aws --profile "$PROFILE" --region "$REGION" networkmanager get-core-network \
    --core-network-id "$CORE_ID" --output json > "$OUT_DIR/cwan_core.json"
echo "Edges:"
jq -r '.CoreNetwork.Edges[] | "  - \(.EdgeLocation) (ASN \(.Asn // "?"))"' "$OUT_DIR/cwan_core.json"
echo
echo "Segments (\(jq '.CoreNetwork.Segments | length' "$OUT_DIR/cwan_core.json") total):"
jq -r '.CoreNetwork.Segments[] | "  - \(.Name)\n      edges: \(.EdgeLocations | join(", "))\n      shared: \(.SharedSegments | join(", "))"' "$OUT_DIR/cwan_core.json"
echo

# Attachments
aws --profile "$PROFILE" --region "$REGION" networkmanager list-attachments \
    --core-network-id "$CORE_ID" --output json > "$OUT_DIR/cwan_attachments.json"
TOTAL=$(jq '.Attachments | length' "$OUT_DIR/cwan_attachments.json")
echo "Attachments: $TOTAL total"
jq -r '.Attachments | group_by(.AttachmentType) | .[] | "  by type: \(.[0].AttachmentType) → \(length)"' "$OUT_DIR/cwan_attachments.json"
jq -r '.Attachments | group_by(.State) | .[] | "  by state: \(.[0].State) → \(length)"' "$OUT_DIR/cwan_attachments.json"
jq -r '.Attachments | group_by(.EdgeLocation) | .[] | "  by edge:  \(.[0].EdgeLocation // "(none)") → \(length)"' "$OUT_DIR/cwan_attachments.json"
echo
echo "Top segments by attachment count:"
jq -r '.Attachments | group_by(.SegmentName) | sort_by(-length) | .[] | "  \(.[0].SegmentName // "(none)"): \(length)"' "$OUT_DIR/cwan_attachments.json" | head -10
echo

# Non-AVAILABLE attachments are red flags
echo "⚠️  Attachments NOT in AVAILABLE state:"
jq -r '.Attachments[] | select(.State != "AVAILABLE") | "  [\(.State)] \(.AttachmentType) \(.AttachmentId) edge=\(.EdgeLocation // "?") seg=\(.SegmentName // "?")"' "$OUT_DIR/cwan_attachments.json"

# Policy
aws --profile "$PROFILE" --region "$REGION" networkmanager get-core-network-policy \
    --core-network-id "$CORE_ID" --alias LIVE --output json > "$OUT_DIR/cwan_policy.json" 2>/dev/null
echo
echo "Policy version:"
jq -r '.CoreNetworkPolicy | "  version: \(.PolicyVersionId)  alias: \(.Alias)  changedAt: \(.ChangeSetState // "n/a")"' "$OUT_DIR/cwan_policy.json"

echo
echo "✓ Saved to $OUT_DIR/{cwan_core,cwan_attachments,cwan_policy}.json"
