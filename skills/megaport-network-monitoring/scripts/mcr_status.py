#!/usr/bin/env python3
"""Megaport — MCR status report.

For each Megaport Cloud Router (MCR2), reports:
- ASN, port speed, diversity zone, location
- Number of attached VXCs (and their cloud destinations)
- IPsec tunnel count and max limit (v3 endpoint)
- Overall up flag and provisioning status

Usage:
    python3 mcr_status.py
    python3 mcr_status.py --json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _megaport_client import MegaportClient, vxc_cloud_provider


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cli = MegaportClient()
    inv = cli.get("/v2/products")
    if inv is None:
        return 1

    mcrs = [p for p in inv.get("data", []) if p["productType"] == "MCR2"]

    report = []
    for m in sorted(mcrs, key=lambda x: x["productName"]):
        uid = m["productUid"]
        # MCR config detail (gives mcrAsn from resources.virtual_router)
        detail = cli.get(f"/v2/product/{uid}")
        d = (detail or {}).get("data", {}) or {}
        vrouter = (d.get("resources") or {}).get("virtual_router", {}) or {}
        # IPsec tunnels
        ipsec = cli.get(f"/v3/products/mcrs/{uid}/ipsec")
        ipsec_data = (ipsec or {}).get("data", {}) or {}

        # Per-cloud VXC count
        vxc_clouds = Counter(vxc_cloud_provider(v) for v in (m.get("associatedVxcs") or []))

        entry = {
            "productUid": uid,
            "productName": m["productName"],
            "location": (m.get("locationDetail") or {}).get("name"),
            "diversityZone": m.get("diversityZone"),
            "asn": vrouter.get("mcrAsn"),
            "portSpeed_Mbps": m.get("portSpeed"),
            "vrouter_up": vrouter.get("up"),
            "vrouter_bgp_shutdown_default": vrouter.get("bgpShutdownDefault"),
            "provisioningStatus": m.get("provisioningStatus"),
            "up": m.get("up"),
            "vxc_count": len(m.get("associatedVxcs") or []),
            "vxc_by_cloud": dict(vxc_clouds),
            "ipsec_tunnels_active": ipsec_data.get("totalTunnelCount"),
            "ipsec_tunnels_max": ipsec_data.get("maxTunnelCountLimit"),
        }
        report.append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 110)
    print(f"MCR STATUS REPORT  ({len(report)} MCRs)")
    print("=" * 110)
    for r in report:
        flag = "🟢" if r["up"] and r["vrouter_up"] else "🔴"
        print(f"\n{flag} {r['productName']}  ({r['location']})  zone={r['diversityZone']}")
        print(f"     ASN={r['asn']}  port={r['portSpeed_Mbps']/1000:.1f}G  "
              f"status={r['provisioningStatus']}  up={r['up']}  vrouter_up={r['vrouter_up']}  "
              f"bgp_default_shutdown={r['vrouter_bgp_shutdown_default']}")
        print(f"     VXCs: {r['vxc_count']}  {r['vxc_by_cloud']}")
        if r["ipsec_tunnels_max"] is not None:
            print(f"     IPsec tunnels: {r['ipsec_tunnels_active']}/{r['ipsec_tunnels_max']}")
        print(f"     uid: {r['productUid']}")

    # ASN diversity check
    asns = [r["asn"] for r in report if r["asn"]]
    dup = [a for a, c in Counter(asns).items() if c > 1]
    print("\n" + "=" * 110)
    if dup:
        print(f"⚠️  ASN duplicado entre MCRs: {dup}  (revisar — pode causar BGP confusion)")
    else:
        print("✅ ASNs únicos entre MCRs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
