---
name: network-observability-dashboards
description: Use when building Grafana Zabbix network dashboards.
---

# Network Observability Dashboards (Grafana + Zabbix)

Build network monitoring dashboards interactively, connecting Grafana panels to Zabbix data sources for infrastructure telemetry.

## FPDC Monitoring Central — Catálogo de Dashboards em Produção

Para consulta direta em troubleshooting ou criação de novos painéis, consulte o catálogo completo em:
`/home/hermes/fpdc-network/fpdc-monitoring-central/docs/CATALOG_DASHBOARDS.md`

### Resumo dos UIDs & Dashboards Ativos (Host: `http://10.10.1.10:3000`):
- **F5 Infraestrutura & Plataforma:** `/d/f5-infra-overview` (`var-f5_cluster`, `var-f5_host`) — CPU/Memória Host e TMM, status HA, interfaces físicas.
- **F5 Virtual Server Drilldown:** `/d/f5-vs-drilldown` (`var-f5_host`, `var-vs`, `var-pool`) — Status operacional, curConns, throughput In/Out bps, volume diário em barras.
- **F5 Pool Drilldown:** `/d/f5-pool-drilldown` (`var-f5_host`, `var-pool`) — Eficiência `(active/total)*100`, status membros, curConns por pool.
- **Cisco IP SLA Operacional:** `/d/ipsla-overview` (`var-site`, `var-device`, `var-tag`) — RTT médio, Jitter SD/DS, perda de pacotes.
- **Cisco IP SLA TCP Connect:** `/d/ipsla-tcpconnect` (`var-site`, `var-device`, `var-tag`) — Latência de conexão TCP para portas de serviços críticos/RSFN.
- **Cisco IP SLA Tracepath:** `/d/ipsla-tracepath` (`var-path_tag`) — Saltos hop-by-hop na rede e isolamento de latência WAN.
- **Cisco IP SLA Status Geral:** `/d/ipsla-status` — Tabela executiva com código de retorno (`oper_sense`) de todos os probes.
- **Cisco IP SLA por Site:** `/d/ipsla-por-site` — Comparativo consolidado de latência entre datacenters.

### Diretrizes de Troubleshooting & Visual Telemetry:
- **Context-Aware URLs:** Em todo tshoot, monte a URL com as variáveis preenchidas (`?var-<chave>=<valor>&from=now-1h&to=now&refresh=10m`) para levar direto ao equipamento/porta/VIP sob análise.
- **Visual Snippets no Chat:** Quando aplicável enriquecer o diagnóstico visualmente, gere ou capture a imagem do gráfico e anexe via `MEDIA:/path/to/chart.png` para exibição nativa no Telegram.

## Workflow: Step-by-Step Dashboard Setup

1. **Template Variables Setup**:
   - Create `group`: Variable type `Query`, Data source `Zabbix`, Query Type `Group`.
   - Create `host`: Variable type `Query`, Data source `Zabbix`, Query Type `Host`, filtering by `$group`.
2. **Core Health Panels**:
   - **Operational Status (UP/DOWN)**: 
  ## Core Health Panels
     - **Operational Status (UP/DOWN)**: 
       - **Time Series (Step Interpolation)**: Recommended for clean binary availability (`Reachable`). Use `Time series` panel style, `Line interpolation: Step before`, set Y-axis decimals to `0`, add `Value mappings` (`1` -> `UP`, `0` -> `DOWN`), configure `Thresholds` (`Base`/`<=0` = Red/DOWN, `1` = Green/UP), set `Color scheme: From thresholds (by value)`, and set `Gradient mode: Scheme` to apply threshold colors on line/fill.
       - **Alternative Panels**: Stat panel with sparkline or State timeline.
     - **System Uptime**: Stat panel for device uptime (`Uptime`).
     - **Hardware Resources**: Time series for CPU utilization (`CPU utilization`) and memory utilization (`Memory utilization`).
     - **Traffic / Interfaces**: Time series for interface inbound/outbound octets.

  ## Dashboard Layout & Organization
  - **Rows (Collapsible Sections)**: Group panels by site or function (e.g., Datacenter BGP/Uptime sections like `Atlanta - BGPs`, `Chicago - BGPs`) using Grafana Rows for clean multi-site navigation.

## Pitfalls & Best Practices
- Bind variables hierarchically (`group` -> `host`) to ensure clean multi-site multi-device filtering.
- Step-by-step manual configuration in Grafana provides precise control over variable scopes and panel options when JSON imports are not desired.
- See `references/grafana-time-series-reachable.md` for detailed configuration steps on binary reachability (`Reachable`), step interpolation, gradient schemes, and text panel rendering.

## Provisioning dashboards as JSON files (any datasource, not just Zabbix)

