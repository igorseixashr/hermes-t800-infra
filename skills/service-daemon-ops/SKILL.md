---
name: service-daemon-ops
description: Operational procedures for managing long-lived background daemons, proxies, and services.
---

# Service Daemon Operations

Guidelines for managing persistent background processes (daemons, proxies, listeners) in this environment.

## Operational Rules

0. **CHECK FOR systemd FIRST — before any kill/restart.** This is the #1 time-waster. If a service is managed by systemd, killing the PID or `fuser -k <port>` does NOT stop it — systemd respawns it instantly (often within the same second), and if you were mid-edit it may reload a half-written file, producing wildly erratic behavior that looks like your code changes "aren't taking" or "randomly break". Symptom: after `kill`/`fuser -k`, `ss -tulnp | grep <port>` immediately shows the port held again by a *new* PID. Before touching any long-lived listener, run:
   ```bash
   ss -tulnp | grep :<port>            # find the PID
   ps -o cmd= -p <pid>                  # see how it was launched (look for 'uvicorn', '-m', wrapper scripts)
   systemctl status <service> 2>/dev/null | head    # is it systemd-managed?
   # Or discover the unit owning the cgroup:
   systemctl status <pid>
   ```
   If systemd-managed: edit the file, then `systemctl restart <service>` (let smart-approval prompt for it) — do NOT fight the port. Manual `nohup`/`setsid` launches are redundant and will just lose to systemd's respawn.
1. **Daemonization:** Do not use `&` in foreground terminal calls. Use `background=true` in `terminal()` calls for long-lived processes.
2. **Process Discovery:** Use `pgrep` or `ps -ef` to locate processes. Always verify if multiple PIDs exist for the same service before taking action.
3. **Redundancy Cleanup (non-systemd only):** If multiple instances exist AND the service is NOT systemd-managed, kill them and launch a fresh, clean instance. If it IS systemd-managed, use `systemctl restart` instead.
- **Cron Integration:** Avoid using pipes or complex shell command strings directly as cron job paths. If a command requires initialization/check-and-start, wrap it in a dedicated shell script file.
- **Log Rotation:** For long-running apps generating log/CSV files, implement a rotation strategy at the application level (e.g., weekly/daily folders or timestamps in filenames) or use OS-level utilities like `logrotate` to prevent disk overflow.

## Auditing & Versioning an Unversioned systemd App

