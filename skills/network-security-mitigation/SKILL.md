---
name: network-security-mitigation
description: Patterns for remediating common Nessus/security findings in network infrastructure.
tags: [security, nessus, pci, nginx, palo-alto]
---

# Network Security Mitigation

This skill contains proven workarounds for common security scanner findings that don't require intrusive or breaking changes to core services.

## Web Server Password Auto-Completion
**Finding:** "Web Server Allows Password Auto-Completion" (e.g., NetBox, internal dashboards).
**Fix (Nginx):** Inject the `autocomplete="off"` attribute via `sub_filter` in your Nginx reverse proxy to avoid modifying the app source code, handling specific framework-generated attributes (like `username` and `current-password`).

```nginx
location / {
    sub_filter 'autocomplete="current-password"' 'autocomplete="off"';
    sub_filter 'autocomplete="username"' 'autocomplete="off"';
    sub_filter_once off;
    proxy_set_header Accept-Encoding ""; # Required to prevent Gzip encoding from breaking sub_filter
}
```

## SSH Weak Key Exchange Algorithms Enabled
**Finding:** "SSH Weak Key Exchange Algorithms Enabled" (Tenable/Nessus).
**Fix (OpenSSH):** Restrict `KexAlgorithms` in `/etc/ssh/sshd_config` (or `sshd_config.d/`) to remove SHA-1 and group-exchange variants, and disable GSSAPI Kex if necessary.

```ini
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp256,ecdh-sha2-nistp384,ecdh-sha2-nistp521,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512,diffie-hellman-group14-sha256
GSSAPIAuthentication no
```

## SSH Server CBC Mode Ciphers Enabled
**Finding:** "SSH Server CBC Mode Ciphers Enabled" (Tenable/Nessus).
**Fix (OpenSSH):** Restrict `Ciphers` in `/etc/ssh/sshd_config` to use only GCM and CTR modes.

```ini
Ciphers aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr
```

## ICMP Timestamp Request Remote Date Disclosure
**Finding:** "ICMP Timestamp Request Remote Date Disclosure" (Tenable). Output often reads "The remote clock is synchronized with the local clock" — that line is just confirming NTP works, it is NOT the vulnerability. The actual issue is the host answering ICMP Type 13 (Timestamp Request) with Type 14 (Timestamp Reply), leaking system clock remotely (fingerprinting/recon, low severity, no RCE).
**Root cause:** Linux kernel answers ICMP Timestamp natively; there is no dedicated `sysctl` for it (unlike `icmp_echo_ignore_all` for ping) — mitigation is filtering, not a kernel toggle.
**Decide where to filter first:** if the Tenable scanner reaches the host through a perimeter firewall (Palo Alto/F5), check whether the allow rule uses a generic `icmp`/`application: any` service instead of the specific `ping` App-ID — a generic ICMP allow lets Type 13/14 through along with Echo. Fixing the App-ID/service on that rule (deploy in log-only first, then enforce) is the correct systemic fix and avoids touching every host. Only fall back to a host-level rule if the scanner is on the same segment/VLAN as the target (perimeter firewall never sees that traffic).
**Host-level fallback (no dedicated firewall layer on the VM — iptables/nftables is the kernel's native packet filter, not an extra service):**
```bash
sudo iptables -I INPUT -p icmp --icmp-type timestamp-request -j DROP
sudo iptables -I OUTPUT -p icmp --icmp-type timestamp-reply -j DROP
```
**Persistence on modern Ubuntu/Debian (where `iptables-persistent` is absent or lacks candidate):**
Do not assume `/etc/iptables/rules.v4` is reloaded on boot. Use a lightweight, zero-dependency systemd oneshot unit:
```ini
# /etc/systemd/system/icmp-timestamp-filter.service
[Unit]
Description=Filter ICMP Timestamp Requests and Replies
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '/usr/sbin/iptables -C INPUT -p icmp --icmp-type timestamp-request -j DROP 2>/dev/null || /usr/sbin/iptables -A INPUT -p icmp --icmp-type timestamp-request -j DROP; /usr/sbin/iptables -C OUTPUT -p icmp --icmp-type timestamp-reply -j DROP 2>/dev/null || /usr/sbin/iptables -A OUTPUT -p icmp --icmp-type timestamp-reply -j DROP'

[Install]
WantedBy=multi-user.target
```
Enable via `sudo systemctl daemon-reload && sudo systemctl enable --now icmp-timestamp-filter.service`.

**Validation:**
- Test with nping: `sudo nping --icmp --icmp-type timestamp -c 2 <target_ip>` (must show 100% packet loss for timestamp).
- Test standard ping: `ping -c 2 <target_ip>` (must show 0% loss, validating normal ICMP echo is intact).
**Rollback:** `sudo iptables -D INPUT -p icmp --icmp-type 13 -j DROP` — safe, ICMP Timestamp isn't used by NTP, Zabbix ICMP echo monitoring, or standard `ping` (Type 8/0), so removing/adding this rule has no operational impact either way.

## SSL Hostname Mismatch (Internal Services)
**Finding:** "SSL Certificate with Wrong Hostname" or "Self-Signed Certificate" in proprietary components (e.g., SolarWinds agents).
**Pattern:** These are often internal identities, not user-facing web services.
**Approach:** 
1. Validate if the service is exposed to the internet.
2. If internal/isolated, present a formal technical justification to CyberSec for risk acceptance, highlighting that manual replacement of proprietary certificates breaks component trust/communication.
3. If public-facing, replace with standard organization-wide wildcard certs (e.g., `*.corp.io`) via the appropriate management portal (e.g., IIS Bindings).

## Apache Unused Default Service (AddType & mod_suexec)
**Finding:** "Apache Mixed Platform AddType Directive Information Disclosure" or "Apache mod_suexec Multiple Privilege Escalation Vulnerabilities" (Tenable).
**Context:** Often triggered by an unmanaged default Apache installation left running on port 80 while the actual application runs on dedicated application ports (e.g., 3000, 8420).
**Verification:** Inspect `/etc/apache2/sites-enabled/` and check if port 80 serves only the default distribution page (`Ubuntu: Apache2 Default Page` or `It works!`).
**Fix (Unused service):** Stop and disable the unit completely.
```bash
sudo systemctl disable --now apache2
```
**Fix (If Apache must remain active):** Disable `suexec` module and suppress banner disclosure:
```bash
sudo a2dismod suexec
# In /etc/apache2/conf-available/security.conf:
# ServerTokens Prod
# ServerSignature Off
sudo systemctl reload apache2
```

## Grafana Major Version Upgrade Safety Gate
**Finding:** "Grafana Labs Multiple Vulnerabilities" (requiring upgrade to >= 11.6.x or newer while host runs legacy 9.x/10.x).
**Pitfall:** Upgrading across multiple major versions (e.g., v9 -> v11) applies destructive schema migrations to SQLite `/var/lib/grafana/grafana.db`, which cannot be rolled back by merely downgrading the package if a dashboard or datasource fails.
**Procedure:**
1. **Cold backup first:** Always stop `grafana-server` and create timestamped copies of `/var/lib/grafana/grafana.db` and `/etc/grafana/` before invoking `apt-get install --only-upgrade grafana`.
2. **Validate critical datasources:** Ensure InfluxDB (InfluxQL) and Prometheus queries remain valid after migration; verify `/api/health` returns `200` with `database: "ok"`.
3. **Rollback plan:** Restore `grafana.db.bak` and re-pin package version if custom panel plugins or legacy queries break.

