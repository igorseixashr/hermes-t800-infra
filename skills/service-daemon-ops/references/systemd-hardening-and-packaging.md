# systemd Hardening & Packaging an Unversioned App

Workflow for taking an in-production systemd app that nobody versioned, auditing
it, and committing it to the correct repo with a sandboxed unit file. Distilled
from packaging a Streamlit RSFN probe dashboard (Enterprise/Core, `dc1-tmp-bank-01`).

## 1. Inspect (read-only, never change prod)

```bash
# What listens on the port?
sudo ss -ltnp | grep <port>            # -> users:(("<proc>",pid=N,fd=...))
# Which unit + its file?
systemctl show <svc> -p FragmentPath --value
cat "$(systemctl show <svc> -p FragmentPath --value)"
systemctl status <svc> --no-pager -l | head -20
# Confirm the app's working dir (relative paths in code depend on this)
sudo ls -la /proc/<pid>/cwd
# Pin dependency versions from the live venv
sudo /opt/<app>/venv/bin/pip freeze
sudo /opt/<app>/venv/bin/python3 --version
# Is the deploy dir already a git repo?
sudo git -C /opt/<app> rev-parse --is-inside-work-tree 2>/dev/null || echo "NOT A REPO"
```

Read the actual app source before writing anything — the committed code must be
**faithful to what runs in prod**, not a rewrite.

## 2. Security audit

```bash
systemd-analyze security <svc> --no-pager | head -50
```

`✗` lines are missing protections. A unit with no hardening directives scores
~9.6/10 ("UNSAFE"). Common red flags: `NoNewPrivileges=`, `ProtectSystem=`,
`RestrictAddressFamilies=`, `PrivateTmp=` all unset; files in `/opt/<app>` at
`777`; service bound to `0.0.0.0:<port>` with no auth.

## 3. Reusable hardened unit template

Adapt `User`/`Group`/`WorkingDirectory`/`ExecStart`/`ReadWritePaths`. This set
keeps a Python network-probe app (TCP/ping/traceroute/DNS) working while closing
almost every `systemd-analyze` finding:

```ini
[Service]
Type=simple
User=<svcuser>
Group=<svcgroup>
WorkingDirectory=/opt/<app>
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/<app>/venv/bin/<cmd> ...
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# --- Hardening (systemd sandbox) ---
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/<app>          # ONLY the dirs the app writes (CSVs, logs)
ProtectHome=yes
Environment=HOME=/opt/<app>        # see ProtectHome gotcha below
ProtectControlGroups=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
ProtectKernelLogs=yes
ProtectClock=yes
ProtectHostname=yes
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
RestrictAddressFamilies=AF_INET AF_INET6
SystemCallArchitectures=native
RemoveIPC=yes
```

**Gotcha — ICMP/traceroute under sandbox:** `ping` and `traceroute` do NOT need
root or `CAP_NET_RAW` when the kernel allows unprivileged ICMP sockets. Check:

```bash
sysctl net.ipv4.ping_group_range   # "0  2147483647" == open for everyone
```

If open, the template above (no caps, only AF_INET/AF_INET6) is fine. If you
add `RestrictAddressFamilies` without AF_INET you break the sockets; if the
range is closed you'd need `AmbientCapabilities=CAP_NET_RAW` instead.

**Gotcha — `ProtectHome=yes` breaks apps that write to `~/`.** Many runtimes
write under the service user's home: Streamlit → `~/.streamlit/machine_id_v4`,
pip/uv caches → `~/.cache`, matplotlib → `~/.config`, etc. `ProtectHome=yes`
makes `/home` inaccessible, so the app either errors or silently regenerates
state on every boot. Check the service user's home BEFORE applying:

```bash
getent passwd <svcuser>                        # find its home dir
sudo find /home/<svcuser> -maxdepth 2 -type f  # what does it actually keep there?
```

Fix WITHOUT weakening the sandbox: point `HOME` into the already-writable
`ReadWritePaths` dir — `Environment=HOME=/opt/<app>` — and migrate the existing
state file so a stable id isn't lost:

