---
name: cisco-catalyst-mgmt-vrf-tftp
category: devops
description: Fix TFTP failures on Cisco switches using Mgmt-vrf.
---

# Cisco Catalyst Mgmt-vrf TFTP Fix

## Problem
Cisco Catalyst switches running IOS-XE with a dedicated management VRF (`Mgmt-vrf` on `GigabitEthernet0/0`) fail to initiate TFTP transfers (e.g. `copy tftp`) to management jump hosts or servers, even when ping over the VRF works.

## Root Cause
The switch's control plane does not automatically bind TFTP traffic to the management source interface (`GigabitEthernet0/0`) inside the `Mgmt-vrf`, causing packets to drop or use incorrect parameters.

## Solution Steps
1. Ensure the management interface and VRF route are active:
   ```cisco
   ip route vrf Mgmt-vrf 0.0.0.0 0.0.0.0 <gateway_ip>
   ```
2. Bind the TFTP source interface to the management interface:
   ```cisco
   configure terminal
   ip tftp source-interface GigabitEthernet0/0
   end
   ```
3. Execute the transfer specifying the VRF if required:
   ```cisco
   copy tftp://<server_ip>/<file> bootflash:<file>
   ```
