---
name: juniper-ops
description: "Management and troubleshooting of Juniper PAN-OS/Junos devices. Covers BGP session auditing, routing table checks, and parsing nested Junos configuration blocks."
category: security
tags:
  - networking
  - juniper
  - junos
  - bgp
  - python
  - netmiko
---

# Juniper Junos Network Operations and Automation

This skill covers the workflows, commands, and programmatic parsing methodologies required to safely manage and audit Juniper (Junos) devices—specifically focusing on BGP routing, interface status, and nested bracket-based configuration parsing.

## Trigger Conditions
- Troubleshooting, auditing, or configuring BGP sessions on Juniper/Junos devices.
- Retrieving and listing active or down BGP neighbors, routing tables, or peer descriptions.
- Developing Python automation scripts using Netmiko/Paramiko to connect to Junos routers/switches.
- Reading or parsing Junos configuration blocks (bracket/curly brace nested syntax).

## Setup & Prerequisites (Non-privileged Python Environments)
When running inside isolated agent environments, standard packages like `netmiko` and `paramiko` may not be pre-installed, and global system installations (`pip install --system` or `pip install --user`) might fail due to lack of write access or system restrictions.

**Fastest and safest workaround using `uv`:**
1. Create a lightweight local virtual environment:
   ```bash
   uv venv /home/hermes/.venv
   ```
2. Rapidly install dependencies into that virtual environment:
   ```bash
   uv pip install --python /home/hermes/.venv/bin/python netmiko paramiko
   ```
3. Execute your automation script using the virtualenv's Python binary:
   ```bash
   /home/hermes/.venv/bin/python your_script.py
   ```

## Standard Troubleshooting & Verification Commands

| Operation | Command | Purpose |
| :--- | :--- | :--- |
| **BGP Summary** | `show bgp summary` | Fast overview of all peers, ASNs, flaps, and session status/uptime (Last Up/Dwn). |
| **BGP Neighbors** | `show bgp neighbor` | In-depth status of BGP neighbors, including configured features and descriptions. |
| **BGP Config** | `show configuration protocols bgp` | Review exact BGP config, peering groups, and descriptions. |
| **Active Routes** | `show route protocol bgp` | Display all routes received and active via BGP. |
| **Interface Status** | `show interfaces terse` | Quick overview of interface up/down states and IP addresses. |

## Authentication Pitfall: Password Failures
Some Junos environments have strict security policies that lock accounts (`Too many password failures`) if multiple SSH attempts are made in rapid succession.

**When experiencing authentication failures:**
1. **Manual Verification First:** Always verify access manually from your local shell (`ssh svc-backup@<IP>`) before relying on automation.
2. **Avoid Rapid Retries:** If you receive a 'Too many password failures' error, stop immediately. The system will likely require a cooling-off period before accepting further password-based authentication.
3. **SSH Config:** If automation is necessary, ensure your `~/.ssh/config` is configured to avoid aggressive retries or to use specific authentication methods that bypass manual password prompts where possible.
4. **Interactive vs. Non-Interactive:** Use interactive tools like `pexpect` or `netmiko` with `global_delay_factor` set to `2` or higher to handle slow device responses that might otherwise trigger false-positive authentication errors.

---


### The Bug
Inside a group block, there are sub-blocks like `family` or `multipath` that open and close their own curly braces:
```junos
group CORE-BGP-VRF-INET {
    family inet {
        unicast;
    }   # Naive parsers think this closing brace terminates the group CORE-BGP-VRF-INET!
    neighbor 200.7.13.237 { ... }
}
```
If your script uses a simple flag to detect group closure when encountering a `}` line, it will prematurely set `current_group = None` when parsing sub-blocks, thus skipping all subsequent neighbor definitions.

### The Solution: Stack-Based Block Parser
Always use a stack to track block context and brace depths. Below is a production-grade, battle-tested Python parser for Junos configuration blocks:

```python
import re

def parse_juniper_bgp_groups(config_text):
    groups = {}
    stack = []
    current_group = None
    current_neighbor = None
    
    lines = config_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        has_open = '{' in line
        has_close = '}' in line
        
        # Detect BGP group block start
        group_match = re.match(r"^group\\s+([^\\s{]+)", line)
        if group_match:
            current_group = group_match.group(1)
            groups[current_group] = {'description': None, 'neighbors': {}}
            stack.append(('group', current_group))
            continue
            
        # Detect BGP neighbor block start
        neighbor_match = re.match(r"^neighbor\\s+([^\\s{]+)", line)
        if neighbor_match and current_group:
            current_neighbor = neighbor_match.group(1)
            groups[current_group]['neighbors'][current_neighbor] = {'description': None}
            stack.append(('neighbor', current_neighbor))
            continue
            
        # Push non-group/non-neighbor blocks to stack to balance closing braces
        if has_open and not group_match and not neighbor_match:
            stack.append(('other', None))
            continue
            
        # Parse descriptions (cleaning up quotes)
        desc_match = re.match(r"^description\\s+([^;]+);", line)
        if desc_match:
            desc = desc_match.group(1).strip().strip('\"')
            if current_neighbor and current_group:
                groups[current_group]['neighbors'][current_neighbor]['description'] = desc
            elif current_group:
                groups[current_group]['description'] = desc
                
        # Pop from stack and restore state upon closing braces
        if has_close:
            if stack:
                ctx_type, ctx_val = stack.pop()
                if ctx_type == 'group':
                    current_group = None
                elif ctx_type == 'neighbor':
                    current_neighbor = None
                    # Fall back to parent group context
                    current_group = next((val for t, val in reversed(stack) if t == 'group'), None)
            continue
            
    return groups
```

## BGP Auditing Best Practice: Merging Summary and Config
On Junos, `show bgp summary` provides exact **uptime/session durations** but lacks descriptions, whereas `show bgp neighbor` or config commands contain **descriptions** but are highly verbose.
To construct a beautiful BGP audit report:
1. Run `show bgp summary` and parse active (`Established`/`Establ`) neighbors.
2. Run `show configuration protocols bgp` and parse group structure with the Stack-Based Parser.
3. Merge: If a neighbor lacks a direct description, look up its parent group's description, and fallback to the group's name.

This delivers comprehensive, readable reports to engineers on the status of active production sessions.
