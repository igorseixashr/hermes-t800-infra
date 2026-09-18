# CISCO-RTTMON-MIB OID Reference (validated live, IOS-XE 17.6.3a)

Base: `1.3.6.1.4.1.9.9.42`. Every OID below was confirmed with a direct
`getCmd`/`getWalk` against a real device and cross-checked against
`show ip sla` CLI output — not copied from a spec/blog without
verification (several of those sources have wrong OIDs here, see the
skill's Pitfalls section).

## Admin tables — discovery (read-only walk is safe)

`rttMonCtrlAdminTable` (`.1.2.1.1`) — one row per configured operation,
indexed by `rttMonCtrlAdminIndex`:
- `.3` rttMonCtrlAdminTag (logical name string)
- `.4` rttMonCtrlAdminRttType (enum, see below)
- `.6` rttMonCtrlAdminFrequency (seconds)

RttType enum values seen in practice: `1`=icmpEcho, `2`=pathEcho
(path-jitter — never appears here on IOS-XE despite the enum value
existing), `6`=tcpConnect, `7`=http, `8`=dns, `9`=jitter (udpJitter, or
voipJitter if a codec is set), `13`=voip. Consult the live MIB for
others (dlsw, dhcp, ftp, rtp) — don't hardcode from memory.

`rttMonEchoAdminTable` (`.1.2.2.1`) — echo-specific config, same index:
- `.2` rttMonEchoAdminTargetAddress — **raw 4-byte OCTET STRING**, not
  human-readable. Parse: `bytes(value)` then
  `".".join(str(b) for b in raw)`. All-zero = unset.
- `.5` rttMonEchoAdminTargetPort (Integer32, 0 = unset)
- `.6` rttMonEchoAdminSourceAddress — same raw-octet parsing as `.2`
- `.11` rttMonEchoAdminTargetAddressString — DisplayString column;
  observed EMPTY on IOS-XE even when `.2` has a real value. Don't rely
  on it; always parse `.2` instead.
- `.27` rttMonEchoAdminCodecType — non-zero means voipJitter, not plain
  udpJitter, for an operation whose RttType enum is `9`.

## Latest-value tables — collection (the ones you actually want)

**Do NOT use `1.3.6.1.4.1.9.9.42.1.3.5`** for jitter stats. That's
`rttMonJitterStatsEntry`, part of `rttMonStatsCaptureTable` — a
historical/distribution-bucket table with a compound sub-index, not a
simple "latest value per operation" table. It looks superficially
similar (same numeric neighborhood) and is the wrong OID copied in
several specs/blog posts.

`rttMonLatestRttOperTable` (`.1.2.10.1`) — generic latest RTT, covers
icmpEcho/tcpConnect/dns/http-fallback, indexed by
`rttMonCtrlAdminIndex`:
- `.1` rttMonLatestRttOperCompletionTime (ms) — **not** the sense field
- `.2` rttMonLatestRttOperSense (enum: 1=ok, 2=disabled, 3=timeout,
  4=notConnected, 5=dropped, 6=sequenceError, 7=verifyError,
  8=applicationSpecific, 9=socketError, 10=unknown, 11=badDestAddr,
  12=measureInProgress, 13=generalError, 14=connectionLost — cross-
  check a couple of these against `show ip sla summary`'s human-
  readable Return Code column before trusting the mapping)

`rttMonLatestJitterOperTable` (`.1.5.2.1`) — the correct jitter/voip
latest-value table, indexed by `rttMonCtrlAdminIndex`:
- `.1` NumOfRTT, `.2` RTTSum (avg = RTTSum/NumOfRTT)
- `.8` NumOfPositivesSD, `.9` SumOfPositivesSD
- `.13` NumOfNegativesSD, `.14` SumOfNegativesSD
- `.18` NumOfPositivesDS, `.19` SumOfPositivesDS
- `.23` NumOfNegativesDS, `.24` SumOfNegativesDS
- `.26` PacketLossSD, `.27` PacketLossDS, `.29` PacketMIA
- `.31` rttMonLatestJitterOperSense — **the jitter table's OWN status
  enum, separate OID from `rttMonLatestRttOperTable`'s `.2`.** Same
  value semantics (1=ok, 6=disconnected, etc). Easy to miss because it
  looks like status should already be covered by the generic RTT
  table — it is NOT: udpJitter/voipJitter operations only ever populate
  this table, never `rttMonLatestRttOperTable`. Skipping it means every
  jitter-type operation's "status" panel reads "No data" forever, even
  though the collector is otherwise working. Cross-checked live:
  index with `show ip sla summary` = "No connection" returned `sense=6`
  here, confirming the mapping.
- `.42` MOS (only meaningful for voipJitter operations)

Derived (compute yourself, none of these come pre-calculated):
```
avg_rtt_ms      = RTTSum / NumOfRTT
avg_jitter_sd   = (SumOfPositivesSD + SumOfNegativesSD) /
                  (NumOfPositivesSD + NumOfNegativesSD)   # guard /0
avg_jitter_ds   = same pattern with the *DS counters
packet_loss_pct = (PacketLossSD + PacketLossDS + PacketMIA)
                  / NumOfRTT * 100
```

## `rttMonLatestHTTPOperTable` (`.1.5.1.1`) — NOT live-validated

Referenced by the original spec appendix (RTT/DNS-RTT/TCP-connect-RTT/
TransactionRTT/MessageBodyOctets/Sense columns) but no HTTP-type IP SLA
operation existed on the test router used to validate this reference —
treat these OIDs as unverified until confirmed against a real HTTP
probe.
