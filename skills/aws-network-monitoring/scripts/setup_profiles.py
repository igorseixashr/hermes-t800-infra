#!/usr/bin/env python3
"""Auto-generate ~/.aws/config profiles from AWS SSO list-accounts.

Prerequisites:
  - aws sso login --sso-session <name> --use-device-code (run this first)

Usage:
  python3 setup_profiles.py [--sso-session corp] [--region sa-east-1]
"""
import json, subprocess, os, glob, re, argparse, sys
from concurrent.futures import ThreadPoolExecutor

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sso-session', default='corp')
    ap.add_argument('--region', default='sa-east-1', help='Default region for generated profiles')
    ap.add_argument('--sso-region', default='us-east-1')
    ap.add_argument('--start-url', default='https://d-906789a408.awsapps.com/start')
    args = ap.parse_args()

    cache_dir = os.path.expanduser('~/.aws/sso/cache')
    files = sorted(glob.glob(f'{cache_dir}/*.json'), key=os.path.getmtime, reverse=True)
    token = None
    for f in files:
        d = json.load(open(f))
        if 'accessToken' in d:
            token = d['accessToken']
            break
    if not token:
        sys.exit("ERROR: No SSO token found. Run: aws sso login --sso-session " + args.sso_session)

    env = {**os.environ, 'AWS_PAGER': ''}

    accs = []
    nt = None
    while True:
        cmd = ['aws', 'sso', 'list-accounts', '--access-token', token, '--region', args.sso_region,
               '--max-results', '100', '--output', 'json']
        if nt: cmd += ['--next-token', nt]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        d = json.loads(r.stdout)
        accs.extend(d.get('accountList', []))
        nt = d.get('nextToken')
        if not nt: break
    print(f"Discovered {len(accs)} accounts")

    def get_roles(acc):
        r = subprocess.run(['aws', 'sso', 'list-account-roles', '--access-token', token,
                            '--region', args.sso_region, '--account-id', acc['accountId'], '--output', 'json'],
                           capture_output=True, text=True, env=env)
        try:
            rl = json.loads(r.stdout).get('roleList', [])
            return acc, [r['roleName'] for r in rl]
        except Exception:
            return acc, []

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(get_roles, accs))

    def slugify(name):
        s = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
        return s[:50] or 'unnamed'

    def pick_role(roles):
        for pref in ['AWSNetworkAdministratorV2', 'AWSNetworkAdministrator', 'AWSPowerUser', 'AWSAdministrator', 'AWSReadOnly']:
            if pref in roles: return pref
        return roles[0] if roles else None

    slugs = {}
    for a, r in results:
        s = slugify(a.get('accountName') or a['accountId'])
        if s in slugs:
            s = f"{s}-{a['accountId'][-4:]}"
        slugs[s] = (a, r)

    lines = [
        f"[sso-session {args.sso_session}]",
        f"sso_start_url = {args.start_url}",
        f"sso_region = {args.sso_region}",
        f"sso_registration_scopes = sso:account:access",
        ""
    ]
    skipped = []
    for slug, (a, roles) in sorted(slugs.items()):
        role = pick_role(roles)
        if not role:
            skipped.append((slug, a['accountId'], a.get('accountName')))
            continue
        lines += [
            f"[profile {slug}]",
            f"sso_session = {args.sso_session}",
            f"sso_account_id = {a['accountId']}",
            f"sso_role_name = {role}",
            f"region = {args.region}",
            f"output = json",
            ""
        ]

    cfg_path = os.path.expanduser('~/.aws/config')
    open(cfg_path, 'w').write('\n'.join(lines))
    print(f"✓ Wrote {cfg_path}")
    print(f"  Profiles: {sum(1 for s,(a,r) in slugs.items() if pick_role(r))}/{len(accs)}")
    if skipped:
        print(f"  Skipped (no role): {len(skipped)}")
        for s, aid, n in skipped[:10]:
            print(f"    {aid} {n}")

if __name__ == '__main__':
    main()
