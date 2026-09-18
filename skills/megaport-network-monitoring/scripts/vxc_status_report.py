#!/usr/bin/env python3
"""Megaport — VXC status report with BGP state and cloud-side correlation.

For every VXC in the tenant, fetches /v2/product/{uid} to get the full
csp_connection (including BGP status and cloud identifiers), then prints:
- VXC name, rate limit, contract end date
- A-End / B-End locations and connectType
- BGP peers + status (1=UP, 0=DOWN)
- Cloud-side identifier (AWS connectionId, Azure service_key, GCP pairingKey)

Usage:
    python3 vxc_status_report.py                  # table for all VXCs
    python3 vxc_status_report.py --cloud AWS      # filter by cloud
    python3 vxc_status_report.py --only-issues    # only show DOWN / BGP issues
    python3 vxc_status_report.py --json
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _megaport_client import (
    MegaportClient,
    bgp_status_from_csp,
    collect_all_vxcs,
    csp_identifier,
    vxc_cloud_provider,
)


def ms_to_date(ms: int | None) -> str:
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", help="filter by cloud (AWS, Azure, GCP, Internet/ISP, MCR (private), Port-to-Port)")
    ap.add_argument("--only-issues", action="store_true",
                    help="only show VXCs that are not LIVE/up or have BGP peers down")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cli = MegaportClient()
    inv = cli.get("/v2/products")
    if inv is None:
        return 1
    vxcs = collect_all_vxcs(inv.get("data", []))

    results = []
    for uid, v in vxcs.items():
        cloud = vxc_cloud_provider(v)
        if args.cloud and cloud != args.cloud:
            continue

        # Fetch detail for the full csp_connection (the list-view shape is collapsed)
        detail = cli.get(f"/v2/product/{uid}")
        d = detail.get("data") if detail else {}
        csp = (d.get("resources") or {}).get("csp_connection") if d else None
        bgp = bgp_status_from_csp(csp)
        ident = csp_identifier(csp)

        issue = (
            not v.get("up")
            or v.get("provisioningStatus") != "LIVE"
            or any(state != 1 for state in bgp.values())
        )
        if args.only_issues and not issue:
            continue

        results.append({
            "productUid": uid,
            "productName": v["productName"],
            "rateLimit_Mbps": v.get("rateLimit"),
            "maximumRate_Mbps": v.get("maximumRate"),
            "provisioningStatus": v.get("provisioningStatus"),
            "up": v.get("up"),
            "shutdown": v.get("shutdown"),
            "contractEndDate": ms_to_date(v.get("contractEndDate")),
            "aEnd": {
                "name": v["aEnd"]["productName"],
                "location": v["aEnd"]["location"],
                "connectType": v["aEnd"]["connectType"],
                "vlan": v["aEnd"].get("vlan"),
                "diversityZone": v["aEnd"].get("diversityZone"),
            },
            "bEnd": {
                "name": v["bEnd"]["productName"],
                "location": v["bEnd"]["location"],
                "connectType": v["bEnd"]["connectType"],
                "vlan": v["bEnd"].get("vlan"),
                "diversityZone": v["bEnd"].get("diversityZone"),
            },
            "cloud": cloud,
            "bgp_status": bgp,
            "csp_identifiers": ident,
            "issue": issue,
        })

        # be polite to the API
        time.sleep(0.05)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    # ---------- human table ----------
    print("=" * 130)
    print(f"VXC STATUS REPORT  ({len(results)} VXCs)" + (f"  filter cloud={args.cloud}" if args.cloud else ""))
    print("=" * 130)

    for r in sorted(results, key=lambda x: (x["cloud"], x["productName"])):
        flag = "🔴" if r["issue"] else "🟢"
        bgp_summary = ", ".join(f"{ip}={'UP' if s == 1 else 'DOWN'}" for ip, s in r["bgp_status"].items()) or "-"
        print(f"\n{flag} {r['productName']}  ({r['cloud']})  uid={r['productUid']}")
        print(f"     {r['aEnd']['location']:<32} [{r['aEnd']['connectType']:<8}] "
              f"vlan={r['aEnd']['vlan']} zone={r['aEnd']['diversityZone'] or '-'}")
        print(f"  →  {r['bEnd']['location']:<32} [{r['bEnd']['connectType']:<8}] "
              f"vlan={r['bEnd']['vlan']} zone={r['bEnd']['diversityZone'] or '-'}")
        print(f"     rate={r['rateLimit_Mbps']} Mbps  status={r['provisioningStatus']}  up={r['up']}  "
              f"contract_ends={r['contractEndDate']}")
        print(f"     BGP: {bgp_summary}")
        if r["csp_identifiers"]:
            keys = {k: v for k, v in r["csp_identifiers"].items() if k != "provider"}
            if keys:
                print(f"     Cloud ID: {keys}")

    # Summary
    issues = [r for r in results if r["issue"]]
    inspected = len(vxcs) if not args.cloud else sum(1 for v in vxcs.values() if vxc_cloud_provider(v) == args.cloud)
    print("\n" + "=" * 130)
    if args.only_issues:
        print(f"VXCs inspecionadas: {inspected}   listadas (com problema): {len(results)}")
    else:
        print(f"Total VXCs analisadas: {len(results)}   com problemas: {len(issues)}")
    if issues:
        print("🔴 Investigar:")
        for r in issues:
            why = []
            if not r["up"]:
                why.append("up=False")
            if r["provisioningStatus"] != "LIVE":
                why.append(f"status={r['provisioningStatus']}")
            bgp_down = [ip for ip, s in r["bgp_status"].items() if s != 1]
            if bgp_down:
                why.append(f"BGP DOWN: {bgp_down}")
            print(f"  - {r['productName']}: {', '.join(why)}")
    else:
        print("✅ Todas as VXCs LIVE, up, com BGP estabelecido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
