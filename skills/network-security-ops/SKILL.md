---
name: network-security-ops
description: Management, troubleshooting, and security auditing for network infrastructure, including firewalls (Palo Alto, Fortinet), load balancers (F5), and web servers (NGINX).
---

# Network Security Operations

This skill serves as the umbrella for managing and auditing enterprise network infrastructure.

## 1. Firewall Operations
- **Palo Alto (PAN-OS):** Use `mcp_palo_mcp_*` tools for policy/Panorama management.
- **Fortinet (FortiGate):** Use `mcp_fortigate_mcp_*` tools for FortiOS REST API/VDOM-aware operations.
  - *Key Concepts:* VDOM-aware operations are case-sensitive. Use `discover_vdoms` if 404/403 errors occur.
  - *Host Key Issues:* If SSH fails with `Bad server host key: Invalid key length`, the switch is likely using a legacy/weak RSA host key (e.g., 512-bit). Do NOT force insecure SSH flags on the switch if possible. If you MUST bypass, use:
    ```bash
    ssh -o RequiredRSASize=1024 -o IdentitiesOnly=yes -o PubkeyAuthentication=no -o PreferredAuthentications=password user@host
    ```
    This bypasses the modern OpenSSH security block on weak keys and disables public key attempts which often trigger 'Too many authentication failures' on legacy SSH servers.
  - *Connectivity/Auth:* If MCP server times out or auth fails, verify:
    1. Host accessibility (ping/traceroute).
    2. Correct service account vs. temporary credentials.
    3. Privilege level (level 15 access is required for IOS-XE show/config commands; if you hit 'Authentication failed' on `show` commands but the SSH login itself succeeded, the user lacks elevation/privilege).
    4. Terminal/PTY settings (SSH tools work best with PTY enabled).
    5. VDOM-awareness (for FortiGate/F5, VDOM/Partition mismatches are a common source of 403/404).
    6. *FortiGate Pitfall:* If connection fails on a known valid device, perform a `test_device_connection` first. If it fails, report the error immediately to the user rather than retrying indefinitely or assuming service account permissions are the issue. Do not add the device and immediately try to query it without verifying the connection is healthy.

## 2. Load Balancing (BIG-IP LTM)
- Use `mcp_f5_mcp_*` tools for pool, virtual server, and iRule management.
- See `references/f5-troubleshooting.md` for connectivity workarounds and common alert workflows.

## 3. Web Server & Security Auditing
- **NGINX:** Lifecycle management and configuration auditing (including CVE remediation).
  - *Audit:* Always run `nginx -t` before reloads.
  - *Password Autocomplete:* To resolve Nessus vulnerability 'Web Server Allows Password Auto-Completion' (/login/), inject the attribute via Nginx `sub_filter`:
    ```nginx
    sub_filter '<input type="password"' '<input type="password" autocomplete="off"';
    sub_filter_once off;
    ```
    *Ensure `http_sub_module` is enabled (check via `nginx -V`).*

## 4. Troubleshooting Flow (Deep Dive)
- **Step 1 (Context):** Search for the device in NetBox (`netbox_mcp_search_objects` or `get_devices`).
  - If found: Attach NetBox metadata (Role, Site, IP, Serial) to the context.
  - If NOT found: Flag as "Device not in NetBox", but proceed with the alert information provided.
- **Step 2 (Validation):** Attempt live connection (SSH/API) to the device regardless of NetBox status to validate the alert telemetry.
- **Step 3 (Analysis):** Combine (NetBox Context + Alert Data + Live Telemetry) to formulate the technical analysis.
- **Step 4 (Reporting):** Provide the analysis with clear indications of what was gathered from NetBox vs. what was gathered from the device.

## 4b. Diagnosing Blocked Reachability (ICMP-up / TCP-down)

When a target host is unreachable, classify the failure BEFORE assuming bad
credentials. A host that answers ping but refuses every TCP port is almost
always a firewall dropping SYN from your source — not a wrong password.

Diagnostic sequence (run from the source host):
1. **ICMP reachability:** `ping -c 3 -W 2 <host>`. If it replies, the host is
   alive and L3 routing works. Note the TTL to estimate hop distance.
2. **TCP port probe (no nmap needed):** loop with bash `/dev/tcp`:
   `timeout 4 bash -c "cat < /dev/null > /dev/tcp/<host>/<port>"` → exit 0 =
   open, non-zero = closed/filtered. Probe SSH (22 + alts 2222/2022/22022)
   AND the service ports you expect (e.g. ES 9200/9300, Kibana 5601). If ALL
   ports filter while ICMP passes → firewall block on your source IP.
3. **Comparative traceroute (pinpoint the drop hop):** run ICMP and TCP side
   by side: `traceroute -I -n <host>` vs `sudo traceroute -T -p 22 -n <host>`.
   The TCP trace dies (`* * *`) at the hop AFTER the firewall; the ICMP trace
   reaches the destination. The last responding hop on the TCP trace is your
   block point — name it in the report.

**Consent rule (production change):** opening a firewall rule to grant
*yourself* (the Hermes host) access to a target is a production change. Do NOT
do it unilaterally. Report the diagnosis with evidence, then offer options and
wait for the user: (a) open a minimal staged rule (src=Hermes host, dst=target,
specific TCP port) committed only on their OK; (b) ProxyJump through an existing
bastion that already reaches the segment; (c) confirm a non-standard SSH port.

Detailed recipe + a real transcript: `references/blocked-reachability-diag.md`.

## 5. Automated Server Hardening
- **Objective:** Automate SSH access and privilege escalation on new infrastructure.
- **SSH/Sudo Workflow:** 
  1. **SSH Access:** Add agent public key (via `~/.ssh/id_rsa.pub`) to `~/.ssh/authorized_keys` with standard 0700/0600 permissions.
  2. **Privilege Escalation:** Create a dedicated file in `/etc/sudoers.d/` (e.g., `/etc/sudoers.d/<user>-nopasswd`) rather than modifying the main `/etc/sudoers` file. Set permissions to 0440.
  3. **Verification:** Always confirm `hostname`, `whoami`, and `sudo id` immediately after configuration to verify user identity and sudo access before declaring success.
