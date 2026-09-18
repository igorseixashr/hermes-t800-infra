# OWAMP & TWAMP RFC Summary

## OWAMP (RFC 4656) — One-Way Active Measurement Protocol

**Purpose:** Measure unidirectional delay, loss, reordering with high precision.

### Key Architecture

- **OWAMP-Control (TCP 861):** Client negotiates with Server to set up test sessions.
- **OWAMP-Test (UDP):** Sender → Receiver test packets with timestamps.
- **Roles:** Session-Sender, Session-Receiver, Server, Control-Client, Fetch-Client.

### Three Modes

| Mode | Security | Use Case |
|------|----------|----------|
| Unauthenticated (1) | None | Lab/trusted networks |
| Authenticated (2) | HMAC-SHA-256 | Production control path |
| Encrypted (4) | AES-CBC + HMAC | Hostile networks |

### Control Session Setup (§3.1)

1. Client opens TCP to server:port 861.
2. Server responds with **Greeting:** Modes, Challenge, Salt, Count (PBKDF2 iterations).
3. Client derives session key: `key = PBKDF2-SHA1(secret, salt, count, 16)`.
4. Client sends **Setup-Response** with chosen mode + integrity proof.
5. Server accepts; begins awaiting Request-Session commands.

### Test Session (§3.5)

**Request-Session message fields:**
- Command Number: 0 (OWAMP Request-Session)
- Sender IP/port, Receiver IP/port
- Start time (NTP 64-bit)
- Test duration, Timeout
- Packet size (16–65468 bytes; small packets fit ATM cells)
- Poisson mean interval (λ in microseconds)
- DSCP, Flags
- Session ID (128-bit)
- Shared secret seed (if authenticated)

**Poisson scheduling (§3.6):**
- Exponentially distributed inter-packet intervals with mean λ.
- Server generates seed → Client derives schedule deterministically.
- Allows replaying test with identical timing across runs.

### Test Packet Format (§4.1.2)

```
0                   1                   2                   3
0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                      Timestamp (NTP 64-bit)                   |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                   Error Estimate (Unauthenticated)            |
|                   or HMAC (Authenticated/Encrypted)           |
+- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+
|                        Padding                                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Receiver Behavior (§4.2)

- Listens on negotiated UDP port.
- Logs: Sequence, Timestamp (local NTP-synced), Sender Timestamp.
- Computes: One-way delay = (Receiver Timestamp) − (Sender Timestamp).
- Detects loss (gaps in sequence), reordering (seq < prev seq).

### Results Retrieval

**Fetch-Session (§3.9):**
- Client requests completed session results.
- Server returns statistics: min/max/median delay, loss count, reorder count.
- Results remain on server until explicitly cleared.

---

## TWAMP (RFC 5357) — Two-Way Active Measurement Protocol

**Purpose:** Measure round-trip delay via **Session-Reflector** (echoes packets back).

### Key Differences from OWAMP

| Aspect | OWAMP | TWAMP |
|--------|-------|-------|
| Port | TCP 861 | TCP 862 |
| Receiver Role | Session-Receiver (passive) | Session-Reflector (echo) |
| Results | Server stores metrics | Sender collects RTT only |
| Fetch-Client | Required | Not used |
| Clock Sync | Required on both ends | Not needed (reflector mirrors) |

### Control Session (§3.1)

- TCP connection to **port 862** (not 861).
- Same modes, PBKDF2 key derivation as OWAMP.
- Simpler: no DSCP/PHB negotiation; Reflector has no result storage.

### Request-TW-Session (§3.5)

**Command Number: 5** (vs. 0 for OWAMP Request-Session).

```
+---+---+---+---+---+---+---+---+
| Command=5 | Unused       | IPVN|
+---+---+---+---+---+---+---+---+
| Conf-Sender | Conf-Reflector  |
+---+---+---+---+---+---+---+---+
| ... Session parameters (sender addr, port, etc.) ...
+---+---+---+---+---+---+---+---+
```

### Reflector Behavior (§4.2)

On receipt of test packet:
1. Copy Sender's Sequence Number.
2. Generate Reflector Timestamp (local clock, no sync needed).
3. Return packet immediately (small processing delay ≈ reflector overhead).
4. **Do NOT** store results; sender measures RTT directly.

### Test Packet Exchange

**Sender → Reflector:**
- Sequence, Sender Timestamp, Padding

**Reflector → Sender:**
- Sequence (copied), Sender Timestamp (copied), Reflector Timestamp, Error Estimate

**Sender metrics:**
- Round-trip delay = (Arrival Time) − (Send Time)
- Reflector processing delay ≈ (Reflector Timestamp) − (Sender Timestamp) from previous hop
- Handles reordering via sequence check.

### TWAMP-Light (Appendix I)

Simplified mode: Reflector configured via non-standard means (SSH, SNMP, etc.); no TWAMP-Control.
- Reduces dependencies for constrained environments.
- Requires out-of-band authentication of reflector config.

---

## Security Considerations

### OWAMP/TWAMP Encryption (§6)

- **HMAC:** Covers all data sent since previous HMAC (rolling authentication).
- **AES-CBC:** Encrypts HMAC payload; IV derived from counter.
- **Key derivation:** PBKDF2-SHA1 with server-supplied salt and iteration count.

### Covert Channels (§6.3)

- Packet size variation can encode side-channel data.
- Use fixed packet sizes in encrypted mode.

### Resource Limits (§6.5)

- Server should track active sessions per client.
- Expunge stale sessions after 30 minutes idle (default).
- Prevent unbounded memory via rate limiting.

---

## Appendix: Test Vector (Exponential Deviates)

OWAMP defines pseudo-random exponential deviate generation for Poisson intervals.

**Example seed (RFC 4656 Appendix B):**
```
SID = 0x2872979303ab47eeac028dab3829dab2
SUM[1000000 deviates] = 0x000f4479bd317381 (≈1000569.74 sec)
```

All implementations MUST produce identical deviates from identical seeds (enables reproducible testing).