When dashboards are authored as raw JSON (`dashboards-json/*.json` + a
provider YAML in `provisioning/dashboards/`), instead of built interactively
in the UI, several Grafana quirks bite that don't show up in the UI-driven
workflow above:

- **Auto-Refresh Default Interval Sizing (10m vs. 1m)**:
  - For operational drilldown and telemetry dashboards querying InfluxDB/Prometheus, avoid aggressive auto-refresh intervals (`1m` or lower). Default to `"refresh": "10m"` to prevent query storms and browser memory bloat, especially when multiple operators keep dashboards open.
  - Ensure `"10m"` is present in `timepicker.refresh_intervals: ["10s", "30s", "1m", "5m", "10m", "30m"]` and passed explicitly in portal drilldown query parameters (`&refresh=10m`).
- **Total Volume from Monotonic Counters (InfluxQL Stat Panels)**:
  - Do NOT run `difference()` or `non_negative_difference()` on a single Stat panel without `GROUP BY time(...)` — InfluxQL returns empty/NULL.
  - To compute total transferred volume over any selected window, use:
    `SELECT (spread("bits_in") + spread("bits_out")) / 8 FROM "<measurement>" WHERE ... GROUP BY time($__interval) fill(0)` with `"reduceOptions": {"calcs": ["sum"]}` and unit `decbytes`. Grafana sums the bucket spreads into the exact total volume.
- **Grafana Data Links Variable Resolution (`${var}` vs `${__data.fields.var}`)**:
  - In panel data links forwarding to another dashboard (e.g. VS Drilldown -> Pool Drilldown), reference template variables directly as `${f5_host}` and `${pool}`.
  - Do NOT use `${__data.fields.pool}` unless the query explicitly projects a field/tag alias named `pool`. Otherwise, Grafana forwards the literal literal string `${__data.fields.pool}` in `&var-pool=...`, breaking the target dashboard with "no-data".
- **Visual Hierarchy: Real-Time Timeseries Above Daily Bar Charts**:
  - Place instant Stat cards in Row 1 (`h: 4`), real-time line timeseries (concurrent connections, bandwidth bps) in Row 2 (`h: 8`), and historical daily volume bar charts (`timeseries` with `custom.drawStyle: "bars"` and `GROUP BY time(1d) fill(0)`) at the bottom (`h: 8`, full width `w: 24`).
- **Pool Redundancy Efficiency Metric**:
  - Compute pool health via `(last("active_members") / last("total_members")) * 100` as a percent Stat panel with background color thresholds (`100%` green, `80-99%` yellow, `< 50%` red).
- **InfluxQL Derivative in Stat Panels Requires `GROUP BY time(...)`**:
  - `non_negative_derivative(mean("field"), 1s)` in InfluxQL returns NULL / No Data when used in a Stat panel without a time bucket. Always group by a minute bucket (`GROUP BY time(1m) fill(null)`) and set panel calculation to `Last*` (`lastNotNull`).
- **Searchable Dropdown Combos Require `type: "query"`**:
  - Never configure variable `type: "textbox"` for dynamic entities (e.g., Virtual Servers, Pools, interfaces). Use `type: "query"` with `refresh: 1` (On Dashboard Load) and `SHOW TAG VALUES FROM "<measurement>" WITH KEY = "<tag>" WHERE "<parent_tag>" =~ /^$<parent_tag>$/` to render an interactive, searchable combobox with autocomplete.
- **Decouple Separate Entity Drilldown Dashboards**:
  - Do not merge distinct entities (e.g., Virtual Servers and Pools) into a single shared drilldown dashboard. When an operator selects a Pool, all VS panels render with "No Data", and vice versa. Always maintain distinct, focused dashboards (e.g., `f5-vs-drilldown` and `f5-pool-drilldown`) and cross-link via panel data links.
- **Every target needs its own `datasource` + `refId`, not just the panel.**
  A panel-level `"datasource": {...}` is not enough for legacy/InfluxQL-style
  targets — omitting per-target `datasource`/`refId` triggers a silent
  `Failed to upgrade legacy queries — Datasource <uid> was not found` error
  in the UI even though the datasource exists and the panel-level field is
  correct.
- **Template variable `query` format is per-variable-type, not universal.**
  For InfluxDB `type: query` variables, `query` must be a plain STRING
  (`"query": "SHOW TAG VALUES ..."`) — wrapping it as `{"query": "..."}`
  (the object form some other datasource/variable types expect) breaks the
  variable with `Error updating options: N.replace is not a function`.
  Don't cargo-cult one datasource's variable shape onto another.
