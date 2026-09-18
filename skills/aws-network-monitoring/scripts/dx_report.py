#!/usr/bin/env python3
"""24h Direct Connect utilization & health report — ALL connections cross-account.

Handles both standalone (connection-level metrics) and hosted (VIF-level metrics) DXes.
Run AFTER inventory.py to discover which accounts have DX.

Usage:
  python3 dx_report.py [--accounts a,b] [--regions r1,r2] [--hours 24]
"""
import json, subprocess, os, argparse, re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

DEFAULT = [
    ('corp-network-prod', 'sa-east-1'),
    ('corp-network-prod', 'us-east-1'),
    ('corp-network-prod', 'us-east-2'),
    ('rsfn-network',       'sa-east-1'),
    ('network-production-4588', 'us-east-1'),
    ('network-production-4588', 'us-east-2'),
]

def parse_bw(s):
    if not s: return 0
    s = s.lower().strip()
    if 'gbps' in s: return float(re.sub(r'[^0-9.]', '', s)) * 1e9
    if 'mbps' in s: return float(re.sub(r'[^0-9.]', '', s)) * 1e6
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=int, default=24)
    ap.add_argument('--out', default='/tmp/azreport/aws_dx_final.json')
    args = ap.parse_args()

    end = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    start = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
    env = {**os.environ, 'AWS_PAGER': ''}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # Discover DXes + VIFs in target accounts
    all_vifs = []
    all_conns = {}
    for profile, region in DEFAULT:
        r = subprocess.run(['aws', '--profile', profile, '--region', region,
                           'directconnect', 'describe-connections', '--output', 'json'],
                          capture_output=True, text=True, env=env)
        if r.returncode != 0: continue
        for c in json.loads(r.stdout).get('connections', []):
            c['_profile'] = profile; c['_region'] = region
            all_conns[c['connectionId']] = c

        r = subprocess.run(['aws', '--profile', profile, '--region', region,
                           'directconnect', 'describe-virtual-interfaces', '--output', 'json'],
                          capture_output=True, text=True, env=env)
        if r.returncode != 0: continue
        for v in json.loads(r.stdout).get('virtualInterfaces', []):
            v['_profile'] = profile; v['_region'] = region
            all_vifs.append(v)
    print(f"Discovered: {len(all_conns)} connections, {len(all_vifs)} VIFs")

    # Fetch per-VIF metrics with BOTH ConnectionId + VirtualInterfaceId dimensions
    def vif_metrics(v):
        out = {}
        for metric in ['VirtualInterfaceBpsEgress', 'VirtualInterfaceBpsIngress',
                       'VirtualInterfacePpsEgress', 'VirtualInterfacePpsIngress',
                       'VirtualInterfaceBgpStatus',
                       'VirtualInterfaceBgpPrefixesAccepted', 'VirtualInterfaceBgpPrefixesAdvertised']:
            r = subprocess.run([
                'aws', '--profile', v['_profile'], '--region', v['_region'],
                'cloudwatch', 'get-metric-statistics',
                '--namespace', 'AWS/DX', '--metric-name', metric,
                '--dimensions',
                  f'Name=ConnectionId,Value={v["connectionId"]}',
                  f'Name=VirtualInterfaceId,Value={v["virtualInterfaceId"]}',
                '--start-time', start, '--end-time', end,
                '--period', '3600', '--statistics', 'Average', 'Maximum',
                '--output', 'json'
            ], capture_output=True, text=True, env=env, timeout=20)
            if r.returncode == 0:
                out[metric] = json.loads(r.stdout).get('Datapoints', [])
        return v, out

    print(f"Fetching VIF metrics in parallel...")
    vif_results = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for f in as_completed([ex.submit(vif_metrics, v) for v in all_vifs]):
            vif_results.append(f.result())

    # Aggregate by connection
    by_cid = defaultdict(lambda: {'eg_max': 0, 'in_max': 0, 'vifs': []})
    for v, m in vif_results:
        cid = v['connectionId']
        eg = max((dp.get('Maximum', dp.get('Average',0)) for dp in m.get('VirtualInterfaceBpsEgress', [])), default=0)
        ing = max((dp.get('Maximum', dp.get('Average',0)) for dp in m.get('VirtualInterfaceBpsIngress', [])), default=0)
        by_cid[cid]['eg_max'] = max(by_cid[cid]['eg_max'], eg)
        by_cid[cid]['in_max'] = max(by_cid[cid]['in_max'], ing)
        by_cid[cid]['vifs'].append({'vid': v['virtualInterfaceId'], 'name': v['virtualInterfaceName'],
                                     'type': v['virtualInterfaceType'], 'state': v['virtualInterfaceState'],
                                     'eg_max': eg, 'in_max': ing})

    # Print summary
    print(f"\n{'CID':<14} {'Name':<46} {'BW':<8} {'Eg pico':<22} {'In pico':<22} Saúde")
    print('-'*100)
    for cid in sorted(by_cid):
        c = all_conns.get(cid, {})
        bw = parse_bw(c.get('bandwidth', ''))
        info = by_cid[cid]
        eg_pct = info['eg_max']/bw*100 if bw else 0
        in_pct = info['in_max']/bw*100 if bw else 0
        health = '🔴' if max(eg_pct, in_pct) > 80 else ('🟡' if max(eg_pct, in_pct) > 60 else '🟢')
        print(f"{cid:<14} {(c.get('connectionName','?'))[:44]:<46} {c.get('bandwidth','?'):<8} "
              f"{info['eg_max']/1e6:>5.0f}Mbps ({eg_pct:>4.1f}%)    "
              f"{info['in_max']/1e6:>5.0f}Mbps ({in_pct:>4.1f}%)    {health}")

    json.dump({'connections': all_conns, 'by_cid': dict(by_cid), 'vifs': [(v, m) for v,m in vif_results]},
              open(args.out,'w'), indent=2, default=str)
    print(f"\n✓ Saved {args.out}")

if __name__ == '__main__':
    main()
