# Troubleshooting: Nexus vPC Elephant Flow & Load Balancing

## Context
When troubleshooting latency on vPC bundles serving VMware DVS, standard algorithms (src-dst-ip) often fail to distribute traffic correctly if the workload is dominated by a few "Elephant Flows" (e.g., SQL replication between fixed IP pairs).

## Symptoms
1. **Output Drops:** Tail-drops on specific physical member interfaces while others are idle.
2. **Polarization:** 6x-10x throughput disparity between members of the same Port-Channel.
3. **Correlation:** Occurs with 'Active-Standby' DVS Teaming.

## Debugging Workflow
1. **Identify Member Load:** `show interface port-channel <ID> counters` / `show interface <Eth> counters`.
2. **Check Hash:** `show port-channel load-balance`.
3. **Validate Hash Logic (If supported):** Use `show port-channel load-balance hash interface <Po> src-ip <IP> dst-ip <IP>`. If not supported, use the physical interface counter delta over time.
4. **Elephant Flow Test:** SQL (TCP/1433) replication flows between fixed IPs are guaranteed to map to the same physical link.

## Pitfalls
- **vPC Restrictions:** Changes to load-balance hash are usually global; require change windows.
- **VMware Logic:** 'Source-mac-hash' on DVS locks traffic to a specific uplink; this 'pre-conditions' traffic before it hits the Nexus hash logic, often exacerbating polarization.
- **Firmware:** Older Nexus firmware may not support predictive hash CLI commands.

## Mitigation
- **Short-term:** Apply QoS 'priority-queue' for SQL port (1433) to protect against buffer tail-drops.
- **Medium-term:** Evaluate moving DVS to 'Route based on physical NIC load' (Requires Enterprise Plus).
- **Global Config:** Update to `port-channel load-balance hash-distribution src-dst-mixed-ip-port` (requires change window).