- **To group panels together per repeated variable value, repeat a `row`,
  not the individual panels.** Giving each panel its own `"repeat": "tag"`
  makes Grafana stack every repeated GROUP in its own full-width line —
  gauges never end up side by side. The fix: wrap the panels in a
  `{"type": "row", "repeat": "tag", ...}` panel; the row itself repeats per
  variable value and the panels placed after it (with gridPos widths
  summing to 24) render together on one line per repetition.
- **Dashboard JSON changes apply on their own — no Grafana restart needed.**
  The `dashboards` provider re-reads files within its
  `updateIntervalSeconds` (typically 30s); confirm the pickup by checking
  `dashboard.version` in `grafana.db` (SQLite) rather than assuming success
  from the (often silent) log.
- **Datasource provisioning is NOT hot-reloaded like dashboards**:
  Unlike dashboard files, new datasource YAMLs in `/etc/grafana/provisioning/datasources/`
  are only evaluated on `grafana-server` startup. If dashboards display
  "no-data" or "Datasource <uid> not found", verify whether the datasource
  is registered in Grafana's database: `SELECT uid, name FROM data_source` in
  `/var/lib/grafana/grafana.db`. A new provisioned datasource will only become
  active after `systemctl restart grafana-server` (or by inserting the record
  into `data_source` and restarting). Remember `systemctl reload` is not supported
  by Grafana units.
- **Clean Panel Titles & Variable Offloading to Tooltips (`description`)**:
  - Keep visible panel titles strictly concise, clean, and descriptive (e.g. `Status Operacional`, `Banda Trafegada (In/Out)`, `Pool Padrão`), completely free of raw variable syntax (`$vs`, `$pool`, `$host`) and resolution tokens (`(${collection_interval}-sec Avg)`).
  - Offload the variable context and resolution to the panel `description` (renders as a hover `(i)` tooltip, e.g. `Virtual Server: $vs | Resolução: Média 60s | Host: $f5_host`). This keeps the visual dashboard clean and readable on small screens while maintaining full contextual traceability for the operator.
- **Explicit Short Series Aliases (`alias`) & `renameByRegex` Transformations**:
  - Always define explicit, short `alias` values on every time series target (e.g., `Entrada (In)`, `Saída (Out)`, `Conexões Simultâneas`, `Novas Conexões/s`, `Volume Diário`).
  - Without an explicit `alias`, InfluxDB and Prometheus output fully qualified measurement paths and tag sets (`f5_cpu_sys_cpu_...User %`), cluttering the legend and pushing charts out of view.
  - When scraping multi-interface measurements where the port name is embedded in the measurement key (`f5_interfaces_1_0_stats_counters_bitsIn`), add a Grafana transformation `renameByRegex` with regex `f5_interfaces_([0-9mg_]+)_stats_counters_(bits|pkts)(In|Out).*` and renamePattern `Interface $1 ($2)`. This dynamically shortens series legends to clean identifiers like `Interface 1_0 (In)`.
- **Use `alias` on each target and `fieldConfig.overrides` +
  `displayName` on table columns** to turn raw measurement/tag names
  (`jitter_raw.mean {op_tag: X}`, `device`, `op_tag`) into readable legends
  and column headers — do this proactively for any dashboard meant for
  someone other than the author.
- **Put a `description` on every panel** (renders as a hover (i) icon) that
  explains what the metric means and how to read the thresholds/mappings —
  especially for status/sense codes that don't self-explain (e.g. a
  device-reported "OK" often just means "the probe completed", not "the
  circuit is fully healthy").
- **Resolution Suffix in Panel Titles & InfluxDB Template Variables Pitfall**:
  - InfluxDB datasource in Grafana does NOT support scalar time series queries (`SELECT last(elapsed)...`) for template variables — it expects tag keys/values from `SHOW TAG VALUES`. Scalar queries leave `options: []` and `current: {}`, causing `${collection_interval}` in titles to render as empty or `(-sec Avg)`.
  - Standing User Rule: Never hardcode a static resolution suffix (e.g. `(60-sec Avg)`) into panel titles as a workaround. A static suffix misrepresents reality if the backend collection cadence changes.
  - If resolution cannot be 100% reliably dynamic and true to live scrapes, **omit the resolution suffix from panel titles entirely**. Keep titles clean and descriptive (e.g., `Conexões Simultâneas e Totais`), and document the expected cadence in the hover `description` tooltip or rely on Grafana's native resolution display in the panel footer.
- **Before designing a new dashboard convention from scratch, check
  whether this Grafana instance already has one.** Query
  `sqlite3 /var/lib/grafana/grafana.db "SELECT uid, data FROM dashboard"`
  (or the Python stdlib `sqlite3` fallback shown above) and grep existing
  dashboards' JSON for the pattern you're about to reinvent — title
  suffixes, templating tricks, and layout choices are often already
  established site-wide and should be matched, not reinvented per-project.
