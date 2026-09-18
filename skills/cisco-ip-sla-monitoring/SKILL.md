---
name: cisco-ip-sla-monitoring
description: Build Cisco IP SLA pipelines via SNMP, Telegraf, InfluxDB.
version: 1.0.0
author: T-800 InfraOps
license: MIT
tags: [cisco, ip-sla, rttmon, snmp, telegraf, influxdb, grafana, netmiko]
metadata:
  hermes:
    tags: [cisco, ip-sla, rttmon, snmp, telegraf, influxdb, grafana, netmiko]
    related_skills: [safe-remote-deploy, service-daemon-ops, network-observability-dashboards]
---

# Cisco IP SLA Monitoring

Covers building or troubleshooting a Cisco IP SLA / RTTMON metrics
pipeline: SNMP discovery and collection via `CISCO-RTTMON-MIB`, Telegraf
`inputs.snmp` config generation, InfluxDB storage, Grafana
visualization, and Netmiko/CLI scraping for operations with no SNMP
path (path-jitter). Does not cover general Zabbix network dashboards
(`network-observability-dashboards`) or non-Cisco NaaS monitoring
(`aws-network-monitoring`, `megaport-network-monitoring`, etc.).

## When to Use
- Building a new Cisco IP SLA / RTTMON metrics collector (SNMP or CLI).
- "No data" / wrong data in an existing IP SLA → Telegraf → InfluxDB →
  Grafana pipeline.
- Any task mentioning `ip sla`, `rttmon`, `CISCO-RTTMON-MIB`,
  path-jitter, udp-jitter, or voip-jitter statistics on Cisco IOS/IOS-XE.

## Prerequisites
- SNMPv2c community OR SNMPv3 user (auth+priv). **Check which one the
  device actually has** with `show snmp user` / `show running-config |
  section snmp-server` before assuming v2c — SolarWinds-monitored
  estates especially tend to be SNMPv3-only with no community
  configured at all.
