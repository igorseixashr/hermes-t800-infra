# Case Study: BGP Session Down on AST-SP4-ADQ-CORE-01 (Megatelecom)
**Date:** May 24, 2026  
**Status:** Ongoing Carrier Issue  

---

### Incident Background
An eBGP session alert was triggered for the core switch **`AST-SP4-ADQ-CORE-01`** (Cisco Nexus 5672UP, IP `192.168.153.111`) located at site **Ascenty SP4**. The eBGP peer with **Megatelecom** (`10.153.255.82`, AS `64768`) went into `Idle` state on May 24, 2026, at approximately 02:59:46.

### Troubleshooting Execution & Commands Run

#### 1. Checking BGP State
```text
AST-SP4-ADQ-CORE-01# show ip bgp summary
...
Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
10.153.255.82   4 64768 8810684 8958742        0    0    0 02:31:00 Idle
```
*   **Observation:** State is `Idle` for over 2.5 hours. No prefixes are exchanged.

#### 2. Investigating BFD Neighbors
```text
AST-SP4-ADQ-CORE-01# show bfd neighbors
...
(Vlan1303 neighbor 10.153.255.82 is completely missing from the table)
```
*   **Observation:** The BFD session for `10.153.255.82` (Vlan1303) is completely absent. Log analysis from the event window shows BFD went down due to "Echo Function Failed" shortly before BGP transitioned to `Idle`.

#### 3. Checking Physical Interface
```text
AST-SP4-ADQ-CORE-01# show interface ethernet 1/18
Ethernet1/18 is up
  Dedicated Interface 
  Description: Link Megatelecom 32514624CIR01 - Passeio - 1Gbps
  Last link flapped 23week(s) 0day(s)
```
*   **Observation:** Physical port `Eth1/18` is strictly `UP`. No physical flaps or error counters are increments.

#### 4. LLDP Neighbors (Identifying local loop)
```text
AST-SP4-ADQ-CORE-01# show lldp neighbors interface ethernet 1/18
Device ID            Local Intf      Hold-time  Capability  Port ID  
HW67-OCO-ASCT-C02    Eth1/18         120        BR          XGigabitEthernet0/0/22
```
*   **Observation:** Port `Eth1/18` connects directly to local Ascenty datacenter switch `HW67-OCO-ASCT-C02`. This explains why the physical layer remains `UP`.

#### 5. MAC Address Table Analysis (Vlan 1303)
```text
AST-SP4-ADQ-CORE-01# show mac address-table vlan 1303
   VLAN     MAC Address      Type      age     Secure NTFY   Ports/SWID.SSID.LID
---------+-----------------+--------+---------+------+----+------------------
* 1303     00e0.fc09.bcf9    dynamic   40         F    F  Eth1/18
* 1303     8c60.4f91.eb81    static    0          F    F  Po1
```
*   **Observation:** We learn the MAC of the Ascenty switch (`00e0.fc09.bcf9`) but **fail to learn the MAC of the remote Megatelecom router**. 

#### 6. ARP Table Check
```text
AST-SP4-ADQ-CORE-01# show ip arp vlan 1303
IP ARP Table
Total number of entries: 0
```
*   **Observation:** No ARP entry for the peer. Ping requests to `10.153.255.82` fail because ARP cannot be resolved.

---

### Root Cause & Diagnosis
The physical interface `Eth1/18` is UP because the local physical connection to Ascenty's patch switch (`HW67-OCO-ASCT-C02`) is intact. However, the Layer 2 transport circuit `32514624CIR01` (Megatelecom) is **down or interrupted beyond the local patch panel**.

The remote router is completely unreachable. The peer's MAC is not being delivered to our core switch.

### Actions Taken
- Diagnosed via read-only credentials `svc-backup`.
- Formulated the exact carrier-fault diagnosis.
- Recommended immediate escalation to Megatelecom Support citing the circuit ID and ARP/MAC evidence.
