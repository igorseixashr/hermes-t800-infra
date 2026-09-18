#!/usr/bin/env python3
"""Megaport — cross-cloud correlation report.

For every VXC that lands on AWS, Azure, or GCP, prints the cloud-side
identifier so you can pivot directly to the corresponding resource on the
other provider's side.

This script DOES NOT call AWS/Azure/GCP — it only emits the keys you need
to query them. To enrich with cloud-side state, pipe `--json` output through
the matching cloud-network-monitoring skill.

Output columns:
- Megaport: VXC name, MCR/Port, rate, status
- Provider: AWS / Azure / GCP
- Cloud-side ID: AWS connectionId+account / Azure service_key+vlan / GCP pairingKey

Usage:
    python3 correlate_cross_cloud.py
    python3 correlate_cross_cloud.py --json
    python3 correlate_cross_cloud.py --provider AWS
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _megaport_client import (
    MegaportClient,
    bgp_status_from_csp,
    collect_all_vxcs,
    csp_identifier,
    vxc_cloud_provider,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["AWS", "Azure", "GCP"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cli = MegaportClient()
    inv = cli.get("/v2/products")
    if inv is None:
        return 1
    vxcs = collect_all_vxcs(inv.get("data", []))

    rows = []
    for uid, v in vxcs.items():
        cloud = vxc_cloud_provider(v)
        if cloud not in ("AWS", "Azure", "GCP"):
            continue
        if args.provider and cloud != args.provider:
            continue

        detail = cli.get(f"/v2/product/{uid}")
        d = (detail or {}).get("data", {}) or {}
        csp = (d.get("resources") or {}).get("csp_connection")
        ident = csp_identifier(csp)
        bgp = bgp_status_from_csp(csp)
        bgp_up = sum(1 for s in bgp.values() if s == 1)
        bgp_total = len(bgp)

        rows.append({
            "vxc_uid": uid,
            "vxc_name": v["productName"],
            "mcr_or_port": v["_parent_name"],
            "rate_Mbps": v.get("rateLimit"),
            "up": v.get("up"),
            "status": v.get("provisioningStatus"),
            "aEnd_location": v["aEnd"]["location"],
            "bEnd_location": v["bEnd"]["location"],
            "diversity": v["aEnd"].get("diversityZone") or v["bEnd"].get("diversityZone"),
            "cloud_provider": cloud,
            "bgp": f"{bgp_up}/{bgp_total} up",
            **ident,
        })
        time.sleep(0.05)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print("=" * 140)
    print("CROSS-CLOUD CORRELATION REPORT  (Megaport VXC → cloud-side identifier)")
    print("=" * 140)

    by_cloud: dict[str, list] = {}
    for r in rows:
        by_cloud.setdefault(r["cloud_provider"], []).append(r)

    for cloud in ["AWS", "Azure", "GCP"]:
        items = by_cloud.get(cloud, [])
        if not items:
            continue
        print(f"\n### {cloud}  ({len(items)} VXCs)")
        print("-" * 140)
        for r in sorted(items, key=lambda x: x["vxc_name"]):
            flag = "🟢" if r["up"] else "🔴"
            print(f"{flag} {r['vxc_name']}")
            print(f"     parent={r['mcr_or_port']}  rate={r['rate_Mbps']} Mbps  "
                  f"path={r['aEnd_location']} → {r['bEnd_location']}  zone={r['diversity']}  bgp={r['bgp']}")
            if cloud == "AWS":
                acct = r.get("aws_account_id", "?")
                conn = r.get("aws_connection_id", "?")
                print(f"     AWS:   account={acct}  connectionId={conn}")
                print(f"     Query: aws --profile <acct-{acct}> directconnect describe-connections --connection-id {conn}")
            elif cloud == "Azure":
                key = r.get("azure_service_key", "?")
                vlan = r.get("azure_vlan", "?")
                print(f"     Azure: serviceKey={key}  vlan={vlan}")
                print(f"     Query: az network express-route list --query \"[?serviceKey=='{key}']\" -o json")
            elif cloud == "GCP":
                pk = r.get("gcp_pairing_key", "?")
                print(f"     GCP:   pairingKey={pk}")
                print(f"     Query: gcloud asset search-all-resources --scope=organizations/<ORG_ID> \\")
                print(f"              --asset-types=compute.googleapis.com/InterconnectAttachment \\")
                print(f"              --format=json | jq '.[] | select(.additionalAttributes.pairingKey == \"{pk}\")'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
