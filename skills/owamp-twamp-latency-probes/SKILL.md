---
name: owamp-twamp-latency-probes
description: Measure one-way/round-trip latency independently via OWAMP/TWAMP.
version: 0.1.0
author: Hermes
metadata:
  hermes.tags: [OWAMP, TWAMP, Paris-Traceroute, Latency, Probes, Measurement]
---

# OWAMP/TWAMP Latency Probe Design

Protocol toolkit for measuring **one-way delay (OWAMP)** and **round-trip delay (TWAMP)** with independent path analysis. Includes Paris Traceroute for load-balanced path detection.

Does NOT provide: CLI tools (install separately), server/client implementations (framework only), real-time dashboards. Does NOT replace production monitoring — use for enrichment and targeted diagnostics.

## When to Use

- Need unidirectional latency metrics (not just round-trip).
- Diagnosing multi-path load balancing (ECMP/LB) affecting measurements.
- Building custom probe agents for latency enrichment pipelines.
- Measuring metrics across different DSCPs/QoS classes.
- Require timestamp synchronization via GPS/NTP for accuracy.

## Prerequisites

- Linux/macOS system with clock source: GPS/NTP (stratum 1 preferred) or CDMA.
- `python3` with type hints support.
- TCP port 861 (OWAMP) / 862 (TWAMP) accessible on target endpoints.
- Optional: `paris-traceroute` binary; `tcpdump` for packet capture.
- Shared secret for authenticated/encrypted modes (pre-shared or derived via PBKDF2).

## How to Run

1. **Understand the protocols:** Load OWAMP (RFC 4656) and TWAMP (RFC 5357) reference docs.
2. **Choose measurement type:**
   - **One-way (OWAMP):** Unidirectional delay + loss. Requires synchronized clocks.
   - **Two-way (TWAMP):** Round-trip delay. No clock sync needed; reflector echoes packets.
   - **Path isolation (Paris Traceroute):** Map ECMP-balanced routes per flow tuple.
3. **Build probes:** Use templates in `scripts/` for sender/reflector logic.
4. **Enrich tools:** Integrate latency vectors into your monitoring pipeline.

## Quick Reference

| Component | RFC | Port (TCP) | Purpose |
|-----------|-----|------------|---------|
| OWAMP-Control | 4656 | 861 | Session setup, results fetch |
| OWAMP-Test | 4656 | UDP (negotiated) | Test packets (unidirectional) |
| TWAMP-Control | 5357 | 862 | Session setup (two-way) |
| TWAMP-Test | 5357 | UDP (negotiated) | Test packets (echo + reflect) |
| Paris Traceroute | — | ICMP/UDP | Path discovery with flow hash |

**Key modes:** Unauthenticated (Mode 1), Authenticated (Mode 2), Encrypted (Mode 4).

## Procedure

### 1. OWAMP One-Way Latency Measurement

**Hypothesis:** Measure sender → receiver delay independently, accounting for ATM SAR and per-hop behavior (PHB).

**Control flow (TCP 861):**
- Client → Server: Setup request with passphrase (if authenticated).
- Server → Client: Greeting (modes, salt, key derivation params).
- Client: Derives session key via PBKDF2 (SHA-1, HMAC).
- Client ↔ Server: Negotiate sender/receiver addresses, port, packet size, Poisson interval, DSCP.

**Test flow (UDP):**
- Sender emits test packets at exponentially distributed intervals (Poisson λ).
- Each packet: 16-byte OWAMP header + payload (adjustable for ATM).
- Receiver: Logs sequence, timestamps (NTP-synced), sequence gaps.
- Results: One-way delay distribution, loss, reordering (no round-trip noise).

**Advantages:** True one-way metrics. Decouples path asymmetry.
**Constraints:** Requires GPS/NTP sync on both ends; UDP test packets must traverse firewalls; small packets (<64B) fit ATM cells.

### 2. TWAMP Round-Trip Measurement

**Hypothesis:** Measure round-trip delay via packet reflection (Session-Reflector echoes Sender's packets).

**Control flow (TCP 862):**
- Simpler than OWAMP: Control-Client ↔ Server (no separate Fetch-Client).
- Session-Reflector does NOT store results; echoes immediately.
- No DSCP/PHB negotiation (simplified).

**Test flow (UDP):**
- Sender: Emits test packet with Sequence + Timestamp.
- Reflector: On receipt, immediately returns packet with Reflector Timestamp + Timestamp field copied (or zeroed, based on mode).
- Sender: Collects round-trip delay, reordering.

**Advantages:** No clock sync at reflector. Simpler deployment. Familiar (like ping).
**Constraints:** Measures round-trip only; path asymmetry hidden; reflector CPU overhead per packet.

### 3. Paris Traceroute for Load-Balanced Path Discovery

**Hypothesis:** Detect which upstream router uses ECMP by varying packet header fields (src port, dst port, flow label, DSCP).

**Mechanism:**
- Vary flow tuple (5-tuple hash) while incrementing TTL.
- If router uses consistent hashing, packets with same tuple hash → same path → same downstream routers.
- If routers differ, ECMP is active at that hop; repeat with different tuples to enumerate all branches.

**Invocation:**
```bash
paris-traceroute -A icmp|udp|tcp [--sport SRC] [--dport DST] TARGET
```

**Output interpretation:**
- Each route shown as separate branch.
- Repeated tuple fields (e.g., sport) force consistent ECMP path per branch.

## Pitfalls

1. **Clock skew:** OWAMP requires ≤1ms skew for accurate one-way delay. NTP may not suffice; GPS/CDMA needed.
2. **Firewall filtering:** UDP test traffic on ephemeral ports often blocked. Pre-negotiate port ranges; use TCP mode if available.
3. **Encryption overhead:** AES-CBC adds ~12% CPU overhead. Use unauthenticated mode for high-frequency probes if acceptable.
4. **Packet loss in analysis:** OWAMP/TWAMP include loss in results; don't confuse with network loss — test packets themselves may be dropped by firewalls.
5. **Paris Traceroute limitations:** Cannot exceed destination's TTL; unreachable hops collapse into "*". Some routers ignore flow-hash variation (no ECMP).
6. **Reflector availability:** TWAMP Reflector must remain on-path; NAT/load balancers may remove it between bidirectional sessions.

## Verification

**OWAMP readiness:**
```bash
# Check clock source (should be GPS/NTP stratum 1)
ntpstat
# Verify port 861 listening
ss -tulnp | grep 861
```

**TWAMP readiness:**
```bash
# Verify port 862 listening
ss -tulnp | grep 862
# Test round-trip with standard reflector
twamp -c <reflector-ip> -n 100
```

**Paris Traceroute:**
```bash
# Enumerate paths to target, varying sport to force ECMP diversity
paris-traceroute -A udp --sport 1024 TARGET
```
