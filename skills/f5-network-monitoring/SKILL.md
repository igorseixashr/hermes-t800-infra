---
name: f5-network-monitoring
description: F5 BIG-IP LTM monitoring via Zabbix SNMP Low-Level Discovery (LLD), partition handling, and Grafana visualization for least-connections load-balancing auditing.
---

# F5 Network Monitoring & Load Balancing Audit

## 1. Scope & Purpose
Procedures for discovering, monitoring, and auditing F5 BIG-IP LTM pools and pool members (nodes) using Zabbix SNMP Low-Level Discovery (LLD) and visualizing traffic distribution in Grafana (e.g., verifying Least Connections balancing).

## 2. SNMP Low-Level Discovery (LLD) for Pools & Members
- **Pool Name Discovery OID:** `discovery[{#POOLNAME},.1.3.6.1.4.1.3375.2.2.5.2.3.1.1]`
- **Pool Member Discovery OID:** Use direct numeric table OID `.1.3.6.1.4.1.3375.2.2.5.3.1.1.2` (exposing `{#SNMPINDEX}` and `{#SNMPVALUE}`) or the full discovery pair format:
  ```text
  discovery[{#POOLNAME},.1.3.6.1.4.1.3375.2.2.5.3.1.1.1,{#MEMBERNAME},.1.3.6.1.4.1.3375.2.2.5.3.1.1.2]
  ```
  *(Note: If using two pairs, ensure filters target `{#POOLNAME}` instead of `{#SNMPVALUE}` or `{#MEMBERNAME}`, as `{#SNMPVALUE}` is not generated when explicit macros are declared).*
- **Active Connections per Member (`ltmPoolMemberStatCurConns`):** `.1.3.6.1.4.1.3375.2.2.5.3.2.1.7.{#SNMPINDEX}`

## 3. Key Pitfall: Non-Common Partitions & SNMP Discovery
- F5 SNMP returns paths prefixed with the partition name (e.g., `/PCI/pool-name` or `/InsidePCI/pool-name`).
- **Self-IP Port Lockdown Hardening:** Set Self-IP Port Lockdown to **Allow Custom** (without "Include Default") to remediate Tenable/security alerts on SSH (22) and HTTPS (443). Data plane traffic (VIPs $\rightarrow$ pools $\rightarrow$ nodes) and TMM forwarding are unaffected. Preserve config-sync/mirror IPs (`10.31.0.x`) and BGP (`tcp/179`) where applicable.
- **Zabbix SNMP Discovery Pitfall (`Invalid SNMP OID: pairs of macro and OID are expected` or `cannot parse OID`):**
  - Occurs when Zabbix server lacks the F5 MIB files (`F5-BIGIP-LOCAL-MIB.txt`) or when raw `snmp.discovery` is mixed with numeric OIDs.
  - **Alternative Strategy (Native Discovery & Static Fallbacks):** When raw LLD string matching is cumbersome due to F5 composite path returns (e.g., `/pool/node`), check if the Zabbix template already provides built-in discovery rules (like `Node stats discovery` using `ltmNodeAddrStatNodeName`). Alternatively, fallback to static node items using exact numeric leaf OIDs discovered via `snmpwalk` to bypass strict LLD filter validation in locked-down GUI environments.
- **Filter configuration in Zabbix:**
  - Macro: `{#SNMPVALUE}`
  - Operator: `matches`
  - Value: `^/InsidePCI/pool-name.*` (always include `.*` if the returned OID string includes node IP/port suffix like `/pool-name 10.x.x.x:443`).

## 5. F5 Virtual Server (VIP) Audit & Partition Categorization
- When auditing LTM Virtual Servers exported across partitions (`SHARED`, `NONPCI`, `PCI`, `Common`):
  - **Parsing Strategy:** Extract `ltm virtual <name>` blocks and inspect their descriptions and Ansible deployment tags (`(Ansible) <team>'s <app>`).
  - **Categorization Rules:**
    - Map Ansible tags to their respective teams/domains (`clr`, `tms`, `fo`, `glias`, `acquirer`, `payments`, `affiliation`, etc.).
    - Fallback classification for manual/non-Ansible VIPs by analyzing description keywords (e.g., `splunk`, `zabbix`, `grafana`, `cyberark`, `dns`, `netbox`).
    - Quantify and group VIPs per partition to provide high-level inventory reports for security and architecture teams.
  - **Deliverable Format:** When the user asks for a "visualização"/report of this inventory:
    - First pass: a rich standalone HTML file (Tailwind CDN, dark theme `bg-slate-950`/`bg-slate-900`, KPI cards + per-partition tables) works well for a full drill-down deliverable.
    - If the user then says "generate an HTML with the same summary I saw here" — they mean the exact chat-message text/structure (headers, bullet counts, sections) reproduced as styled HTML, NOT a redesigned/richer version. Mirror the prior text 1:1 in HTML cards, don't reinterpret it.
    - Deliver by returning the local file path prefixed with `MEDIA:` (e.g. `MEDIA:/home/hermes/.hermes/cache/report.html`) so the platform renders/attaches it.
    - `default sort order: always descending (maior → menor)` for every ranking in a dashboard/report — partition totals, status/availability breakdown, per-category tables, and chart bar/doughnut ordering. Don't default to alphabetical or discovery order; sort by count desc unless the user asks otherwise. User explicitly corrected this once — treat it as the standing default for all future F5 VIP dashboards, not a one-off ask.

