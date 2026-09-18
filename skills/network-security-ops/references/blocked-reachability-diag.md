# Diagnosing Blocked Reachability (ICMP-up / TCP-down)

Recipe for when a host is given to you with credentials but you can't connect.
The frequent root cause is a perimeter firewall that permits ICMP echo but
drops TCP SYN from your source IP — so the credentials are likely fine and the
real blocker is the network path. Prove it before touching anything.

## Symptom signature

- `ping` succeeds (replies, low loss). TTL ~59 on a /24-ish enterprise path
  means ~5 hops away (started at 64).
- EVERY TCP port you probe — SSH and the service ports — is closed/filtered.
- TCP traceroute dies a couple hops short of the destination while ICMP
  traceroute reaches it. The divergence hop is the firewall.

## Probe commands (copy/adapt)

```bash
HOST=10.10.1.10

# 1. ICMP — is the host alive and routed?
ping -c 3 -W 2 "$HOST"

# 2. TCP port sweep without nmap (bash /dev/tcp). exit 0 = open.
for p in 22 2222 2022 22022 9200 9300 5601 80 443; do
  timeout 4 bash -c "cat < /dev/null > /dev/tcp/$HOST/$p" 2>/dev/null \
    && echo "port $p OPEN" || echo "port $p closed/filtered"
done

# 3. Where does the path die? ICMP vs TCP, side by side.
traceroute -I -n -w2 -m 12 "$HOST"            # ICMP — should reach dest
sudo traceroute -T -p 22 -n -w2 -m 12 "$HOST" # TCP/22 — dies at firewall hop
```

`sshpass` install on Rocky/RHEL 9 if missing: `sudo dnf install -y sshpass`
(needs EPEL on some builds). Keep the password out of argv —
`export SSHPASS='...'; sshpass -e ssh ...`.

## Real transcript (2026-06, target 10.10.1.10 from Hermes host 10.10.4.83)

```
ICMP:  64 bytes from 10.10.1.10 ... ttl=59 time=18.7 ms   (0% loss)
TCP:   port 22/2222/2022/22022/9200/9300/5601/80/443 -> ALL closed/filtered

traceroute -I (ICMP) reaches dest:
  10.10.4.2 -> 10.30.0.62 -> 10.0.0.9 -> 10.0.0.2 -> 10.10.1.10 -> 10.10.1.10

traceroute -T -p 22 (TCP) dies after hop 5:
  10.10.4.2 -> 10.30.0.62 -> 10.30.0.10/10.0.0.9 -> 10.0.0.2 -> 10.0.0.2 -> * * * ...
```

Verdict: firewall at/after `10.0.0.2` drops TCP SYN from `10.10.4.83` toward
the `10.10.1.10/24` segment. ICMP is permitted, TCP is not. Credentials
untested because the socket never opens — do NOT report them as wrong.

## What to do with the verdict

Present the evidence as a table (ICMP vs each TCP port) and name the drop hop.
Then STOP and let the user choose — opening a firewall rule for your own host
is a production change you don't make unilaterally:

1. **Minimal staged firewall rule** — src = Hermes host IP, dst = target,
   only the needed TCP port. Identify the owning firewall (the drop hop tells
   you roughly where), stage the policy, commit ONLY on explicit OK.
2. **ProxyJump via bastion** — if a host already reaches the segment, hop
   through it: `ssh -J user@bastion user@target`. Fastest, touches no firewall.
3. **Non-standard SSH port** — confirm the real port if 22 isn't it.
