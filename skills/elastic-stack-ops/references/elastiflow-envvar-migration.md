# ElastiFlow flow-collector env-var migration (7.13 → 7.26)

The collector's env-var namespace was reorganized across the 7.x line. Old
`EF_FLOW_*` keys are **silently ignored** by 7.26 — ingestion breaks with no
fatal error. When bumping the collector tag, translate every customized var.
Authoritative source: https://docs.elastiflow.com/flowcoll/configuration
(use the GitBook `?ask=` endpoint on any `*.md` page to confirm a specific var).

## Translation map (confirmed Jun 2026)

| Function | Old (≈7.13) | New (≈7.26) |
|----------|-------------|-------------|
| ES output enable | `EF_FLOW_OUTPUT_ELASTICSEARCH_ENABLE` | `EF_OUTPUT_ELASTICSEARCH_ENABLE` |
| ES addresses | `EF_FLOW_OUTPUT_ELASTICSEARCH_ADDRESSES` | `EF_OUTPUT_ELASTICSEARCH_ADDRESSES` |
| ES TLS | `EF_FLOW_OUTPUT_ELASTICSEARCH_TLS_ENABLE` | `EF_OUTPUT_ELASTICSEARCH_TLS_ENABLE` |
| ES user/pass | `EF_FLOW_OUTPUT_ELASTICSEARCH_USERNAME/PASSWORD` | `EF_OUTPUT_ELASTICSEARCH_USERNAME/PASSWORD` |
| Decode NetFlow5/9 | `EF_FLOW_DECODER_NETFLOW5_ENABLE` / `NETFLOW9_ENABLE` | `EF_PROCESSOR_DECODE_NETFLOW5_ENABLE` / `NETFLOW9_ENABLE` |
| Decode IPFIX | `EF_FLOW_DECODER_IPFIX_ENABLE` | `EF_PROCESSOR_DECODE_IPFIX_ENABLE` |
| Decode sFlow5 | `EF_FLOW_DECODER_SFLOW5_ENABLE` | `EF_PROCESSOR_DECODE_SFLOW5_ENABLE` |
| Option templates (nf9+ipfix interface table) | `EF_FLOW_DECODER_NETFLOW9_ENABLE_OPTIONS` + `EF_FLOW_DECODER_IPFIX_ENABLE_OPTIONS` (two flags) | `EF_PROCESSOR_ENRICH_NETIF_FLOW_OPTIONS_ENABLE` (single flag, default true) |
| netif metadata fallback | `EF_PROCESSOR_ENRICH_NETIF_METADATA_ENABLE` | `EF_PROCESSOR_ENRICH_NETIF_METADATA_ENABLE` (unchanged, default true) |
| MaxMind ASN enable | `EF_FLOW_DECODER_ENRICH_MAXMIND_ASN_ENABLE` | `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_ASN_ENABLE` |
| MaxMind GeoIP enable | `EF_FLOW_DECODER_ENRICH_MAXMIND_GEOIP2_ENABLE` | `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_GEOIP_ENABLE` |
| MaxMind ASN/GeoIP path | (n/a) | `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_ASN_PATH` / `_GEOIP_PATH` (default `/etc/elastiflow/maxmind/GeoLite2-ASN.mmdb` / `GeoLite2-City.mmdb`) |
| DNS enrich | `EF_FLOW_DECODER_ENRICH_DNS_ENABLE` | `EF_PROCESSOR_ENRICH_IPADDR_DNS_ENABLE` |
| Pool size | `EF_PROCESSOR_POOL_SIZE` | `EF_PROCESSOR_POOL_SIZE` (unchanged; min 2, diminishing returns >32) |
| Index template shards/replicas | (n/a) | `EF_OUTPUT_ELASTICSEARCH_INDEX_TEMPLATE_SHARDS` / `_REPLICAS` |
| License accept | `EF_LICENSE_ACCEPTED` | `EF_LICENSE_ACCEPTED` (unchanged) |
| UDP listener IP/port | `EF_FLOW_SERVER_UDP_IP` / `_PORT` | `EF_FLOW_SERVER_UDP_IP` / `_PORT` (unchanged) |

## Hard rules learned

- **MaxMind enabled + missing `.mmdb` = PANIC crashloop** in 7.26 (not a silent
  skip). Real error: `Maxmind ASN Enricher initialization failed: open
  /etc/elastiflow/maxmind/GeoLite2-ASN.mmdb: no such file or directory`. If the
  DBs were never mounted (common — the old config "enabled" it but the files
  never existed, so geo/ASN enrichment was silently off), set both
  `..._MAXMIND_ASN_ENABLE` and `..._MAXMIND_GEOIP_ENABLE` to `"false"` to boot,
  then offer to download GeoLite2 (needs a free MaxMind license key) as a
  follow-up improvement.
- **Persistence volumes are mandatory in v7.5+:** mount host dirs to
  `/etc/elastiflow` (config + `maxmind/`) and `/var/lib/elastiflow/flowcoll`
  (state). Create with `chown -R 1000:1000` (the collector runs as uid 1000).
- **`network_mode: host` is required** for NetFlow/IPFIX — the Docker bridge
  drops the original exporter source IP, breaking device identification. sFlow
  is unaffected (agent IP is in the sFlow header).
- **Indices are recreated by the collector on every start.** To control
  shard/replica counts for single-node, set them via the collector's
  `EF_OUTPUT_ELASTICSEARCH_INDEX_TEMPLATE_*` vars, not by editing ES templates
  (which get overwritten).

## corp host reference

- `10.10.1.10` (Ubuntu, user `infra`, uid 1000) — ElastiFlow stack at
  `/opt/elastiflow`, data bind-mounted to `./esdata`. NetFlow v9 exporters
  (e.g. `10.30.0.244`). SSH reachable only after the network firewall is opened
  (ICMP passes by default, TCP filtered). Jun 2026 upgrade: ES+Kibana
  8.6.0→8.19.9, collector 7.13.0→7.26.0.