## 7. Querying Virtual Servers by Profile (TMSH Pitfalls & Proven Syntax)
- **TMSH `list ltm virtual` filter limitation:** TMSH does NOT support direct argument filtering for sub-block properties like `profiles { <name> }` (e.g. `list ltm virtual profiles { ... }` or `list ltm virtual one-line profiles { ... }` throws `Syntax Error: unexpected argument "profiles"` or `"one-line" unknown property`).
- **Canonical TMOS Syntax (Piping to grep):**
  - Inside TMOS (`(tmos)#`): Always use `one-line` so the full virtual server definition and its profiles remain on a single line, then pipe to `grep`:
    ```bash
    list ltm virtual one-line | grep <profile-name>
    # To extract only the virtual server names:
    list ltm virtual one-line | grep <profile-name> | awk '{print $3}'
    ```
  - From Bash (`~ #`): Run across all partitions:
    ```bash
    tmsh -q -c "cd /; list ltm virtual one-line" | grep -i "<profile-name>" | awk '{print $3}'
    ```
  - To count occurrences of a profile across all VSs:
    ```bash
    tmsh -q -c "cd /; list ltm virtual one-line" | grep -c "<profile-name>"
    ```
  - For batch auditing multiple profiles (fast one-shot memory export):
    ```bash
    VARS=$(tmsh -q -c "cd /; list ltm virtual one-line")
    for p in "profile-1" "profile-2"; do
      count=$(echo "$VARS" | grep -c "$p")
      echo "$p: $count VS(s)"
    done
    ```
- **Direct config verification (Zero-false-positive check):**
  - If TMOS queries return empty but a profile exists in GUI, search `/config/bigip.conf` directly:
    ```bash
    grep -rn "<profile-name>" /config/
    ```
    If only the definition line (`ltm profile ...`) appears, the profile is orphaned with 0 virtual servers attached.
- **Profile Inheritance Pitfall:** If the profile search returns no virtual servers, verify if the profile is a parent or child. Virtual servers may attach a child profile that inherits from the target profile. Check for children:
  ```bash
  tmsh -q -c "cd /; list ltm profile client-ssl one-line" | grep "<parent-profile-name>"
  ```
- **Multiline list trap:** Running `list ltm virtual | grep <profile-name>` without `one-line` returns only the matching profile line inside the definition block, stripping the `ltm virtual <name>` header line. Never omit `one-line` when piping to grep.
  - **Parsing `tmsh show ltm virtual | grep -E "Ltm::Virtual Server|Availability|State"` text dumps:** Output is partition-header lines (e.g. `Common`, `NONPCI`, `PCI`, `QA`, `SHARED`) followed by repeating 3-line blocks: `Ltm::Virtual Server: <name>` / `Availability : <available|offline|unknown|unavailable>` / `State : <enabled|disabled|disabled-by-parent>`. Track `current_partition` as you scan lines top-to-bottom and reset it on each header line; accumulate (partition, name, availability, state) tuples. "Em uso" (actually in use, not just configured) = `Availability: available` AND `State: enabled` — report this distinct from raw partition/VS counts, since most partitions have a large fraction sitting `offline`/`disabled` (config present, no real traffic).

## 8. F5 Telemetry Streaming (TS) Operations & Ingestion
- **Verification of TS Installation (Zero-Impact Healthcheck):**
  - Check whether Telemetry Streaming RPM is installed and active without logging into the shell:
    ```bash
    curl -sk -u "${NET_USER}:${NET_PASS}" https://<BIG-IP-IP>/mgmt/shared/telemetry/info
    ```
  - HTTP `200 OK` with JSON (`version`, `release`, `schemaCurrent`) confirms TS is operational. A `404 Not Found` indicates the RPM package is not installed or `restnoded` has not loaded the extension.
- **Metrics Scraping & Declarative Pull:**
  - Fast pull of full system metrics (Virtual Servers, Pools, nodes, CPU, memory):
    ```bash
    curl -sk -u "${NET_USER}:${NET_PASS}" https://<BIG-IP-IP>/mgmt/shared/telemetry/pull
    ```
