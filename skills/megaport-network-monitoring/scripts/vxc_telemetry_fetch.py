import time
import sys
import json
import os
from _megaport_client import MegaportClient

def get_telemetry(client, product_uid, hours=48):
    now = int(time.time() * 1000)
    start = now - (hours * 3600 * 1000)
    
    params = {
        "from": start,
        "to": now,
        "step": "300000" # 5 minutos
    }
    
    # O método 'get' do client lida com auth e headers
    return client.get(f"/v2/product/{product_uid}/telemetry", params=params)

if __name__ == "__main__":
    client = MegaportClient()
    target_ids = ["1dad57a5", "03fabf4d", "243483e9", "3878b32c", "8177565a", "f0cd5eb4"]
    
    inventory = json.load(open('/tmp/megaport_vxc_report.json'))
    
    results = {}
    for tid in target_ids:
        uid = None
        for item in inventory:
            if item['productUid'].startswith(tid):
                uid = item['productUid']
                break
        
        if uid:
            print(f"Fetching telemetry for {tid}...", file=sys.stderr)
            results[tid] = get_telemetry(client, uid)
        else:
            results[tid] = "UID not found in inventory"
            
    print(json.dumps(results, indent=2))
