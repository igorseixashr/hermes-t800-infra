#!/usr/bin/env python3
"""24h Transit Gateway throughput + drop counts report — cross-account.

Discovers TGWs in network accounts, dedupes by TransitGatewayId (TGW shared via RAM
appears in multiple accounts), then queries CloudWatch metrics in parallel.

Usage:
  python3 tgw_report.py [--hours 24]
"""
import json, subprocess, os, argparse
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT = [
    ('aws-network', 'us-east-1'),
    ('corp-network-prod', 'sa-east-1'),
    ('corp-network-prod', 'us-east-1'),
    ('corp-network-prod', 'us-east-2'),
    ('network-production-4588', 'sa-east-1'),
    ('network-production-4588', 'us-east-1'),
    ('network-production-4588', 'us-east-2'),
    ('rsfn-network', 'sa-east-1'),
    ('rsfn-network', 'us-east-1'),
    ('shared', 'us-east-1'),
    ('shared-production', 'us-east-1'),
    ('network-hub-gsn', 'us-east-1'),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=int, default=24)
    ap.add_argument('--out', default='/tmp/azreport/aws_tgw_final.json')
    args = ap.parse_args()

    end = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    start = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
    env = {**os.environ, 'AWS_PAGER': ''}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # Discover TGWs (deduped)
    seen, tgws = set(), []
    for profile, region in DEFAULT:
        r = subprocess.run(['aws', '--profile', profile, '--region', region,
                           'ec2', 'describe-transit-gateways',
                           '--filters', 'Name=state,Values=available,pending,modifying',
                           '--output', 'json'],
                          capture_output=True, text=True, env=env, timeout=30)
        if r.returncode != 0: continue
        for t in json.loads(r.stdout).get('TransitGateways', []):
            key = t['TransitGatewayId']
            if key in seen: continue
            seen.add(key)
            t['_profile'] = profile; t['_region'] = region
            tgws.append(t)
    print(f"Unique TGWs: {len(tgws)}")

    def fetch(t):
        out = {'tgw': t, 'metrics': {}}
        for metric in ['BytesIn', 'BytesOut', 'PacketsIn', 'PacketsOut',
                       'PacketDropCountBlackhole', 'PacketDropCountNoRoute',
                       'BytesDropCountBlackhole', 'BytesDropCountNoRoute']:
            r = subprocess.run([
                'aws', '--profile', t['_profile'], '--region', t['_region'],
                'cloudwatch', 'get-metric-statistics',
                '--namespace', 'AWS/TransitGateway', '--metric-name', metric,
                '--dimensions', f'Name=TransitGateway,Value={t["TransitGatewayId"]}',
                '--start-time', start, '--end-time', end,
                '--period', '3600', '--statistics', 'Sum', 'Average', 'Maximum',
                '--output', 'json'
            ], capture_output=True, text=True, env=env, timeout=20)
            if r.returncode == 0:
                out['metrics'][metric] = json.loads(r.stdout).get('Datapoints', [])
        return out

    print(f"Fetching metrics in parallel...")
    results = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        for f in as_completed([ex.submit(fetch, t) for t in tgws]):
            results.append(f.result())

    def total(m, key):
        return sum(dp.get('Sum', 0) for dp in m.get(key, []))

    print(f"\n{'TgwId':<22} {'Conta':<28} {'Região':<11} {'Name':<35} {'BytesIn':<10} {'BytesOut':<10} {'Drops'}")
    print('-'*120)
    for r in sorted(results, key=lambda x: -(total(x['metrics'], 'BytesIn') + total(x['metrics'], 'BytesOut'))):
        t = r['tgw']
        m = r['metrics']
        name = next((tag['Value'] for tag in t.get('Tags',[]) if tag['Key']=='Name'), '-')
        bin_gb = total(m, 'BytesIn') / 1e9
        bout_gb = total(m, 'BytesOut') / 1e9
        drops = total(m, 'PacketDropCountBlackhole') + total(m, 'PacketDropCountNoRoute')
        if bin_gb > 0.1 or bout_gb > 0.1 or drops > 0:
            warn = ' ⚠️' if drops > 1000 else ''
            print(f"{t['TransitGatewayId']:<22} {t['_profile'][:26]:<28} {t['_region']:<11} {name[:33]:<35} {bin_gb:>6.1f}GB   {bout_gb:>6.1f}GB   {drops:>6.0f}{warn}")

    json.dump(results, open(args.out,'w'), indent=2, default=str)
    print(f"\n✓ Saved {args.out}")

if __name__ == '__main__':
    main()