- **Telegraf Pipeline Architecture:**
  - **Push Pattern:** Configure F5 TS declaration with a `Generic_HTTP` consumer target pointing to Telegraf's `inputs.http_listener_v2`. Eliminates SNMP polling load on BIG-IP control plane.
  - **Pull Pattern:** Configure Telegraf `inputs.http` or `inputs.prometheus` to poll `/mgmt/shared/telemetry/pull`.
  - **Interval Sizing Pitfall:** Do not set TS collection or polling intervals below 10s — sub-10s cycles cause memory growth in `restnoded` on TMOS. Maintain intervals between 30s and 60s.
  - **Telegraf inputs.prometheus Timeout Pitfall:** Telegraf's `inputs.prometheus` defaults to `response_timeout = "5s"`. On BIG-IPs with large inventories (>1,000 VIPs), Telemetry Streaming Prometheus dynamic formatting takes 5–8 seconds to render headers/body. Telegraf fails with `context deadline exceeded (Client.Timeout exceeded while awaiting headers)`. Always explicitly configure `timeout = "30s"` (not `response_timeout`, which in Telegraf ≥1.30.2 only controls HTTP client header wait).
  - **Single Table Scrape for 1,000+ VIPs/Pools (`virtual/stats` & `pool/stats`):** Querying individual VIP endpoints takes ~100ms each (>100s for 1k items). In contrast, a single GET to `/mgmt/tm/ltm/virtual/stats` and `/mgmt/tm/ltm/pool/stats` returns all VIPs and Pools with `clientside.curConns`, `clientside.bitsIn`, `clientside.bitsOut`, `serverside.curConns`, `activeMemberCnt`, and `status.availabilityState` in 2.5–3.2 seconds. Cache in-memory (TTL 30s) or stream to InfluxDB in batch.
  - **PAM Lockout Pitfall (`pam_tally2` / `faillock`):** Escaping environment variables containing special characters (especially `$`) in automated deploy scripts is critical; passing truncated credentials even 3–5 times triggers F5 PAM brute-force lockout (`deny=5`, `unlock_time=900s`). When locked, all REST API and SSH connections return `HTTP 401 F5 Authorization Required`. Reset via `faillock --user <user> --reset` or `pam_tally2 --user <user> --reset`.

