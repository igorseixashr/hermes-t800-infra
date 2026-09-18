#!/usr/bin/env python3
"""Org-wide GCP network inventory via Cloud Asset Inventory.

Discovers Interconnects, Cloud Routers, VPN Gateways/Tunnels across ALL projects
in a GCP Organization in one shot (no per-project loop).

Usage:
  python3 inventory.py [--org 1053327236318] [--out /tmp/gcp_inv.json]
"""
import json, subprocess, os, argparse, sys
from collections import defaultdict

def run(cmd):
    env = {**os.environ}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        print(f"ERR ({r.returncode}): {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        return json.loads(r.stdout) if r.stdout.strip() else []
    except json.JSONDecodeError as e:
        print(f"JSON parse err: {e}", file=sys.stderr)
        return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--org', default='1053327236318', help='Organization ID')
    ap.add_argument('--out', default='/tmp/gcp_network_inventory.json')
    args = ap.parse_args()

    print(f"Scanning org {args.org}...")
    interconnects = run(['gcloud','asset','search-all-resources',
                         f'--scope=organizations/{args.org}',
                         '--asset-types=compute.googleapis.com/Interconnect,compute.googleapis.com/InterconnectAttachment',
                         '--page-size=500','--format=json'])
    routers = run(['gcloud','asset','search-all-resources',
                   f'--scope=organizations/{args.org}',
                   '--asset-types=compute.googleapis.com/Router',
                   '--page-size=500','--format=json'])
    vpns = run(['gcloud','asset','search-all-resources',
                f'--scope=organizations/{args.org}',
                '--asset-types=compute.googleapis.com/VpnGateway,compute.googleapis.com/TargetVpnGateway,compute.googleapis.com/VpnTunnel',
                '--page-size=500','--format=json'])

    print(f"\n=== Interconnects + Attachments ({len(interconnects)}) ===")
    by_proj_ic = defaultdict(lambda: {'ic':[], 'att':[]})
    for a in interconnects:
        proj = a.get('parentFullResourceName','').replace('//cloudresourcemanager.googleapis.com/projects/','')
        if 'Interconnect' == a['assetType'].split('/')[-1]:
            by_proj_ic[proj]['ic'].append(a)
        else:
            by_proj_ic[proj]['att'].append(a)
    for proj, it in by_proj_ic.items():
        print(f"  {proj}: {len(it['ic'])} interconnects, {len(it['att'])} attachments")
        for x in it['ic'][:3]: print(f"    IC: {x['name'].split('/')[-1]}")
        for x in it['att'][:5]: print(f"    AT: [{x.get('location','?')}] {x['name'].split('/')[-1]}")
        if len(it['att']) > 5: print(f"    ... +{len(it['att'])-5} more attachments")

    print(f"\n=== Cloud Routers ({len(routers)}) ===")
    by_proj_r = defaultdict(list)
    for r in routers:
        proj = r.get('parentFullResourceName','').replace('//cloudresourcemanager.googleapis.com/projects/','')
        by_proj_r[proj].append(r)
    for proj, items in sorted(by_proj_r.items(), key=lambda x: -len(x[1])):
        print(f"  {proj}: {len(items)} routers")

    print(f"\n=== VPN Resources ({len(vpns)}) ===")
    by_proj_v = defaultdict(lambda: defaultdict(int))
    for v in vpns:
        proj = v.get('parentFullResourceName','').replace('//cloudresourcemanager.googleapis.com/projects/','')
        by_proj_v[proj][v['assetType'].split('/')[-1]] += 1
    for proj, counts in by_proj_v.items():
        print(f"  {proj}: {dict(counts)}")

    out = {'interconnects': interconnects, 'routers': routers, 'vpns': vpns}
    json.dump(out, open(args.out,'w'), indent=2, default=str)
    print(f"\n✓ Saved {args.out}")

if __name__ == '__main__':
    main()
