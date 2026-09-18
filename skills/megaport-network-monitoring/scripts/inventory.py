#!/usr/bin/env python3
"""Megaport — full inventory snapshot.

Lists every Port, MCR, MVE, IX in the tenant plus a deduplicated count of VXCs.

Usage:
    python3 inventory.py                # human-readable table
    python3 inventory.py --json         # full JSON to stdout
    python3 inventory.py --save snap.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _megaport_client import MegaportClient, collect_all_vxcs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of table")
    ap.add_argument("--save", metavar="PATH", help="save raw API response to file")
    args = ap.parse_args()

    cli = MegaportClient()
    resp = cli.get("/v2/products")
    if resp is None:
        return 1

    products = resp.get("data", [])
    vxcs = collect_all_vxcs(products)

    if args.save:
        Path(args.save).write_text(json.dumps(resp, indent=2))
        sys.stderr.write(f"Saved raw response to {args.save}\n")

    if args.json:
        print(json.dumps(
            {
                "message": resp.get("message"),
                "products": products,
                "vxcs_unique": list(vxcs.values()),
            },
            indent=2,
        ))
        return 0

    # ---------- human table ----------
    type_counts = Counter(p["productType"] for p in products)
    status_counts = Counter(p["provisioningStatus"] for p in products)
    up_counts = Counter(p.get("up") for p in products)

    print("=" * 100)
    print(f"MEGAPORT INVENTORY  ({resp.get('message')})")
    print("=" * 100)
    print(f"Top-level products: {len(products)}  "
          f"types={dict(type_counts)}  status={dict(status_counts)}  up={dict(up_counts)}")
    print(f"VXCs (deduplicated): {len(vxcs)}")
    vxc_status = Counter(v.get("provisioningStatus") for v in vxcs.values())
    vxc_up = Counter(v.get("up") for v in vxcs.values())
    print(f"  VXC status={dict(vxc_status)}  up={dict(vxc_up)}")

    # Ports / MCRs / MVEs table
    print()
    print(f"{'Type':<8} {'Name':<46} {'Location':<32} {'Zone':<6} {'Speed':>7} {'VXCs':>5} {'Status':<8} {'Up'}")
    print("-" * 120)
    for p in sorted(products, key=lambda x: (x["productType"], x["productName"])):
        loc = (p.get("locationDetail") or {}).get("name", str(p.get("locationId", "?")))
        speed = p.get("portSpeed", 0)
        speed_str = f"{speed/1000:.0f}G" if speed >= 1000 else f"{speed}M"
        print(f"{p['productType']:<8} {p['productName'][:45]:<46} {loc[:31]:<32} "
              f"{str(p.get('diversityZone') or '-'):<6} {speed_str:>7} "
              f"{len(p.get('associatedVxcs') or []):>5} "
              f"{p['provisioningStatus']:<8} {p.get('up')}")

    # VXCs by cloud provider
    from _megaport_client import vxc_cloud_provider
    by_cloud = Counter(vxc_cloud_provider(v) for v in vxcs.values())
    print()
    print(f"VXCs por destino:")
    for cloud, n in sorted(by_cloud.items(), key=lambda x: -x[1]):
        print(f"  {cloud:<20} {n}")

    # Anomalies
    down = [p for p in products if not p.get("up")]
    down_vxc = [v for v in vxcs.values() if not v.get("up")]
    not_live = [p for p in products if p["provisioningStatus"] != "LIVE"]
    not_live_vxc = [v for v in vxcs.values() if v.get("provisioningStatus") != "LIVE"]

    print()
    if down or down_vxc or not_live or not_live_vxc:
        print("🔴 ALERTS:")
        for p in down:
            print(f"  PORT/MCR DOWN: {p['productName']}  (up={p.get('up')})")
        for v in down_vxc:
            print(f"  VXC DOWN: {v['productName']}  ({v['aEnd']['location']} → {v['bEnd']['location']})")
        for p in not_live:
            print(f"  Not LIVE: {p['productName']} -> {p['provisioningStatus']}")
        for v in not_live_vxc:
            print(f"  VXC not LIVE: {v['productName']} -> {v['provisioningStatus']}")
    else:
        print("✅ Tudo LIVE e up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
