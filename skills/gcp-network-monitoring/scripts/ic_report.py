#!/usr/bin/env python3
"""24h Interconnect attachment utilization + drops report via Cloud Monitoring REST API.

Queries `interconnect.googleapis.com/network/attachment/*` metrics for all
attachments in a target project.

Usage:
  python3 ic_report.py [--project transit-network-228018] [--hours 24]
"""
import json, subprocess, os, argparse, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BW_MAP = {'BPS_50M':50e6,'BPS_100M':100e6,'BPS_200M':200e6,'BPS_300M':300e6,
          'BPS_400M':400e6,'BPS_500M':500e6,'BPS_1G':1e9,'BPS_2G':2e9,
          'BPS_5G':5e9,'BPS_10G':10e9,'BPS_50G':50e9}

def get_token():
    r = subprocess.run(['gcloud','auth','print-access-token'],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def query_monitoring(project, token, filter_str, start, end, aligner='ALIGN_RATE', period='3600s'):
    params = {
        'filter': filter_str,
        'interval.startTime': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'interval.endTime': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'aggregation.alignmentPeriod': period,
        'aggregation.perSeriesAligner': aligner,
        'view': 'FULL',
    }
    url = f'https://monitoring.googleapis.com/v3/projects/{project}/timeSeries?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {'error': f'{e.code}: {e.read().decode()[:200]}'}
    except Exception as e:
        return {'error': str(e)[:200]}

def list_attachments(project):
    env = {**os.environ}
    r = subprocess.run(['gcloud','compute','interconnects','attachments','list',
                        f'--project={project}','--format=json'],
                       capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0: return []
    atts = json.loads(r.stdout) if r.stdout.strip() else []
    # Enrich with describe (region, bandwidth)
    out = []
    for a in atts:
        region = a['region'].split('/')[-1]
        rd = subprocess.run(['gcloud','compute','interconnects','attachments','describe',
                             a['name'],f'--project={project}',f'--region={region}','--format=json'],
                            capture_output=True, text=True, env=env, timeout=30)
        if rd.returncode == 0:
            full = json.loads(rd.stdout)
            full['_region'] = region
            out.append(full)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='transit-network-228018')
    ap.add_argument('--hours', type=int, default=24)
    args = ap.parse_args()

    end_t = datetime.now(timezone.utc).replace(microsecond=0, second=0, minute=0)
    start_t = end_t - timedelta(hours=args.hours)
    token = get_token()

    attachments = list_attachments(args.project)
    print(f"Found {len(attachments)} interconnect attachments in {args.project}\n")

    summary = []
    for a in attachments:
        name = a['name']; region = a['_region']
        bw_str = a.get('bandwidth','?'); bw_bps = BW_MAP.get(bw_str, 0)
        print(f"\n┌{'─'*88}┐")
        print(f"│ 📡 [{region:<12}] {name[:70]:<70}  ({bw_str}) │")
        print(f"└{'─'*88}┘")
        snap = {'name': name, 'region': region, 'bw_bps': bw_bps}

        for mt, label, unit, aligner in [
            ('interconnect.googleapis.com/network/attachment/sent_bytes_count','Egress (out)','bps','ALIGN_RATE'),
            ('interconnect.googleapis.com/network/attachment/received_bytes_count','Ingress (in)','bps','ALIGN_RATE'),
            ('interconnect.googleapis.com/network/attachment/egress_dropped_packets_count','Drops Egress','pps','ALIGN_RATE'),
            ('interconnect.googleapis.com/network/attachment/ingress_dropped_packets_count','Drops Ingress','pps','ALIGN_RATE'),
        ]:
            f = f'metric.type = "{mt}" AND resource.labels.attachment = "{name}"'
            d = query_monitoring(args.project, token, f, start_t, end_t, aligner)
            if 'error' in d:
                print(f"  {label:<16}: ERR {d['error'][:80]}")
                continue
            ts = d.get('timeSeries', [])
            vals = []
            for s in ts:
                for p in s.get('points', []):
                    v = p.get('value',{})
                    vals.append(float(v.get('doubleValue', v.get('int64Value', 0))) if v else 0)
            if not vals:
                print(f"  {label:<16}: (no data)"); continue
            avg = sum(vals)/len(vals); mx = max(vals)
            if unit == 'bps':
                ab = avg*8; mb = mx*8
                pct = mb/bw_bps*100 if bw_bps else 0
                warn = '🔴 >80%' if pct>80 else '🟡 >60%' if pct>60 else '🟢'
                print(f"  {label:<16}: avg={ab/1e6:>7.1f} Mbps  peak={mb/1e6:>7.1f} Mbps ({pct:>4.1f}%)  {warn}")
                if 'Egress' in label and 'Drop' not in label: snap['eg_max'] = mb
                elif 'Ingress' in label and 'Drop' not in label: snap['in_max'] = mb
            elif unit == 'pps':
                warn = '⚠️ DROPS' if mx>0 else '🟢'
                print(f"  {label:<16}: avg={avg:>9.2f} pps  peak={mx:>9.2f} pps  {warn}")
                snap[f'drops_{label.lower().split()[1]}'] = mx
        summary.append(snap)

    print('\n' + '='*100)
    print(f'📊 RESUMO — Interconnect Attachments ({args.hours}h)')
    print('='*100)
    print(f"{'Attachment':<55} {'Banda':<8} {'Pico Egress':<22} {'Pico Ingress':<22} Saúde")
    print('-'*120)
    for r in summary:
        bw_str = next((k for k,v in BW_MAP.items() if v == r['bw_bps']), '?')
        eg = r.get('eg_max', 0); ing = r.get('in_max', 0)
        ep = eg/r['bw_bps']*100 if r['bw_bps'] else 0
        ip = ing/r['bw_bps']*100 if r['bw_bps'] else 0
        drops = r.get('drops_egress', 0) + r.get('drops_ingress', 0)
        h = '🔴' if (ep>80 or ip>80 or drops>0) else '🟡' if (ep>60 or ip>60) else '🟢'
        print(f"{r['name'][:53]:<55} {bw_str:<8} {eg/1e6:>5.0f}Mbps ({ep:>4.1f}%)    {ing/1e6:>5.0f}Mbps ({ip:>4.1f}%)    {h}")

if __name__ == '__main__':
    main()