- Telegraf installed on the collector host. Confirm the REAL version
  (`telegraf --version`) and its actual accepted syntax
  (`telegraf --usage snmp`) before writing config — plugin syntax
  drifts across releases and blog examples/old specs go stale fast
  (see Pitfalls #5).
- For path-jitter: SSH/CLI (Netmiko) access — there is no SNMP
  substitute, full stop.

## Quick Reference
Full OID table + column meanings, validated live against IOS-XE
17.6.3a: `references/cisco-rttmon-oid-reference.md`. Load it before
hand-writing any OID. Commonly-copied "appendix" OID tables (from
specs, old blog posts) get the jitter table OID wrong — see Pitfall #1.
**Never wire an OID into code/config without confirming it live**
(`snmpget`/pysnmp GET) against the real device first.

## Procedure

### 1. Discovery — enumerate configured operations
Walk `rttMonCtrlAdminTag` (`1.3.6.1.4.1.9.9.42.1.2.1.1.3`) and
`rttMonCtrlAdminRttType` (`.1.2.1.1.4`) to get index + type per
operation. RttType enum: 1=icmpEcho, 6=tcpConnect, 7=http, 8=dns,
9=udpJitter/voipJitter (differentiate by a non-zero
`rttMonEchoAdminCodecType`, column `.27`), 2=pathEcho/path-jitter.
**path-jitter never appears in this walk on IOS-XE** — confirmed live,
13 of 32 real operations on a test router were invisible via any SNMP
walk of the admin tables. Treat that as expected, not a bug to chase.

For target/source address + port (`rttMonEchoAdminTable`, `.1.2.2.1`):
GET/walk column `.2` for target address, `.6` for source — these are
**raw 4-byte IPv4 octet strings**, not the `.11` "string" column (which
returns empty on IOS-XE). Parse manually:
`".".join(str(b) for b in raw_bytes)`; all-zero means "not configured"
(normal for source address). Port is column `.5`.

### 2. path-jitter — CLI-only, no SNMP path
`show ip sla configuration` gives target/tag/frequency per entry;
`show ip sla statistics <entry>` gives hop-by-hop RTT/jitter/loss.
Parse via Netmiko + regex. **Split the raw multi-entry blob on
`(?=Entry number:\s*\d+)` BEFORE running any per-field regex** — a
single `re.DOTALL` regex across the whole output silently leaks fields
from entry N into entry N+1 on routers with many operations (only
shows up once you have enough entries to actually collide). Normalize
whitespace (`re.sub(r"[ \t]+", " ", output)`) before matching hop
blocks — Cisco mixes tabs and `\r\n` inconsistently in this output.

### 3. Telegraf collection (SNMP-capable operations only)
Generate **one `[[inputs.snmp.table]]` block per device per table
family** (jitter vs generic-rtt), not one block per operation.
`index_as_tag = true` auto-tags every returned row with `index` = the
SNMP table row index (= `rttMonCtrlAdminIndex` = your inventory's
operation index) — a single request then covers every operation of
that family on the device, which is both simpler and cheaper than the
"one block per operation" pattern some older specs describe.

Enrich + filter with a generated `processors.starlark` block per
group: at config-gen time, build a
`{index: {op_tag, target, site, rtt_type}}` dict from your inventory,
then in `apply(metric)` look up `metric.tags.get("index")`; `return
None` for anything not in the dict (drops operations you don't want
polled — including any leftover path-jitter index that slipped into
the same table by mistake), otherwise merge the metadata into
`metric.tags` and compute derived fields (avg RTT/jitter, packet loss
%) in the same pass, div-by-zero guarded.

### 4. Validate before applying
Always run `telegraf --config ... --config-directory ... --test`
against generated config before reloading the live service. **Pass it
the same secrets the real `EnvironmentFile=` provides** — a bare
`subprocess.run(...)` inherits only the caller's env, not the systemd
unit's `EnvironmentFile`, so a naive test silently runs unauthenticated
and reports an auth error that looks like a credentials bug instead of
a test-harness gap. Merge the parsed `.env` file (or the freshly
generated secrets dict) into the subprocess's `env=` explicitly.

### 5. Grafana
InfluxDB 1.x datasource uses InfluxQL (not Flux). Keep dashboards +
datasource + folder as provisioning YAML/JSON under
`/etc/grafana/provisioning/`, `editable: false`, and pin the
datasource's `uid` explicitly so dashboard JSON exports don't break if
the datasource gets recreated.

Datasource secrets (e.g. a read-only InfluxDB password) can be kept out
of the YAML the same way Telegraf's `.env` works: reference
`${VAR_NAME}` in `secureJsonData`, then add `VAR_NAME=...` as its own
line in `/etc/default/grafana-server` (the unit's
`EnvironmentFile=`) — no plaintext secret in a file that might get
committed.

`grafana-server.service` typically does **not** support `systemctl
reload` for picking up new provisioning files (`Job type reload is not
applicable for unit grafana-server.service`) — provisioning changes
need a full `systemctl restart grafana-server`, which briefly drops
other users' sessions/dashboards on a shared instance. Get explicit
confirmation before restarting a Grafana that other teams rely on.
After that initial restart, the dashboard *provider* (not the
datasource) DOES pick up edited JSON files on its own within
`updateIntervalSeconds` — no further restart needed for dashboard-only
edits; confirm via the `dashboard.version` column bumping in
`grafana.db` rather than restarting again out of caution.

**Hand-written dashboard JSON throws "Failed to upgrade legacy
queries — Datasource <uid> was not found" in the UI (Grafana 9.5) even
though the datasource exists and panels have a top-level `datasource`
set.** Cause: each `target` inside `panel.targets[]` also needs its own
explicit `datasource: {type, uid}` and a `refId` — a panel-level
datasource alone isn't enough for provisioned (non-UI-authored) JSON,
because Grafana's legacy-query-upgrade path resolves the datasource
per-target first. Fix every target this way; bump the dashboard's
`"version"` field so the change is visibly distinct.

**Do NOT "fix" `templating.list[].query` into the object form
`{"query": "..."}` for an InfluxDB variable — that breaks it the other
way.** Confirmed live: wrapping a template variable's `query` in an
object (reasoning it should match the per-target fix above) produces
`Templating [varname] — Error updating options: N.replace is not a
function` on every affected variable. InfluxDB query-type template
variables want `query` as a **plain string** in Grafana 9.5 — the
per-target object-form fix and the variable string-form requirement
are two different rules for two different JSON locations; don't
generalize one into the other. If you see the `N.replace` error right
after touching template variables, that's the tell — revert `query` to
a bare string.

**Per-operation panels via `repeat`, not one averaged gauge per
metric.** If the dashboard has `site`/`device`/`tag` (or similar)
multi-select template variables and the ask is "let me see each
operation individually" rather than one aggregate number for the whole
selection, set `"repeat": "<template-var-name>"` (e.g. `"tag"`) plus
`"repeatDirection": "h"` and `"maxPerRow"` on the panel — Grafana clones
that panel once per selected variable value at render time (no template
variable interpolation into the query needed beyond the existing
`op_tag = '$tag'`/`=~ /^$tag$/` pattern already in the query). Keep one
or two non-repeated "aggregate across selection" panels alongside if a
rollup view is still useful.

**Compact layout preference: when a user asks to "save screen space",
put the repeated per-operation gauges (RTT/loss/status or similar small
metrics) SIDE BY SIDE in one row per operation (e.g. `w: 4` each, three
gauges = 12 of 24 grid columns), not stacked as separate repeat groups
each spanning the full width.** Confirmed as an explicit user
preference in this project — default to compact multi-gauge rows for
per-operation status panels rather than the wider single-metric-per-row
layout.

**If two Telegraf table families (e.g. jitter vs generic-rtt) both
produce a field with the same name (`oper_sense`), query BOTH
measurements in one InfluxQL statement instead of duplicating the
panel.** InfluxQL supports comma-separated measurements in `FROM`:
`SELECT last("oper_sense") FROM "jitter_raw", "rtt_raw" WHERE op_tag =
'$tag'` — resolves to whichever measurement actually has data for that
tag value. Confirmed live both directions (a jitter-only tag and an
rtt-only tag each returned correctly from the same query). Cheaper than
one panel per family when the field/unit is the same.

**Broken/gapped lines or "too high resolution" (1s/5s-looking) timeseries
panels, even though the real collection cadence is 60s/120s.** Cause:
`GROUP BY time($__interval)` with no floor lets Grafana pick its own
bucket width from the visible time range/panel pixel width — on a short
zoom window `$__interval` can resolve to 1s or 5s, far below the actual
Telegraf polling interval, so most buckets get `fill(null)` and the line
renders broken. Fix: pin a floor on every target that uses
`$__interval` by adding an explicit `"interval": "<collection_interval>s"`
key to the target object (e.g. `"interval": "60s"` for a 60s Telegraf
poll) — Grafana then never buckets finer than that, independent of zoom.
Confirmed live: added `interval: "60s"` to 3 timeseries targets across
two dashboards, bumped `version`, re-provisioned, and cross-checked
against a direct InfluxQL query — clean 60s buckets, no gaps. If devices
poll at different rates, either pin the floor to the FASTEST tier's
interval or split panels per poll-tier so one floor doesn't over-bucket
a slower-tier operation.

**Don't trust `grafana.log` alone to confirm dashboard provisioning.**
The datasource provisioning step logs clearly (`inserting datasource
from configuration`), but dashboard-provider inserts may not log at
`info` level in some versions (confirmed on 9.5.21) — a genuinely
successful provisioning can show zero matching log lines, looking like
a silent failure. Verify directly instead:
`sudo python3 -c "import sqlite3; c=sqlite3.connect('/var/lib/grafana/grafana.db'); print(c.execute(\"SELECT uid,title FROM dashboard WHERE uid LIKE '%yourprefix%'\").fetchall())"`
(sqlite3 CLI is often not installed; the stdlib `sqlite3` module always
is). Treat the database as the source of truth over the log.

## Pitfalls (all confirmed against a live IOS-XE 17.6.3a router)

1. **Wrong jitter-table OID in most copy-pasted references.**
   `1.3.6.1.4.1.9.9.42.1.3.5` is `rttMonJitterStatsEntry`
   (`rttMonStatsCaptureTable` — the complex historical/distribution-
   bucket table, explicitly the one you're usually told to avoid). The
   simple "latest value" table you actually want is
   `rttMonLatestJitterOperTable = 1.3.6.1.4.1.9.9.42.1.5.2.1`. Symptom:
   `.1.3.5.1.1.<index>` returns `No Such Object`; `.1.5.2.1.1.<index>`
   returns the real NumOfRTT.
2. **rttMonLatestRttOperTable column order is backwards in some
   references.** Column `.1` is `CompletionTime` (ms), `.2` is
   `OperSense` (status enum) — not the other way around. Verify by
   cross-checking `oper_sense` against `show ip sla summary`'s Return
   Code column (e.g. sense=6 must line up with "disconnected"/"no
   connection") before trusting any mapping you write down.
2b. **The jitter table has its OWN Sense OID — `.1.5.2.1.31`, not the
   generic RTT table's `.2`.** Forgetting to collect it means a
   "Status" panel/field is silently "No data" forever for every
   udpJitter/voipJitter operation, even though everything else in the
   pipeline is healthy — easy to miss because Sense already exists
   (correctly) for the OTHER rtt_type family and nothing errors. Add it
   to the jitter Telegraf table block explicitly; don't assume one
   status field covers both table families.
3. **System `pysnmp` package is often too old for the host's Python.**
   `python3-pysnmp4` (v4.x, apt) imports the removed `asyncore` module
   — breaks outright on Python 3.12. Fix: a venv with
   `pip install "pysnmp>=6,<7"` — NOT `pysnmp-lextudio` (same
   maintainers' deprecated package name, ships a different/broken
   `hlapi` surface). Real async API import:
   `from pysnmp.hlapi.asyncio import ...` — calls are coroutines
   despite the module path not saying "async".
4. **pysnmp 6.x `walkCmd`/`bulkCmd` can report the wrong row index.**
   Confirmed live and reproducible: ~20% of rows in a GETBULK walk
   reported an OID index one-off from a neighboring, nonexistent
   index, while the VALUE was correct for the real index. A direct
   `getCmd` on the exact index always returned correctly. If per-row
   identity matters (it does — this silently swaps target IPs between
   adjacent monitored circuits), don't trust walk-returned indices for
   anything you'll persist: either fetch columns via individual
   `getCmd` per already-known index, or cross-validate every
   discovered value against an independent source (the device's own
   `show` CLI output) before trusting a walk's index.
5. **Telegraf `inputs.snmp` syntax drifts across releases — verify
   against `telegraf --usage snmp` on the ACTUAL installed binary, not
   old blog posts or spec appendices:**
   - `[inputs.snmp.tags]` with a key literally named `tag` can collide
     with a reserved field name (`configuration specified the fields
     ["tag"], but they were not used`). Pick a different key (e.g.
     `op_tag`) and update any `inherit_tags` reference too.
   - `[[inputs.snmp.tag]]` (singular, dynamic-OID tag block) may not
     exist in newer releases — the replacement is `[[inputs.snmp.field]]`
     with `is_tag = true`.
   - Default `snmp_translator = "netsnmp"` shells out to
     `snmptable`/`snmptranslate` (needs the net-snmp package). If
     that's not installed, set `snmp_translator = "gosmi"` in
     `[agent]` (built-in Go translator, zero external deps) — don't
     install net-snmp just to satisfy the default.
   - `priv_protocol` accepts `"AES"`/`"AES192"`/`"AES256"`/`"DES"` —
     NOT `"AES128"` (the name pysnmp and many routers use for the same
     algorithm). Translate when generating config from inventory data
     that stores the pysnmp-style name.
   - `[[inputs.snmp.table]]` can silently gather ZERO metrics (no
     error, no data) if the base `oid` points at the wrong table.
     `--test` alone only validates syntax/init — it does NOT prove the
     SNMP walk produces rows. Always also do one live run (full daemon
     for one interval, or `--once` with `[[outputs.file]]` to a temp
     file) and confirm metrics actually appear before calling a config
     "validated".
6. **Terminal-tool sudo approval timeouts** when applying this on a
   remote host — see the `safe-remote-deploy` skill's SSH pitfall.
   Split every `sudo` action (copy unit file, daemon-reload, chown,
   chmod, enable, start) into its own single-command call; this bites
   during config-apply just as often as during read-only recon.
7. **One-way (unidirectional) RTT/latency is NOT a config-only feature
   you can turn on for an already-running operation.** `show ip sla
   statistics <n>` always shows `Number of Latency one-way Samples: 0`
   and `.../.../. milliseconds` all-zero unless BOTH of these are true:
   - NTP is synchronized between source AND target device (`show ntp
     status` → `Clock is synchronized`) — confirmed live this alone is
     NOT sufficient (see below).
   - The operation was configured with `precision microseconds` +
     `clock-tolerance ntp oneway percent <N>` (or `absolute <N>`) —
     **default tolerance is 0%**, so even a well-synced clock with a
     few ms of offset reports zero one-way samples until a realistic
     tolerance is set. `precision microseconds` must be configured
     BEFORE `clock-tolerance ntp oneway` (Cisco usage guideline).
   - **Both commands live inside the operation's `udp-jitter`
     submode and CANNOT be applied to a running entry.** Confirmed
     live: `ip sla <n>` on an active entry returns `Entry already
     running and cannot be modified (only can delete (no) and start
     over)`. Enabling real one-way latency on an existing fleet means
     **deleting and recreating every affected `ip sla` entry** — for a
     production monitoring estate (dozens to hundreds of operations)
     this is a real change with a monitoring-gap risk during the
     transition, not a config tweak. Get explicit user sign-off before
     doing this; don't do it opportunistically while investigating
     something else.
   - IP SLA v2 (`precision microseconds` implies v2 packet format) has
     an even harder restriction on some platforms/RSP3 modules: one-way
     latency values are not displayed in `show ip sla statistics` at
     all regardless of tolerance — check `show ip sla configuration
     <n>` / platform restrictions before promising this will work.
8. **Don't recreate operations just to chase one-way latency when a
   same-session workaround exists.** Per-direction JITTER and PACKET
   LOSS (SD = source→destination = "ida", DS = destination→source =
   "volta") are already exposed by the standard
   `rttMonLatestJitterOperTable` fields collected by the normal
   pipeline (`avg_jitter_sd_ms`/`avg_jitter_ds_ms`,
   `packet_loss_sd`/`packet_loss_ds` — see the OID reference) — **no
   NTP, no operation recreation, no risk.** This does not give you
   absolute one-way delay, but it does answer "which direction is
   degrading this circuit" for jitter/loss-driven problems (the common
   case), which is usually the actual question. Reach for this first;
   reach for one-way RTT (with its recreate-every-entry cost) only when
   the user explicitly needs absolute per-direction delay, not just
   which direction is worse.
9. **NTP rollout across a multi-router fleet: test every candidate
   source from every router BEFORE picking one.** A public/internet NTP
   source that's reachable from some sites can be unreachable from
   others (routing, firewall) — confirmed live (one public source
   failed from 2 of 7 routers). Ping (or better, check `show ntp
   associations` reach) every candidate from every router first, then
   pick sources reachable by ALL of them — all routers must share the
   same reference for one-way calculations to mean anything even once
   enabled. Prefer a stratum-1/GNSS-backed source when available (lower
   dispersion, faster convergence) over a stratum-2+ relay.
   Convergence from `ntp server X` to `Clock is synchronized` with low
   dispersion is NOT instant on classic IOS — `loopfilter state` moves
   FREQ (measuring drift) → CTRL (normal) over several `system poll
   interval` cycles (can be 10+ minutes); don't judge it failed after
   one or two checks. A device stuck at `stratum 16` / `.INIT.` /
   `reach=0` after 10+ min despite ICMP ping succeeding to the NTP
   source is a real block (UDP/123 filtered somewhere — e.g. a cloud
   Security Group on a CSR1000v/C8000v instance), not "still
   converging" — ICMP reachability does NOT prove UDP/123
   reachability. Don't use `debug ntp packets` on a production router
   to chase this — check `show ntp associations`/`show run | include
   ntp|access-list` first; escalate the SG/ACL question instead of
   debugging on the box.

## Verification
- Cross-check at least one discovered/collected value against the
  device's own CLI (`show ip sla summary` / `show ip sla statistics
  <n>` / `show ip sla configuration <n>`) — this is what catches OID
  and walk-index bugs before they reach a dashboard.
- Confirm data actually lands in InfluxDB with a direct query
  (`influx -database <db> -execute "SELECT * FROM <measurement> LIMIT 5"`)
  before calling the pipeline done. A green `systemctl status` only
  proves the process is running, not that it's writing real,
  correctly-tagged data.
