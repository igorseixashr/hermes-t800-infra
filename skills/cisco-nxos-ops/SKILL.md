---
name: cisco-nxos-ops
category: devops
description: Management, troubleshooting, and operations on Cisco Nexus (NX-OS) switches, covering physical, L2, L3, BGP, and BFD layers.
---

# Cisco NX-OS Operations

## Troubleshooting: Nexus vPC Elephant Flow & Load Balancing
(See `references/nexus-vpc-elephant-flow.md`)

## SSL Certificate Management & Uptime
(See `references/nexus-ssl-cert-management.md`)

## Operational Procedures
- Nexus SSH troubleshooting: Use `-o RequiredRSASize=1024 -o IdentitiesOnly=yes -o PubkeyAuthentication=no`.
- Always verify LACP member loads with `show interface <Eth> counters` to identify elephant flows.

## Port-Channel/vPC Teardown + Reconfiguration (e.g. storage array remap)
(See `references/vpc-portchannel-migration.md` for the full sequence, pre-check commands, and a worked 4-switch example.)

Summary of the safe order of operations when retiring a port-channel/vPC to hand interfaces back for new config:
1. Pre-check first, always: `show running-config interface <eth>`, `show vpc brief`, `show port-channel summary interface port-channel <id>` — capture this output, it is the rollback reference.
2. If `show vpc brief` shows the Po as an active vPC: `no vpc <id>` on the port-channel BEFORE removing channel-group membership or deleting the Po. Apply per port-channel individually (`interface port-channel10` then `no vpc`, repeat for `port-channel15`) — do not assume `interface range port-channel10,15` is accepted (see pitfall below).
3. `no channel-group` on each physical interface (bare, no id needed) — `interface range Ethernet1/5-6` then `no channel-group` works fine for physical Ethernet interfaces. Then delete each Po individually: `no interface port-channel10` / `no interface port-channel15` — `no interface port-channel10,15` is rejected the same way.
4. `default interface <eth1> , <eth2>` to wipe the physical interface back to factory defaults (comma syntax for non-sequential ports, hyphen for ranges) — only then apply the new `switchport mode trunk` / vlan / mtu / speed / description block.
5. Validate with `show running-config interface`, `show interface <eth> status`, `show vpc brief`; only `copy running-config startup-config` after explicit OK.

Pitfalls learned:
- Never assume the new-config doc matches the current live state, even across "identical" vPC peer pairs — always diff the live pre-check (vlan, description, port index) against the requested target before generating the apply script. Divergences (e.g. peer switch using a different native VLAN, or the array-side port index shifting like eth14→eth8) have shown up repeatedly and must be surfaced to the user as an explicit yes/no confirmation, not silently applied.
- `show vpc brief` also surfaces unrelated pre-existing `down*`/`consistency failed` port-channels on the same switch — flag them as a separate finding, don't fold them into the current change's scope.
- User's preferred mode for this class of change (Nexus vPC/port-channel/interface rebuilds) is GUIDED, not autonomous: generate the full script, but the user runs each command themselves and pastes output back; do not execute directly against their infra even when asked to "gerar os scripts" (that means produce the script text, not execute it).
- `interface range` with a comma-separated list ONLY works reliably for physical interfaces (`Ethernet1/5-6` or `Ethernet1/5,Ethernet1/6`) and object types that natively support range grouping — it does NOT extend to `port-channel<N>,<M>` on all NX-OS platforms/builds: confirmed on live device (NX-OS on Nexus 9000, atl1-tor-13) that `interface range port-channel10,15` throws `Invalid interface format at '^' marker`. Same restriction applies to `no interface port-channel10,15` — the `no interface <obj>` form does not expand comma lists either. Always fall back to one `interface port-channelX` / `no interface port-channelX` block per port-channel; never state comma-list support for port-channels as fact without having it confirmed against the actual device output, since it varies by platform/train and a wrong guess costs the user a failed paste mid-change.
- `default interface` DOES accept a comma-separated list of full interface names (`default interface Ethernet1/5, Ethernet1/6`) — this is a different code path from `interface range` and is confirmed to work; don't conflate the two when advising syntax.