```bash
sudo mkdir -p /opt/<app>/.streamlit
sudo cp -np /home/<svcuser>/.streamlit/machine_id_v4 /opt/<app>/.streamlit/ || true
sudo chown -R <svcuser>:<svcgroup> /opt/<app>/.streamlit
```

This keeps `ProtectHome=yes` AND keeps the app working. (Real case: Streamlit
RSFN dashboard; without this it would warn/regen its machine id every restart.)

Validate syntax locally before committing:

```bash
systemd-analyze verify deploy/<svc>.service   # "not executable" is fine if venv absent here
```

## 4. Package to the TARGET repo's conventions

Do not impose your own layout. Read a sibling component in the repo and mirror
its structure exactly:

```bash
git -C <repo> ls-tree -r --name-only origin/main -- <sibling-dir>
git -C <repo> show origin/main:<sibling-dir>/install.sh
git -C <repo> show origin/main:<sibling-dir>/.gitignore
```

Typical corp `fpdc-network` component layout to replicate:
`<app>/{<main>.py, requirements.txt (pinned), install.sh, uninstall.sh,
deploy/<svc>.service, *.csv.sample / *.txt.sample, .gitignore, README.md}`.

- `install.sh` idempotent: system deps → service user → copy app (overwrite
  code, `copy_if_absent` for config) → venv + `pip install -r requirements.txt`
  → install unit → `daemon-reload`/`enable`/`restart` → post-check (curl local
  endpoint). Apply `chmod 0750` dir / `0640` files — never leave 777.
- `.gitignore` excludes runtime CSVs/logs AND live config (commit only `.sample`).
- **Embed the improvement report inside the README** so it travels with the code.
- Validate before commit: `python3 -m py_compile *.py`, `bash -n *.sh`.
- Remove any `__pycache__` the compile step created before `git add`.

## 4b. Fixing the app's code before versioning (when asked to "corrigir e subir")

A follow-up request is often "fix what you can, then version it" — frequently
on an app that is **being deprecated** in favor of another. Apply YAGNI hard:

- **Scope by lifecycle.** If the app is on its way out, fix only the **contained,
  low-risk** items (the ones whose blast radius is one function) and leave
  structural items as documented recommendations. Do NOT rearchitect a dying
  app. State this trade-off in the commit + README.
  - Fix: bare `python` → `sys.executable` (script shelling to its own venv);
    sequential probes → `ThreadPoolExecutor`; unbounded CSV → simple row cap.
  - Leave as recommendation: auth/exposure on `0.0.0.0` (needs a network
    decision), UI/event-loop rearchitecture, converging overlapping tools.

- **Parallelization WITHOUT a write race.** When converting a per-item loop that
  *each worker writes the CSV itself* into a `ThreadPoolExecutor`, do NOT let
  every thread append to the same file — that races. Refactor the worker to
  **return its row** and do a single write in `main` after the pool drains:
  ```python
  with ThreadPoolExecutor(max_workers=min(N, len(targets))) as ex:
      rows = list(ex.map(check_one, targets))
  with open(CSV, "a", newline="", encoding="utf-8") as f:
      csv.writer(f).writerows(rows)
  ```
  Then **delete the now-orphaned per-item writer** (dead code) and grep to
  confirm nothing else calls it.

- **Bounded history without a rotation rewrite.** A full hierarchical log
  rotation is overkill for a dying app. A `cap_history(path, max_rows)` that
  reads the CSV, keeps header + last `max_rows` data rows, and rewrites — called
  once at the end of each cycle — is enough. Keep most-recent rows.

- **Validate the logic without the live deps/network.** The packaging host has
  no `streamlit`/`dnspython` and no network to the targets. Still prove the
  changed logic: `python3 -m py_compile *.py`, then drive the pure functions
  with stub modules. Stub a package tree so submodule attribute access works:
  ```python
  import sys, types
  dns = types.ModuleType("dns"); sys.modules["dns"] = dns
  for sub in ["message","query","rdatatype","exception"]:
      m = types.ModuleType("dns."+sub); sys.modules["dns."+sub] = m
      setattr(dns, sub, m)              # parent must expose submodule as attr
  ```
  Test `cap_history` for: truncation to N, idempotency (re-run is a no-op),
  small-file no-op. Test the pool with a sleeping fake resolver to confirm
  wall-time drops (20×0.2s: ~4s sequential → ~0.2s parallel).
  - **Pitfall:** do NOT `os.chdir()` into a tmpdir inside an `execute_code`/
    inline `python -` heredoc — it broke `get_hermes_home()` resolution
    ("Could not determine home directory"). Pass explicit paths to the function
    under test instead of changing cwd.

