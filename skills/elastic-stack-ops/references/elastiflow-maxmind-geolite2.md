# ElastiFlow MaxMind GeoLite2 Enrichment — Download, Validate, Enable

The follow-up to the "MaxMind enabled without `.mmdb` = PANIC crashloop" pitfall.
This is how to actually provision GeoLite2 ASN + City databases and turn
geo/ASN enrichment back on, with verification.

## Path mapping (critical — get this right or it PANICs again)

The compose mounts the host config dir into the container:

```
./flowcoll/etc  ->  /etc/elastiflow      (so host ./flowcoll/etc/maxmind  ==  container /etc/elastiflow/maxmind)
```

The collector reads (defaults):
- `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_ASN_PATH=/etc/elastiflow/maxmind/GeoLite2-ASN.mmdb`
- `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_GEOIP_PATH=/etc/elastiflow/maxmind/GeoLite2-City.mmdb`

So the files MUST land in host `<compose_dir>/flowcoll/etc/maxmind/` and be
owned `1000:1000` (the collector's uid).

## Source decision (ask the user, default to pragmatic)

Official MaxMind download requires a **free account + license key** (env
`MAXMIND_LICENSE_KEY`, used by `geoipupdate` or the direct
`https://download.maxmind.com/.../GeoLite2-ASN/.../tar.gz?license_key=...` URL).

If NO license key exists in the environment (checked `~/.bashrc.d/`, the host,
`/etc/elastiflow`), the pragmatic path for an internal lab is the public GitHub
mirror **`P3TERX/GeoLite.mmdb`** which serves the official GeoLite2 files,
updated daily, no credential:

```
https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb
https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb
```

ALWAYS tell the user transparently that you used a mirror (not official), and
OFFER to swap to the official source + configure `geoipupdate` auto-refresh if
they have/can-get a license key. The mirror files are static until re-pulled;
geo/ASN data drifts over time.

Expected sizes (sanity check): ASN ≈ 12 MB, City ≈ 66 MB.

## Procedure (run download ON the target host — it has egress, your box may not)

```bash
DIR=/opt/elastiflow/flowcoll/etc/maxmind        # adjust to the real compose dir
mkdir -p "$DIR" && cd "$DIR"
for db in GeoLite2-ASN GeoLite2-City; do
  curl -sSL -o "${db}.mmdb.tmp" \
    "https://github.com/P3TERX/GeoLite.mmdb/raw/download/${db}.mmdb" \
    -w "  http=%{http_code} size=%{size_download}B\n"
done
```

## Validate BEFORE promoting (don't trust a download blindly)

Use `scripts/validate_mmdb.py` (scp it to the host, run with python3) — it reads
the MaxMind magic marker `\xab\xcd\xefMaxMind.com` and the `database_type`
string. Promote only on VALID:

```bash
python3 /tmp/validate_mmdb.py GeoLite2-ASN.mmdb.tmp GeoLite2-City.mmdb.tmp
# VALID mmdb | ...B | database_type...GeoLite2-ASN...   <- must say GeoLite2-ASN / GeoLite2-City
mv -f GeoLite2-ASN.mmdb.tmp  GeoLite2-ASN.mmdb
mv -f GeoLite2-City.mmdb.tmp GeoLite2-City.mmdb
chown 1000:1000 *.mmdb
```

## Re-enable + recreate collector only

```bash
cd <compose_dir>
sed -i 's/MAXMIND_ASN_ENABLE: "false"/MAXMIND_ASN_ENABLE: "true"/;
        s/MAXMIND_GEOIP_ENABLE: "false"/MAXMIND_GEOIP_ENABLE: "true"/' docker-compose.yml
docker compose config >/dev/null && echo VALID   # plan-first
docker compose up -d elastiflow-flow-collector    # ES/Kibana already healthy, don't churn them
# confirm no panic:
docker logs --since 30s elastiflow-flow-collector 2>&1 | grep -iE 'panic|maxmind.*fail' | grep -v '\.go:'
```

## PROVE enrichment with real data (don't just check "no error")

Private IPs (RFC1918, 10.x/172.16-31/192.168) legitimately resolve to ASN `0`
and no geo — that is correct, not a failure. To prove the enricher works, query
flows with a PUBLIC ASN resolved (`as.asn > 0`):

```bash
curl -s localhost:9200/elastiflow-flow-*/_search -H 'Content-Type: application/json' -d '{
  "size":5,
  "query":{"bool":{"should":[
    {"range":{"flow.server.as.asn":{"gt":0}}},
    {"range":{"flow.client.as.asn":{"gt":0}}}],"minimum_should_match":1}},
  "_source":["flow.*.ip.addr","flow.*.as.asn","flow.*.as.org","flow.*.geo.country.name","flow.*.geo.city.name"]}'
```

Healthy result: `flow.server.as.org="TIM S/A"`, `geo.country.name="Brazil"`,
`geo.city.name="Salvador"`, etc. Field names are CODEX schema:
`flow.{client,server,src,dst}.as.asn`, `.as.org`, `.geo.country.name`,
`.geo.city.name`.
