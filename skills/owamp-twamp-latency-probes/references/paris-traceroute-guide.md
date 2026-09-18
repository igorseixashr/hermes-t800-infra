# Paris Traceroute — Load-Balanced Path Discovery

**Problem:** Classic traceroute fails when routers use ECMP (Equal-Cost Multi-Path).

## Issue with Classic Traceroute

In ECMP networks, different packets in a single traceroute may follow different paths because:
- Router load-balances on **5-tuple hash** (src IP, dst IP, src port, dst port, protocol).
- Each TTL increment → new route → different 5-tuple hash → potentially different ECMP branch.
- Result: **incomplete/inaccurate paths** showing routers that aren't actually on the same path.

## Paris Traceroute Solution

**Keep the 5-tuple constant** while varying TTL.

### Mechanism

1. **Fix 5-tuple:** Sender chooses src port, dst port; keeps them constant across probes.
2. **Vary TTL:** Increment TTL per probe; ECMP router sees identical hash → same branch.
3. **Enumerate branches:** Repeat with different src port values to discover alternative paths.

### Command-Line Usage

```bash
# Measure single path (fixed src port)
paris-traceroute -A udp --sport 1024 example.com

# Enumerate all ECMP branches (vary sport automatically)
paris-traceroute -A udp example.com

# Use ICMP instead of UDP
paris-traceroute -A icmp example.com

# TCP probes (port 443)
paris-traceroute -A tcp --dport 443 example.com
```

### Output Interpretation

```
 1  gw.local (192.168.1.1)  0.123 ms
 2  isp-1.net (10.0.0.1)    2.543 ms
 2  isp-2.net (10.0.0.2)    2.612 ms  [ECMP branch]
 3  core-a.isp (203.0.113.10) 5.234 ms  [path via isp-1]
 3  core-b.isp (203.0.113.20) 5.891 ms  [path via isp-2]
```

- Duplicate TTL hops = ECMP branches.
- Each branch traced independently to destination.

### Integration with OWAMP/TWAMP Probes

**Why combine:**
- OWAMP measures one-way delay per path.
- Paris Traceroute identifies which physical path is active.
- Together: Diagnose asymmetric delay across ECMP branches.

**Workflow:**
1. Run `paris-traceroute` to enumerate paths.
2. Launch OWAMP probes on same src/dst ports to lock onto each path.
3. Correlate latency with path topology.

### Installation

```bash
# Linux (Debian/Ubuntu)
sudo apt-get install paris-traceroute

# macOS
brew install paris-traceroute

# Build from source
git clone https://github.com/paris-traceroute/paris-traceroute
cd paris-traceroute
./configure && make && sudo make install
```

### Caveats

- **TTL limit:** Some paths may be shorter than destination; TTL expires at intermediate hop.
- **Firewalls:** May rate-limit or drop ICMP/UDP probes; TCP port 443 often more permissive.
- **No ECMP:** Routers without load-balancing show identical path for all variants.
- **Reverse path:** Only shows forward path (source → destination); asymmetry may hide reverse-path ECMP.
