# vPC/Port-Channel Teardown for Interface Reconfiguration

Context: recurring task — a port-channel member interface (often a storage
array uplink, e.g. Pure Storage FC/eth over Ethernet) needs its port-channel
and vPC association removed so the physical interface can be reset and
given a brand-new access/trunk config (different VLAN, different array port
index after a cabling/controller remap).

## Full per-switch script template

```
! === PASSO 0: Pre-check (ALWAYS run first, keep the output as rollback reference) ===
show running-config interface Ethernet1/X
show running-config interface Ethernet1/Y
show running-config interface port-channelA
show running-config interface port-channelB
show vpc brief
show port-channel summary interface port-channel A
show port-channel summary interface port-channel B

! === PASSO 1: Remove vpc association FIRST if show vpc brief lists Po A/B as vPC ===
configure terminal
interface port-channelA
  no vpc A
interface port-channelB
  no vpc B

! === PASSO 2: Remove interfaces from channel-group ===
interface Ethernet1/X
  no channel-group A
interface Ethernet1/Y
  no channel-group B

! === PASSO 3: Delete the port-channels ===
no interface port-channelA
no interface port-channelB

! === PASSO 4: Reset physical interfaces to factory default ===
default interface Ethernet1/X , Ethernet1/Y

! === PASSO 5: Apply the new target config ===
interface Ethernet1/X
  description <new-desc>
  switchport mode trunk
  switchport trunk native vlan <new-vlan>
  spanning-tree port type edge trunk
  mtu 9216
  speed <new-speed>
  no shutdown

! === PASSO 6: Validate ===
show running-config interface Ethernet1/X
show running-config interface Ethernet1/Y
show interface Ethernet1/X status
show interface Ethernet1/Y status
show vpc brief

! === PASSO 7: Save only after explicit confirmation ===
copy running-config startup-config
```

## Worked example (Chicago/Atlanta Pure storage TOR migration, 2026-09)

4 switches, each with 2 interfaces to migrate off Po10/Po15:
- chi1-tor-15: Eth1/3 (Po10) + Eth1/4 (Po15) -> vlan 1138, speed 25000
- chi1-tor-16: Eth1/3 (Po10) + Eth1/4 (Po15) -> vlan 1140 (DIFFERENT from tor-15 despite being the vPC peer — confirmed intentional, not a typo)
- atl1-tor-13: Eth1/5 (Po10) + Eth1/6 (Po15) -> vlan 1070, speed 10000
- atl1-tor-14: Eth1/5 (Po10) + Eth1/6 (Po15) -> vlan 1080 + array port index changed eth15->eth31 (double change: vlan AND port index — required an explicit user confirmation before generating the final script, because the live pre-check disagreed with the original migration doc twice)

Lesson baked into the main SKILL.md: never silently trust the migration doc over the live pre-check output. Surface every mismatch as a blocking question.

## Rollback (any switch in this pattern)
Reapply the original block captured in PASSO 0 output:
`switchport access vlan X` (or the original trunk config) + `channel-group X mode active` + original description, then recreate `interface port-channelX` and `vpc X`.
