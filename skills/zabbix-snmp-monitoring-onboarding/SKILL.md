---
name: zabbix-snmp-monitoring-onboarding
category: devops
description: Use when a new Zabbix SNMP host has no data, only ICMP.
---

# Zabbix SNMP Device Onboarding — Troubleshooting

## Symptom pattern that triggers this workflow
A device was just added to Zabbix for SNMP monitoring. In Latest Data, the
`Reachable` (ICMP) item has data, but every SNMP-sourced item (Memory,
CPU, Interfaces, Uptime, etc.) shows "no data". This pattern isolates the
problem to SNMP authentication/config on the device — NOT network
reachability, NOT the Zabbix template, and NOT proxy connectivity. Don't
chase ping/firewall/proxy theories when the ICMP item already succeeds.

## Diagnostic sequence
1. In Zabbix, open the host's SNMP interface config: security level
   (authPriv / authNoPriv / noAuthNoPriv), auth protocol (SHA/MD5), priv
   protocol (AES/DES), and the `{$SNMPV3_AUTHPASS}` / `{$SNMPV3_PRIVPASS}`
   macros. These must match what actually exists on the device — Zabbix
   macros only hold values, they don't create the device-side user.
2. Find a KNOWN-GOOD reference device on the same vendor/platform that is
   already monitored successfully. Run the same read-only commands on both
   the broken device and the reference device, side by side. Diffing
   against a working peer is far faster than guessing at SNMPv3 syntax.
3. Cisco IOS/NX-OS commands to compare:
   - `show snmp user` — does the monitoring user (e.g. `zbx`) exist at all?
     Check Group-name, Authentication Protocol, Privacy Protocol match the
     reference device exactly.
   - `show snmp group` — for a user configured with `auth priv`, the group
     needs BOTH a `security model: v3 auth` entry AND a `security model:
     v3 priv` entry. A device that only has the `v3 auth` entry (missing
     `v3 priv`) will still fail authPriv binds even though the user exists
     and looks correctly configured — this exact partial-group state has
     been seen in production and is easy to miss on a quick glance.
4. Fix on the device (values must match the Zabbix host's macros exactly):
   ```
   snmp-server group MONITORING v3 priv
   snmp-server user zbx MONITORING v3 auth sha <authpass_from_macro> priv aes 128 <privpass_from_macro>
   ```
   Re-run `show snmp group` / `show snmp user` and confirm the output now
   matches the reference device 1:1 (same protocols, same group entries).
5. End-to-end validation BEFORE waiting on the next Zabbix poll cycle —
   run from the Zabbix server itself:
   ```
   snmpwalk -v3 -u zbx -l authPriv -a SHA -A '<authpass>' -x AES -X '<privpass>' <device_ip> sysDescr.0
   ```
   A successful sysDescr response confirms the fix; then force a manual
   check in Zabbix (`Check now`) rather than waiting for the scheduled poll.

## Pitfalls
- Don't stop at "user exists" — an existing user with an incomplete group
  (missing the priv-level entry) looks fine at a glance but still fails.
- Always pull the auth/priv values from the Zabbix macros, never invent or
  reuse a password from another device — mismatch = silent auth failure,
  no useful error on the Zabbix side beyond "no data".