When you find a systemd-deployed app that is NOT in any repo (the deploy dir
isn't a git repo, no `requirements.txt`, no README), the job is usually:
inspect → improvement report → package into the right repo. Full workflow +
reusable systemd hardening template: `references/systemd-hardening-and-packaging.md`.

Quick spine:
1. **Inspect, don't change prod.** `systemctl show <svc> -p FragmentPath --value`
   to find the unit; `cat` it; read the app code; `pip freeze` the venv to pin
   versions; check the `/proc/<pid>/cwd` to confirm relative-path assumptions.
2. **Audit security with `systemd-analyze security <svc>`.** A bare unit scores
   ~9.6 ("UNSAFE"). The report names every missing sandbox directive.
3. **Before sandboxing, check what the app actually needs.** ICMP/traceroute
   work WITHOUT root or `CAP_NET_RAW` when `sysctl net.ipv4.ping_group_range`
   is open (`0  2147483647`) — so `RestrictAddressFamilies=AF_INET AF_INET6` +
   no caps is fine. Verify before you restrict, or you'll break ping.
4. **Package following the TARGET REPO's own conventions, not your defaults.**
   Read a sibling directory in the repo first (its `install.sh`, `.gitignore`,
   `deploy/*.service`, README structure) and mirror it. Embed the improvement
   report in the README so it travels with the code.
5. **Never touch the host UNLESS explicitly authorized.** By default: versioning
   + recommendations only; hardening and `chmod` corrections go in a separate
   prod window. State this explicitly. When the user DOES authorize a live apply,
   follow the ordered backup→apply→verify→functional-proof→rollback procedure in
   section 6 of the reference. Two traps that only surface at apply time:
   `ProtectHome=yes` breaks apps writing to `~/` (fix: `HOME=<ReadWritePaths dir>`),
   and a green `systemctl is-active` is NOT proof — run one real cycle as the
   service user, in its `WorkingDirectory`, to confirm the app still works sandboxed.
6. **If asked to also "fix and push"** — apply YAGNI scoped to the app's
   lifecycle. On a deprecating app, fix only contained low-risk bugs
   (`python`→`sys.executable`, sequential→`ThreadPoolExecutor` with a single
   unified CSV write to avoid a thread race, simple `cap_history` row cap) and
   leave structural items (auth, UI rearchitecture) as README recommendations.
   Validate changed logic with stubbed deps (no live network). See section "4b"
   in `references/systemd-hardening-and-packaging.md`.

## Granting a non-privileged app user access to a hardened dedicated service

When a NEW dedicated systemd service is provisioned with its own service
user (e.g. `useradd --system` + `ProtectSystem=strict`, following the
"isolated instance" pattern), a separate application (e.g. a backend API
that generates and applies that service's config) often needs to read/
write its config dir and trigger a reload — without running the whole
app as that service user or as root.

- **Add the app's user to the service's group, then grant group perms:**
  `sudo usermod -aG <service_user> <app_user>` (takes effect on the app's
  NEXT login/session — an already-open SSH session needs a fresh
  connection or explicit `newgrp`/re-login to see it; a freshly-spawned
  subprocess in a NEW ssh session picks it up immediately). Then
  `sudo chmod -R g+w <config_dir>` on directories, but files need EXPLICIT
  `g+r` too — `chmod -R g+w` alone leaves a `600` secrets file at
  `rw--w----` (write-only for group, unreadable!); use `chmod 660` on
  files the app must read AND write (e.g. an `EnvironmentFile`/`.env`).
- **Reuse existing passwordless sudo for the reload/start command** rather
  than writing a new sudoers rule: check `sudo -l` first — if the app's
  user already has `NOPASSWD: ALL` (common on infra/ops boxes), the
  generating app can just shell out to `sudo systemctl reload
  <service>` directly; no new sudoers entry needed.
- **A `--test`/dry-run validation subprocess needs the SAME secrets the
  real service gets via `EnvironmentFile=`.** The systemd unit reads
  `EnvironmentFile` only at its own start/reload — a `subprocess.run()`
  from the generating app does NOT inherit it automatically. Read the
  env file yourself (simple `KEY=VALUE` parsing) and merge it into the
  subprocess's `env=` explicitly, or the validation will silently run
  unauthenticated and report an auth failure that looks like a
  credentials bug rather than a test-harness gap.

## Troubleshooting

- **"Script not found" in cron:** This happens when a shell pipeline is passed to cron as if it were a direct file path.
    *   **Fix:** Write a dedicated bash script (e.g., `~/scripts/ensure-service.sh`) that contains the check (pgrep/ps) and launch logic. Call this single path from cron.
- **Port already in use:** If a service fails to start due to port conflicts:
    *   First check ownership: `ss -tulnp | grep :<port>` then `systemctl status <pid>`.
    *   **If systemd-managed:** do NOT kill — `systemctl restart <service>`. Killing only triggers an instant respawn (see Operational Rule 0).
    *   **If NOT systemd-managed:** `kill -9 <pid>`, confirm with `ss` that the port is free, then relaunch.
- **Log/File Growth:** If a file (e.g., `results.csv`) grows indefinitely:
    *   **Fix:** Ensure the application rotates files by date (YYYY/MM/week_N/file.csv) or uses an append-only structure with external cleanup/compression, especially for high-frequency logs.
    - **Implementation Pattern:** In Python, use `pathlib.Path` with `datetime` to build dynamic folder/file paths (`LOG_DIR / str(now.year) / f"{now.month:02d}" / f"week_{week}" / "results.csv"`) inside the application's logging or data-storage loop. This eliminates the need for complex external logrotate configurations.

    ## Troubleshooting systemd PATH issues
    If a systemd-managed service (e.g., Hermes Dashboard) logs "binary not found in PATH", the service's environment `PATH` likely lacks the custom directory (e.g., `~/.local/bin`).
    - **Fix**: Edit the unit file (`/etc/systemd/system/<unit>.service`) and add/update the `Environment="PATH=..."` line in the `[Service]` section to include the missing path. Then run `sudo systemctl daemon-reload && sudo systemctl restart <unit>`.

    ## Configuration Migration (Deprecated .env)
    When warned about deprecated `.env` settings (e.g., `TERMINAL_CWD`):
    1.  Verify the canonical location for the new setting (`config.yaml`).
    2.  Update `~/.hermes/config.yaml` to include the new configuration.
    3.  Remove the deprecated line from `~/.hermes/.env`.