## 6. Ownership Overlay & Phased Remediation Planning
- **Ownership dashboard (separate from status dashboard):** When the user supplies a manual service→VIP-count→owner mapping per partition (Slack-pasted list with `@mentions`), build it as its own HTML report (KPI cards for coverage %, per-partition tables with Serviço/VIPs/Owners columns, an "Observações" section for risk callouts like bus-factor concentration or offline-but-unowned groups). Keep it separate from the raw status dashboard (availability/state) — cross-reference by filename in an "Observações" bullet rather than merging into one file.
- **Iterative dashboard edits:** Once the HTML report exists, treat small user asks ("remove this section", "rename this heading", "sort desc") as `patch` calls on the existing file, not full regenerations. Users in this workflow issue edits one at a time across several turns (remove a section → rename a heading → ...); re-deliver the same `MEDIA:` path each time.
- **"Bus factor" framing:** When one owner covers multiple high-count services in a partition (e.g. one person owns 5 services / 50+ VIPs), call it out explicitly as a bus-factor/knowledge-concentration risk in the Observações section — this is the kind of finding the user wants surfaced, not just raw counts.
- **Phased-by-partition remediation plan — do NOT skip the vulnerability ID check:** Before drafting a "correção faseada por partição" plan, confirm what is actually being remediated (CVE / Tenable finding / TMOS patch / port-lockdown hardening). This context carries multiple, different F5 security workstreams (Port Lockdown hardening is one, but not the only one) — never assume which one is in scope from prior turns alone. Ask via clarify; if unanswered within the turn, state the assumption explicitly at the top of the plan and proceed (don't block indefinitely on a plan the user is waiting on).
- **Recommended phase order once confirmed:** lowest-criticality partitions first to validate the procedure (Common/QA) → SHARED → NONPCI → PCI last. Within a partition, sub-order by owner (batch all services under one owner into a single coordination window) and by ascending VIP count, saving the largest/most business-critical service (e.g. Clearing) for a dedicated window with formal CHG. Always pair each phase with: pre-check (HA status, config backup/UCS save), a validation step (`curConns` check + owner smoke test), and an explicit rollback step (restore UCS / revert the specific Self-IP or VIP attribute).

## 8. F5 Telemetry Streaming (TS) & High-Scale Metric Collection
- **Verification & Declaration Inspection:**
  - Health & Version: `GET https://<big-ip>/mgmt/shared/telemetry/info` (expects HTTP 200 with schema/version).
  - Active Declaration: `GET https://<big-ip>/mgmt/shared/telemetry/declare`.
- **Pull Consumer Endpoint Pitfall:**
  - Telemetry Streaming does NOT serve pull metrics at `/mgmt/shared/telemetry/pull` (returns 404).
  - Always query the named pull consumer path: `https://<big-ip>/mgmt/shared/telemetry/pullconsumer/<consumer_name>` (e.g. `/pullconsumer/prometheus-critical` or `/pullconsumer/vs`).
- **Telegraf `inputs.prometheus` Timeout Pitfall**:
  - `inputs.prometheus` defaults to `timeout = "5s"`. Because F5 Telemetry Streaming dynamically formats and serializes large Prometheus metrics payloads on the fly, responses typically take 5-7s, triggering `context deadline exceeded (Client.Timeout exceeded while awaiting headers)`.
  - Fix: Always set `timeout = "30s"` explicitly inside `[[inputs.prometheus]]` when scraping F5 TS pull consumer endpoints. (Note: in Telegraf $\ge$1.30, `response_timeout` only sets HTTP client header timeout; use `timeout` for the Prometheus scrape).
- **Service Account PAM/TACACS Lockout Protection**:
  - TMOS enforces failed login lockouts via `pam_tally2` or `faillock` (typically 5 failed attempts locks the account for 15 minutes or indefinitely).
  - Ensure automation credentials containing special characters (e.g. `$`, `"`, `'`) are passed without bash interpolation (use single quotes or direct config file injection), otherwise repeated failed background scrapes will lock the service account across all F5 devices simultaneously.
  - Reset command via TMOS bash: `faillock --user <user> --reset` or `pam_tally2 --user <user> --reset`.
- **Capacity & Bulk REST Statistics for Large Inventories (1,000+ VIPs/Pools)**:
  - While sequential querying of individual VIPs causes `mcpd` CPU contention, a single batch query to `/mgmt/tm/ltm/virtual/stats` and `/mgmt/tm/ltm/pool/stats` retrieves complete operational state (`status.availabilityState`), `clientside.curConns`, `bitsIn/Out`, and `activeMemberCnt` for all 1,000+ objects in ~2.5-3.2s.
  - In companion web apps, cache bulk LTM stats in-memory with a 30s TTL (`_STATS_CACHE_TTL = 30.0`) to provide instant operational views without polling F5 control plane on every user click.
- **Watchlist Pattern for High-Density ADC Portals**:
  - In environments with >1,000 Virtual Servers and Pools, avoid displaying all objects in operational dashboards. Implement a two-tier Watchlist:
    1. Fast periodic discovery importing names, partitions, and availability into local SQLite.
    2. Configuration view with multi-column sorting (type, host, partition, name, status), filtering, and a batch "Enable All Online" selector.
    3. Operational views showing only watched items with real-time stats and drilldown links to Grafana with pre-populated template parameters (`?var-f5_host=...&var-vs=...`).
- **Capacity & Resource Sizing for Large Inventories (1,000+ VIPs/Pools):**
  - Never query raw iControl REST `/mgmt/tm/ltm/virtual/stats` sequentially or in large batches for polling — querying 50 VIPs takes ~2.5s and causes heavy `mcpd` CPU contention.
  - TS native batching: Configure `workers: 5`, `chunkSize: 30`, and collection interval $\ge 30\text{s}$ (recommended 30s-60s) to keep `restnoded` memory footprint bounded.
  - Sizing for InfluxDB / TS: 1,000 VIPs produce ~40 metrics/VIP in Prometheus format (~40k data points/cycle raw, or ~4k data points/cycle filtered to `curConns`, `bitsIn`, `bitsOut`, `totRequests`). With multi-field line protocol, ingestion is ~70-200 writes/sec, consuming ~30-45 MB/day of disk.
- **HA & Secondary (Standby) Node Monitoring:**
  - TS must be queried/configured independently on both Active and Standby management IPs.
  - On Standby nodes, CPU, host memory, physical interfaces, power supplies, and sync status report live metrics, while Virtual Server counters remain idle/zero.
  - Track failover and sync state via `/mgmt/tm/cm/failover-status` (extracts `status` ACTIVE/STANDBY, flap counter `transitions`, peer heartbeat `pktsReceived`) and `/mgmt/tm/cm/sync-status` (`In Sync`, `Changes Pending`).

## 8. F5 Telemetry Streaming (TS) — Validation, Endpoints & Sizing
- **Verification of TS Installation:**
  - Check via REST API: `curl -sk -u <user>:<pass> https://<BIG-IP>/mgmt/shared/telemetry/info`
  - Returns `200 OK` with JSON (`version`, `release`, `schemaCurrent`). A `404 Not Found` means TS RPM is not installed.
- **Inspect Active Declarations:**
  - `GET https://<BIG-IP>/mgmt/shared/telemetry/declare`
- **Pull Consumer Endpoint URL Trap:**
  - Querying `GET /mgmt/shared/telemetry/pull` fails with `404 Not Found (Bad URL: /shared/telemetry/pull)`.
  - The canonical endpoint for Prometheus/pull scraping is strictly per-consumer:
    `GET https://<BIG-IP>/mgmt/shared/telemetry/pullconsumer/<consumer_name>` (e.g., `pullconsumer/vs`).
- **Capacity & Control Plane Sizing Rules:**
  - Raw TS Prometheus output generates ~40 metrics per Virtual Server and ~15 per Pool.
  - Direct iControl REST statistics (`/mgmt/tm/ltm/virtual/stats`) incur heavy control-plane latency (~2.5s per 50 VSs). Never poll unbatched REST endpoints directly for large inventories (1,000+ VSs).
  - In TS poller declarations, always configure internal chunking and worker bounds (`workers: 5`, `chunkSize: 30`, `interval: 30-60`) to avoid memory pressure on the `restnoded` daemon.
  - InfluxDB capacity for filtered metrics (Status, curConns, bitsIn/Out per VS + activeMembers per Pool) at 30s interval for ~1,000 VSs: ~72 writes/sec, ~250 KB payload/cycle, ~35 MB/day uncompressed storage.
  - **Telegraf Prometheus Timeout Pitfall**: Scrapes against F5 TS pull consumers (e.g., `/mgmt/shared/telemetry/pullconsumer/prometheus-dynamic`) can take 5-8s to assemble metrics across a full system. Telegraf's `inputs.prometheus` defaults to a 5s client timeout, causing `context deadline exceeded`. Always set `timeout = "30s"` in the input configuration.
  - **Fast Inventory & Status Discovery (1,000+ VIPs/Pools)**: Instead of querying individual VIPs or iterating `/mgmt/tm/ltm/virtual`, query `/mgmt/tm/ltm/virtual/stats` and `/mgmt/tm/ltm/pool/stats` once in bulk. Each call returns all items in ~2.5–3.2s with `nestedStats.entries.status.availabilityState` (`available`, `offline`, `unknown`), enabling rapid watchlist population and status filtering.
  - **TMOS PAM Lockout (`faillock` / `pam_tally2`)**: Ensure deployment scripts generating environment files containing service account passwords do not evaluate special characters (like `$`) via shell parameter expansion. Sending truncated passwords repeatedly trips TMOS PAM lockout (`HTTP 401 F5 Authorization Required`), which must be cleared via `faillock --user <user> --reset` or by waiting for the lockout timer to expire.
- **Telegraf `inputs.prometheus` Scrape Timeout Pitfall:**
  - Telegraf's `inputs.prometheus` plugin defaults to `timeout = "5s"`. Because F5 TS formats thousands of metric lines dynamically inside `restnoded`, scrape response times often range from 5s to 8s. A default scrape will fail with `context deadline exceeded (Client.Timeout exceeded while awaiting headers)`. Always explicitly set `timeout = "30s"` inside `[[inputs.prometheus]]`.
- **Password Character Escaping & `faillock` / `pam_tally2` Lockout:**
  - When persisting service credentials into environment files (`telegraf.env`, `.env`) via remote shells, double-quoted interpolation expands characters like `$` and silently truncates passwords. F5 TMOS brute-force protection (`faillock` or `pam_tally2`) triggers lockout after consecutive failed authentications, returning generic `HTTP 401: F5 Authorization Required` across all iControl REST endpoints and SSH. Always transfer credentials as literal single-quoted strings. If locked, reset via TMOS CLI: `faillock --user <user> --reset` or `pam_tally2 --user <user> --reset`.
- **Large-Scale VIP/Pool Watchlist Architecture:**
  - When monitoring F5 clusters hosting thousands of Virtual Servers (>1,000 per box), polling all objects creates unnecessary telemetry bloat and Grafana dashboard lag. Implement a two-tier Watchlist pattern:
    1. Fast on-demand inventory enumeration via iControl REST (`/mgmt/tm/ltm/virtual?$select=name,partition,destination` and `/mgmt/tm/ltm/pool?$select=name,partition`) into a local inventory database (takes ~1-2s total).
    2. Configuration UI (Watchlist) allowing operators to check/uncheck specific VIPs and Pools for active monitoring.
    3. Dedicated Telegraf shards (`telegraf-f5@<shard>`) pulling metrics for watched items and general platform health, keeping CPU overhead under 1%.
- **Telegraf Pull Consumer Timeout Pitfall:** Because `restnoded` dynamically renders thousands of Prometheus metric lines on demand, TS pull consumer endpoints routinely take 3s-6s to complete. Telegraf's `[[inputs.prometheus]]` default `timeout` (5s) triggers `context deadline exceeded`. Always configure `timeout = "30s"` in the scraper block.
- **Password Shell Expansion & TMOS Lockout:** Passwords containing `$` or shell metacharacters get truncated when written to environment files via double-quoted shell commands. A truncated password causes repeated 401s that trigger TMOS PAM account lockouts (`pam_tally2` or `faillock`, default lockout 15min / 900s). Always single-quote passwords without variable expansion when generating service environment files.
- **High-Scale Inventory Watchlist Pattern:** When an F5 estate hosts >1,000 Virtual Servers/Pools per box, full real-time dashboards become noisy and sluggish. Decouple into two layers: (1) fast on-demand metadata discovery (`/mgmt/tm/ltm/virtual?$select=name,partition,destination` takes ~1s for 1,000+ items) stored in a local inventory table; (2) a user-curated Watchlist with targeted Telegraf collection for active monitoring and drilldown dashboards.
- **Telegraf Scrape Timeout Pitfall (`timeout = "30s"` required):**
  - Telegraf's `[[inputs.prometheus]]` default timeout is 5 seconds. TS pull consumers format thousands of Prometheus metric lines dynamically in memory, routinely requiring 5–8 seconds to respond under moderate load. Always set `timeout = "30s"` in the Telegraf Prometheus plugin block — the default 5s causes persistent `context deadline exceeded (Client.Timeout exceeded while awaiting headers)` errors.
- **Service Account Lockout via Shell Variable Expansion (`pam_tally2` / `faillock`):**
  - TMOS PAM locks service accounts cluster-wide after consecutive failed authentication attempts (typically 3–5 attempts, locking for 15 minutes or indefinitely). When provisioning credentials into `.env` or systemd `EnvironmentFile` files, always quote values strictly with literal single quotes (`'...'`) to prevent shell expansion of `$` characters. An unescaped `$` truncates the password and triggers immediate multi-shard authentication failure and account lockout.
- **High-Inventory Watchlist Architecture Pattern (1,000+ VIPs/Pools):**
  - When monitoring clusters with hundreds or thousands of Virtual Servers and Pools, do not stream or display all objects indiscriminately. Decouple discovery from continuous polling:
    1. Run fast, single-call on-demand inventory queries via iControl REST (`/mgmt/tm/ltm/virtual?$select=name,partition,destination` and `/mgmt/tm/ltm/pool?$select=name,partition`) to populate a local SQLite inventory.
    2. Provide a configuration UI allowing operators to toggle an `is_watched` flag on critical services.
    3. Restrict dashboard table rendering and dedicated time-series collectors strictly to watched items, keeping control plane overhead on BIG-IP near 0%.
- **Telegraf Prometheus Timeout Pitfall (`context deadline exceeded`):**
  - Telegraf's `[[inputs.prometheus]]` default HTTP client timeout is 5s (`timeout = "5s"`).
  - TS pull consumer endpoints serialize thousands of metric lines on the fly and take 5–8s to return under live TMOS load.
  - Always configure `timeout = "30s"` in `[[inputs.prometheus]]`, otherwise Telegraf aborts the scrape with `context deadline exceeded (Client.Timeout exceeded while awaiting headers)`.
- **Credential Escaping & PAM/TACACS Lockout Trap:**
  - When writing `.env` files for Telegraf or collector daemons, wrap passwords containing special characters (especially `$`) in single quotes (`'...'`) or write binary-safe.
  - Shell variable interpolation during file generation silently truncates `$var`, sending bad passwords to the F5.
  - Repeated bad auth attempts trigger TMOS `pam_tally2` / `faillock` lockout (HTTP 401 across all REST/SSH endpoints for typically 15 minutes / 900s). Reset manually via `faillock --user <user> --reset` if accessible.
- **Backend Service Privilege Isolation:**
  - When running an API backend under systemd as an unprivileged user (e.g., `infra`), the process cannot read Telegraf's environment file (permissions `0600` owned by `telegraf-ipsla`).
  - Maintain a dedicated `.env` file owned by the backend user and explicitly add `EnvironmentFile=-/path/to/.env` to the backend systemd service unit.
- **Telegraf `inputs.prometheus` Scrape Timeout Pitfall**:
  - TS pull consumers dynamically format thousands of Prometheus metric lines on request, taking 3–6s on active boxes. Telegraf's default 5s timeout triggers `context deadline exceeded`. Always configure `timeout = "30s"` in `[[inputs.prometheus]]`. Do NOT use `response_timeout`, which in Telegraf ≥ 1.30.2 only governs header read deadlines.
- **F5 Service Account Lockout Prevention (`pam_tally2` / `faillock`)**:
  - F5 TMOS enforces brute-force protection locking accounts for 15 minutes (`deny=5`, `unlock_time=900`) across all API and SSH interfaces upon consecutive failed logins. Ensure password literals containing special characters (`$`) are strictly quoted in systemd/Telegraf `EnvironmentFile` to prevent silent shell interpolation from causing lockout.
- **Watchlist Architecture for Large Inventories (1,000+ VIPs/Pools)**:
  - For boxes with dense VIP/pool counts, separate discovery from polling. Query metadata fast via `$select=name,partition`, store in a local SQLite inventory, and allow operators to curate an active Watchlist so continuous TS/Telegraf polling focuses only on critical endpoints.
- **Pull vs. Push Architecture & Firewall Decoupling:**
  - Pull (`inputs.prometheus` scraping `https://<BIG-IP>/mgmt/shared/telemetry/pullconsumer/<consumer_name>` on TCP 443) leverages existing outbound management access from the monitoring host. Eliminates need for reverse firewall openings (`F5 -> Telegraf:8450-8453`) required by `Generic_HTTP` push.
  - TS pull scraping reads from memory-cached buffers compiled by `restnoded` in background every 60s, avoiding synchronous `mcpd` CPU contention on query.
- **Watchlist Pattern for Large Inventories (1,000+ VIPs/Pools):**
  - Polling full `/mgmt/tm/ltm/virtual/stats` across 1,000+ VIPs returns ~40k+ metrics per cycle.
  - Use lightweight discovery (`/mgmt/tm/ltm/virtual?$select=name,partition`) to populate an inventory cache, and allow operators to curate a Watchlist. Configure TS `Telemetry_Endpoints` with targeted paths (`/mgmt/tm/ltm/virtual/~<partition>~<name>/stats`) to bound collection overhead to <1% CPU.
- **Telegraf Sharding per F5 Device:**
  - Standardize on a systemd template unit (`telegraf-f5@%i.service`) with 1 dedicated process per F5 box. Prevents HTTPS connection timeouts or buffer stalls on an active or standby node from delaying metrics collection across the cluster.
- **Pull vs. Push Architecture & Firewall Sizing:**
  - Pull via `Telemetry_Pull_Consumer` (`type: Prometheus`) does NOT trigger live metric harvesting at scrape time. `restnoded` pre-populates metrics in-memory on its internal poll cycle (e.g. 60s). Scrapes simply read this cache, keeping management CPU impact < 1%.
  - Pull avoids reverse firewall openings (F5 -> collector server); standard outbound HTTPS (TCP 443) from collector to BIG-IP management suffices.
- **Collector Sharding Pattern:**
  - Follow the 1-shard-per-box model (`telegraf-f5@<box_id>.service`) using `inputs.prometheus` pointed at `/mgmt/shared/telemetry/pullconsumer/<consumer_name>`. Isolates scrape failures, timeouts, and buffer pressure across distinct F5 appliances.
- **UI Watchlist & High-Density Presentation Pattern:**
  - In large environments with hundreds of VIPs/Pools, decouple ingestion from presentation: store all telemetry in InfluxDB, but gate status page rendering through an operator-configured Watchlist.
  - Standard columns for VIP status: F5 Host, Partition, Virtual Server Name, Default Pool (`default_pool`), Status Badge, Concurrent Connections (`curConns`), Estimated Bandwidth, Total Daily Bytes.
  - Direct drill-down: VIP and Pool names in UI tables must link directly to target Grafana dashboards passing entity context via template variables (`?var-host=...&var-vs=...&var-pool=...`).
- **Decoupling VS & Pool Drilldown Dashboards:**
  - Do not merge Virtual Server and Pool drilldown metrics into a single shared dashboard. When an operator drills into a Pool, all VS panels render empty ("No Data"), and vice versa. Always provision two distinct dashboards: `f5-vs-drilldown` and `f5-pool-drilldown`.
- **InfluxQL Throughput Derivative Pitfall in Grafana Stat Panels:**
  - `non_negative_derivative(mean("bits_in"), 1s)` in InfluxQL requires an explicit `GROUP BY time(...)` bucket (e.g. `GROUP BY time(1m) fill(null)`) and calculation set to `lastNotNull`. Evaluating `non_negative_derivative` in a stat panel without a time grouping returns NULL / No Data.
- **Grafana Combobox Template Variables (`type: "query"`):**
  - To render a searchable dropdown combo in Grafana for Virtual Servers or Pools, use `type: "query"` with `SHOW TAG VALUES FROM "f5_vs_stats" WITH KEY = "vs" WHERE "f5_host" =~ /^$f5_host$/` and `refresh: 1` (On Dashboard Load). Configuring `type: "textbox"` or static custom lists prevents operator search and dynamic host filtering.
- **Fast Default Pool Mapping via iControl REST (`$select=name,pool`):**
  - `/mgmt/tm/ltm/virtual/stats` provides counters and destination IP, but omits the configured default pool. To map pools for thousands of VIPs in a single fast call without per-object REST calls, query `/mgmt/tm/ltm/virtual?$select=name,pool` (~1-2s total) and strip partition paths (`/Common/`).
- **Standard 10-Minute Auto-Refresh for LTM Dashboards:**
  - Configure `"refresh": "10m"` across all F5 Grafana dashboards and API navigation links (`&refresh=10m`). Avoid 1m refresh cycles to prevent high query frequency against InfluxDB for multi-thousand VIP/Pool metrics.
- **InfluxQL Total Traffic Volume in Stat Panels (`spread` + `sum`):**
  - Difference functions like `non_negative_difference()` return NULL / No Data in InfluxQL if queried without a `GROUP BY time(...)` bucket.
  - To compute cumulative traffic volume across the entire dashboard time window in a Single Stat panel, query `SELECT (spread("bits_in") + spread("bits_out")) / 8 FROM "f5_vs_stats" WHERE ("f5_host" =~ /^$f5_host$/) AND ("vs" =~ /^$vs$/) AND $timeFilter GROUP BY time($__interval) fill(0)` with `reduceOptions.calcs = ["sum"]` and unit `decbytes`.
- **Grafana Data Links Syntax for Dashboard Variables:**
  - In Grafana panel data links, reference dashboard variables directly as `${var_name}` (e.g. `/d/.../f5-pool-drilldown?var-pool=${pool}&refresh=10m`), NEVER as `${__data.fields.var_name}` unless the query explicitly returns a field with that name. If the field is missing from the query payload, Grafana outputs the unexpanded literal string `${__data.fields.var_name}`, causing 404 / "No Data" on the target dashboard.
- **Hierarchical Layout for LTM Drilldown Dashboards:**
  - Tier 1 (Top): KPI Stat cards (Status, Conexões Ativas, Throughput Instantâneo, Total Trafegado no Período, Pool Associado).
  - Tier 2 (Center): Time-series line graphs side-by-side (Conexões Simultâneas/Totais on the left, Throughput In/Out bps on the right, `w: 12` each).
  - Tier 3 (Bottom): Full-width Daily Bar Chart (`drawStyle: bars`, `GROUP BY time(1d) fill(0)`, `w: 24`) showing historical daily volume.
- **Pool Redundancy Efficiency KPI in InfluxQL:**
  - Formula: `SELECT (last("active_members") / last("total_members")) * 100 AS "Eficiência" FROM "f5_pool_stats" WHERE ("f5_host" =~ /^$f5_host$/) AND ("pool" =~ /^$pool$/) AND $timeFilter`
  - Visual Thresholds: Unit `percent`, 1 decimal place. 100% = Green (full redundancy), 80-99% = Yellow (minor member loss), 50-79% = Orange (degraded), <50% = Red (critical or pool offline). Position as a top-row KPI card alongside member counts and throughput.
- **F5 Dashboard Ergonomics & corp Observability Standards:**
  - **Clean Panel Titles & Variable Offloading to Tooltips (`description`)**: Never clutter panel titles with raw template variable tokens (`$vs`, `$pool`, `$f5_host`) or resolution tokens (`${collection_interval}-sec Avg`). Keep visible titles concise, clean, and functional (e.g. `Status Operacional & Throughput Instantâneo`, `Banda Trafegada (In/Out)`, `Pool Padrão`, `Status & Estatísticas dos Membros`), and offload the specific entity context and resolution note to the panel `description` hover tooltip (`Virtual Server: $vs | Resolução: Média 60s`, `Pool: $pool | Host: $f5_host`).
  - **Short Series Legend Aliases (`alias`) & Regex Transformations**: Always define concise `alias` labels on queries (e.g. `Entrada (In)`, `Saída (Out)`, `Conexões Simultâneas`, `Novas Conexões/s`, `Volume Diário`, `Usuário (User %)`, `Sistema (System %)`, `Espera I/O (IOWait %)`). For multi-interface measurements with embedded interface names (`f5_interfaces_1_0_stats_counters_...`), apply Grafana transformation `renameByRegex` (`f5_interfaces_([0-9mg_]+)_stats_counters_(bits|pkts)(In|Out).*` -> `Interface $1 ($2)`) to prevent InfluxDB measurement paths from flooding chart legends.
  - **Resolution Detail in Tooltips**: Do NOT put `(${collection_interval}-sec Avg)` in the visible title — user preference is clean titles with resolution notes in the `description` tooltip. Configure `collection_interval` dynamically via InfluxQL `elapsed()` for any background metric aggregation:
  - **Resolution Suffix in Panel Titles Pitfall (`(XX-sec Avg)`)**:
    - Avoid using InfluxQL scalar queries (`SELECT last(elapsed)...`) for Grafana template variables to display dynamic resolution in titles: the Grafana InfluxDB plugin expects tag sets from `SHOW TAG VALUES`, so scalar timestamp tables fail to populate `options`, rendering the variable as empty or `(-sec Avg)`.
    - Never substitute an unverified query with a hardcoded static resolution suffix like `(60-sec Avg)` in panel titles. If the scrape or pull cadence changes, a static title misrepresents reality and violates telemetry integrity.
    - Standing User Rule: If the resolution cannot be 100% reliably dynamic, **do NOT place it in the panel title**. Keep panel titles clean, concise, and focused solely on the metric (e.g., `Conexões Simultâneas e Totais`, `Banda Trafegada (Throughput In/Out)`). Rely on Grafana's native bucket resolution display in the panel footer, or note the expected cadence in the panel `description` hover tooltip.
  - **Eliminating Scrape Gaps ("Vales" / Lacunas) in Custom LTM Collectors**:
    - **iControl REST Payload Size & Standby Node Latency**: Large F5 inventories (~1,900 VIPs/Pools) return ~15MB JSON on `/mgmt/tm/ltm/virtual/stats`. On standby appliances, `restjavad` routinely takes 15–28s to respond. A default 10s client timeout triggers persistent `<urlopen error timed out>`, skipping cycles and leaving gaps in InfluxDB. Always set HTTP timeout to $\ge 40\text{s}$.
    - **Parallel Appliance Scraping via `ThreadPoolExecutor`**: Never poll multiple F5 boxes sequentially in a single loop. Sequential blocking causes one lagging appliance to delay the entire cycle to >90s. Use `concurrent.futures.ThreadPoolExecutor(max_workers=N)` to scrape all appliances concurrently, reducing total cycle time to ~12–14s.
    - **Grafana `fill(previous)` for Time-Series Continuity**: InfluxQL queries with `GROUP BY time(1m) fill(null)` render sharp visual drops to zero ("vales") whenever a point arrives at 61s instead of 60s. Always configure `fill(previous)` on timeseries throughput and connection panels to maintain clean, gap-free line charts between 60s scrape intervals.
  - **Collector Loop Drift Prevention in Ingestion Daemons**: In custom polling scripts (like `f5_ltm_collector.py`), always measure cycle execution time and sleep `max(2.0, interval - (time.time() - t0))` instead of a naive `time.sleep(interval)`. Fixed sleep adds API round-trip latency to the interval (e.g. 35s execution + 60s sleep = 95s real cadence), causing cadence drift in InfluxQL `elapsed()` queries.
  - **Explanatory Tooltips (`description`) in PT-BR**: Every panel must include a clear `description` hover tooltip explaining what the metric represents and how to interpret thresholds/status (e.g. HA active/standby state, TMM vs Host memory, pool efficiency).
  - **F5 Navigation Menu Hierarchy**: Provide a top-level `Overview` entry linking directly to the cluster-wide infrastructure dashboard (`f5-infra-overview`) alongside granular entity drilldowns (`Virtual Servers`, `Pools`, `Watchlist`).