## 5. Safety boundary (state it explicitly to the user)

Versioning + the recommendation report are SAFE (no prod impact). Applying the
hardened unit, the `chmod` correction, and any restart are PROD CHANGES that
belong in a maintenance window with a rollback plan — do NOT do them as part of
the versioning task. Offer to prepare a separate apply+rollback plan.

## 6. Applying hardening to the LIVE service (when the user authorizes prod)

Once the user explicitly says "apply in prod now", run this ordered, reversible
procedure. Keep `git` and prod in sync — if the apply reveals a unit fix (e.g.
the `HOME` gotcha), commit it to the repo too so they don't diverge.

1. **Pre-flight (read-only).** Re-confirm current state and check the
   `ProtectHome`/`HOME` gotcha for THIS service user before anything mutates:
   `getent passwd <svcuser>`, look for `~/.streamlit` / `~/.cache` / etc.,
   `md5sum` the live code, note `ActiveEnterTimestamp`.
2. **Upload new artifacts to `/tmp` on the host** (`scp` the `.py` + the
   `.service`). Don't overwrite `/opt/<app>` yet.
3. **Backup with a timestamp** into a dir the service ignores
   (`/opt/<app>/.backup-<YYYYmmdd-HHMMSS>/`): copy old code, old unit, and a
   `perms_before.txt` snapshot (`ls -la`). `md5sum` the backup to prove it
   matches live. This is the rollback source.
4. **Apply code + permissions.** `install -m 0640 -o <user> -g <group>` the new
   `.py`; fix 777 → `0750` dir / `0640` files (include the `venv` if it's 777);
   remove stray root-owned backups and `__pycache__`; set up `HOME=<app dir>`
   `.streamlit` per the gotcha above.
5. **Swap the unit + reload.** `install -m 0644 -o root -g root` the unit;
   `systemd-analyze verify` it; `systemctl daemon-reload`; `systemctl restart`;
   `sleep 4`; `systemctl is-active`.
6. **Verify — four checks, all must pass:**
   - Port up: `ss -ltnp | grep <port>`
   - HTTP: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/`
     (Streamlit also has `/_stcore/health`)
   - Score dropped: `systemd-analyze security <svc> | tail -1` (saw 9.6→5.3)
   - `NRestarts == 0` and journal has no errors.
7. **Functional proof UNDER the sandbox (the check people skip).** A green
   `is-active` only means the process started — prove the app's real work still
   runs with the restrictions on. Run one real cycle as the service user, in the
   service's `WorkingDirectory`, with the same `HOME`:
   ```bash
   sudo -u <svcuser> sh -c "cd /opt/<app> && HOME=/opt/<app> ./venv/bin/python <smoke>.py"
   ```
   For a network probe: assert TCP/ping/traceroute/DNS all succeed (e.g. 5/5).
   **Pitfall:** the app uses RELATIVE paths from `WorkingDirectory` — if you run
   the smoke test from the wrong cwd you get `PermissionError: targets.csv`,
   which is a test artifact, NOT a sandbox failure. Always `cd /opt/<app>` first.
8. **Rollback (keep ready, state it to the user):** restore the unit + `.py`
   from `.backup-<ts>/`, `daemon-reload`, `restart`. Leave the backup dir on the
   host through an observation period before removing.

## Improvement-report skeleton (order by risk)

- **Alta (⚠️ security):** world-writable deploy dir (777), unit with no
  hardening, listener on `0.0.0.0` with no auth.
- **Média (🔧):** sequential probes that should be `ThreadPoolExecutor`,
  unbounded history CSVs (need rotation), config/owner mismatch.
- **Evolução (📈):** converge overlapping tools on the same host, Prometheus
  metrics for Zabbix/Grafana, use `sys.executable` not bare `python` when a
  script shells out to its own venv.
