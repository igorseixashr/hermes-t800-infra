# BGP Troubleshooting: Cisco IOS-XE (Catalyst 8500/ASR)

## Idle State with 0.0.0.0 Identifier
When `show ip bgp neighbors <IP>` shows state `idle` and `Remote ID 0.0.0.0`, it indicates the router is not even attempting to open a TCP session.

### Common Causes
1. **No Route to Peer**: Check `show ip route <PEER_IP>`. If not present, BGP cannot initiate.
2. **Update-Source Down**: If using `update-source Loopback0`, and the loopback is down, the session stays idle.
3. **Admin Down**: The neighbor is explicitly `shutdown` in the config.
4. **VRF Mismatch**: Peer is in a VRF but the neighbor command is in the global instance (or vice versa).

### Validation Commands
```bash
show ip bgp neighbors <IP> | include state|ID
show ip route <IP>
show run | section neighbor <IP>
ping <IP> source <SOURCE_INT>
```
