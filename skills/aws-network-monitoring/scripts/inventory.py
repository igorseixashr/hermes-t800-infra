#!/usr/bin/env python3
"""Cross-account inventory of DX, TGW, VPN, CloudWAN across an AWS Org.

Probes a list of network-relevant accounts in parallel and reports counts per
(account, region) combination. Run AFTER setup_profiles.py + aws sso login.

Usage:
  python3 inventory.py [--accounts a,b,c] [--regions sa-east-1,us-east-1,us-east-2]
"""
import json, subprocess, os, argparse, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_ACCOUNTS = [
    'aws-network', 'corp-network-prod', 'rsfn-network',
    'network-production-4588', 'network-non-production',
    'shared', 'shared-production', 'network-hub-gsn',
    'network-homolog', 'corp-network-non-prod',
]
DEFAULT_REGIONS = ['sa-east-1', 'us-east-1', 'us-east-2']

def probe(profile, region):
    out = {'profile': profile, 'region': region, 'dx': 0, 'tgw': 0, 'vpn': 0, 'cwan_core': 0, 'cwan_global': 0, 'err': None}
    env = {**os.environ, 'AWS_PAGER': ''}
    try:
        for key, cmd in [
            ('dx',          ['directconnect', 'describe-connections']),
            ('tgw',         ['ec2', 'describe-transit-gateways', '--filters', 'Name=state,Values=available,pending,modifying']),
            ('vpn',         ['ec2', 'describe-vpn-connections', '--filters', 'Name=state,Values=available,pending']),
            ('cwan_core',   ['networkmanager', 'list-core-networks']),
            ('cwan_global', ['networkmanager', 'describe-global-networks']),
        ]:
            r = subprocess.run(['aws', '--profile', profile, '--region', region, *cmd, '--output', 'json'],
                              capture_output=True, text=True, env=env, timeout=20)
            if r.returncode != 0: continue
            d = json.loads(r.stdout)
            field = {'dx':'connections','tgw':'TransitGateways','vpn':'VpnConnections',
                     'cwan_core':'CoreNetworks','cwan_global':'GlobalNetworks'}[key]
            out[key] = len(d.get(field, []))
    except subprocess.TimeoutExpired:
        out['err'] = 'timeout'
    except Exception as e:
        out['err'] = str(e)[:60]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--accounts', default=','.join(DEFAULT_ACCOUNTS))
    ap.add_argument('--regions', default=','.join(DEFAULT_REGIONS))
    ap.add_argument('--out', default='/tmp/azreport/aws_inventory.json')
    args = ap.parse_args()

    accs = args.accounts.split(',')
    regs = args.regions.split(',')
    tasks = [(p,r) for p in accs for r in regs]
    print(f"Probing {len(tasks)} (account,region) combinations in parallel...")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        for f in as_completed([ex.submit(probe, p, r) for p, r in tasks]):
            results.append(f.result())

    print(f"\n{'Profile':<28} {'Region':<11} {'DX':>3} {'TGW':>4} {'VPN':>4} {'CW-C':>5} {'CW-G':>5} err")
    print('-'*78)
    for r in sorted(results, key=lambda x: (x['profile'], x['region'])):
        marker = '⭐' if (r['dx'] or r['tgw'] or r['vpn'] or r['cwan_core'] or r['cwan_global']) else '  '
        print(f"{marker} {r['profile']:<26} {r['region']:<11} {r['dx']:>3} {r['tgw']:>4} {r['vpn']:>4} {r['cwan_core']:>5} {r['cwan_global']:>5}  {r['err'] or ''}")

    json.dump(results, open(args.out,'w'), indent=2)
    print(f"\n✓ Saved {args.out}")
    print(f"  DX={sum(r['dx'] for r in results)} TGW={sum(r['tgw'] for r in results)} VPN={sum(r['vpn'] for r in results)} CW-Core={sum(r['cwan_core'] for r in results)} CW-Global={sum(r['cwan_global'] for r in results)}")

if __name__ == '__main__':
    main()
