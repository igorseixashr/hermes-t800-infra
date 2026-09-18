---
name: netops-graphrag-ops
description: Use for the Neo4j GraphRAG stack + MCP server ops.
---

# NetOps GraphRAG Stack (Neo4j + MCP)

Built Sep 2026 on top of the daily Confluence->Markdown sync (`~/wiki/FOUND`,
`~/wiki/STIS`, see `confluence-batch-sync` skill). Turns ~9,139 wiki pages into
a queryable knowledge graph with vector search, exposed to Hermes via MCP.

## Components

- **Neo4j 5.26 Community + APOC**: Docker Compose at `/opt/netops-graph/`
  (container `netops-graphrag-neo4j`, ports 7474/7687 bound to 127.0.0.1 only).
  Password in `/opt/netops-graph/.env` (chmod 600), var `NEO4J_PASSWORD`.
- **Isolated venv**: `/opt/netops-graph/venv` (neo4j driver, google-genai,
  tenacity, `mcp[cli]<2` for FastMCP v1 API — mcp>=2 renamed FastMCP to
  MCPServer and breaks `from mcp.server.fastmcp import FastMCP`).
- **Ingestion**: `/opt/netops-graph/ingest_wiki_to_graph.py` — chunks each MD
  by `##` headers, embeds via `gemini-embedding-001` with
  `output_dimensionality=768` (the model defaults to 3072d if you omit this —
  must match the Neo4j vector index dimension exactly), upserts
  `(:Document)-[:HAS_CHUNK]->(:Chunk {embedding})`. Idempotent via
  `ingest_state.json` checkpoint (`done_files`/`failed_files`), safe to resume.
- **Entity extraction (NER)**: `/opt/netops-graph/entity_extraction.py` — ONE
  Gemini call per DOCUMENT (not per chunk, ~9k calls not ~30k+) asking for
  structured JSON entities (Device/Protocol/Policy/Network), links them to
  the Document AND to individual Chunks via case-insensitive substring match
  (zero extra API cost for the chunk-linking step). Checkpoint in
  `ner_state.json`. Validated on a real technical doc (RSFN migration HLD) —
  correctly extracted ACLs, subnets, datacenters; returns empty arrays
  (correctly) on non-technical pages.
- **MCP server**: `/opt/mcp-servers/neo4j_graphrag_mcp.py`, registered in
  Hermes as `neo4j_graphrag` via `hermes mcp add` (NOT by hand-editing
  `config.yaml` — that's blocked by a security guard). Exposes 3 tools:
  `search_hybrid_graphrag(query, limit, rerank=True)` (vector search + cross-encoder
  listwise reranker via `gemini-2.5-flash` + graph expansion to entities + parent doc),
  `query_graph_topology(entity_name, depth)`, and `read_only_cypher(cypher_query)`.
- **Ontology & Topology**: Supports `Device`, `Protocol`, `Policy`, `Network`,
  `Interface`, `VRF`, `ASN`, and `Circuit_ID`. High-frequency co-occurrence links:
  `HAS_INTERFACE` (16.9k), `CONNECTED_TO` (14.7k), `ATTACHED_TO` (6.2k), `APPLIES_TO` (2k),
  `USES_PROTOCOL` (1.5k), `HAS_ASN` (916), `IN_VRF` (867), `ENFORCES_POLICY` (541).
  Scripts: `/opt/netops-graph/link_entities_topology.py` and
  `/opt/netops-graph/ingest_ontology_regex.py`.
- **Vector index**: named `chunk_embeddings` (NOT `wiki_chunks_embeddings` —
  match whatever name you actually created with `db.index.vector.
  createNodeIndex`), 768d, cosine, on `:Chunk.embedding`.
- **Entity topology linking**: `/opt/netops-graph/link_entities_topology.py` —
  connects co-occurring entities in the same chunk with frequency >= 3 via
  typed relationships: `(:Device)-[:USES_PROTOCOL]->(:Protocol)`,
  `(:Device)-[:ATTACHED_TO]->(:Network)`, `(:Device)-[:CONNECTED_TO]->(:Device)`,
  `(:Device)-[:ENFORCES_POLICY]->(:Policy)`, `(:Protocol)-[:APPLIES_TO]->(:Network)`.
  Integrated directly into `graph_delta_sync.py` to auto-update after page changes.
  Safe to re-run; supports `--threshold N`, `--dry-run`, and `--rollback`.

## Pitfalls

- **`hermes mcp add` positional-arg ordering**: `--args` must be the LAST
  flag (consumes everything after it). Putting `--env KEY=VAL ...` after
  `--args script.py` silently swallows the env vars into `args` instead of
  the `env` dict — the server then can't find `NEO4J_PASSWORD`/`GOOGLE_API_
  KEY`. Order: `--command ... --env K=V K2=V2 --connect-timeout N --args
  script.py` (args last). Verify with `grep -A 20 "  <name>:"
  ~/.hermes/config.yaml` — must show `env:` as its own dict, not entries
  under `args:`.
- **`hermes mcp add` is interactive** ("Enable all N tools? [Y/n/select]") —
  pipe `echo "Y" |` in non-interactive/automated contexts.
- **`@mcp.tool()` decorated functions are called directly** (no `.fn`
  attribute) when unit-testing by importing the module — `FastMCP.tool()`
  in the v1 API returns the original function.
- **Neo4j driver logs `WARNING` for labels/relationship types that don't
  exist yet** (e.g. querying `:MENTIONS` before the NER pass has run). This
  is informational noise, not an error — don't treat it as a failure signal.
- **Multi-hour background pipelines killed by session recycling**: a bare
  `terminal(background=true)` process can get SIGTERM'd (exit 143,
  `tcsetattr: Inappropriate ioctl for device` in trailing output) when the
  owning terminal session is torn down/recycled, even with zero bugs in the
  script itself. Prefer `nohup <cmd> > out.log 2>&1 & disown` to fully
  detach from the controlling session for anything running >30-60 min.
- **Checkpoint-only monitoring hides a dead process**: see the
  `agent-observability-and-reporting` skill's "monitoring checkpoint-only
  state hides a dead process" pitfall — status scripts must `pgrep -f
  '<script>.py'` to confirm liveness, not just read the JSON checkpoint.
- **MCP parity/overhead testing must reuse ONE persistent client session**
  across test scenarios (matching how Hermes actually runs MCP servers —
  "connections persist for the lifetime of the agent process" per
  `native-mcp` skill) plus a throwaway warm-up call. Opening a fresh
  stdio subprocess per test call measures cold-start (~1000ms), not real
  per-call overhead (~10-30ms) — wildly overstates MCP overhead and could
  cause a false REPROVADO against a <150ms threshold.
- **Do not ingest raw device configurations into GraphRAG**: ingesting
  unparsed running-configs directly into the knowledge graph severely degrades
  vector search (80% repetitive CLI boilerplate like `no shutdown`/NTP/SNMP drowns
  out semantic SOPs/architecture docs) and triggers graph hairballing (switches
  generate hundreds of low-value interfaces/VLANs). Keep raw configs separated
  in shadow backups (`network-core-backup`) or runtime MCPs (`ios_xe_mcp`), and
  use NetBox (`netbox_mcp`) for current topology/inventory.
- **Entity-to-entity co-occurrence edge density**: creating direct edges
  between entities that appear in the same chunk without a minimum frequency
  threshold causes massive graph bloat (e.g. 470k+ edges on 37k chunks / 31k entities).
  Always apply a frequency filter (e.g. co-occurrence across >=3 distinct chunks/docs)
  to preserve graph sparsity and avoid query slowdowns.
- **Cron dependency sequencing between markdown sync and graph delta**: schedule
  the upstream Confluence markdown sync (`confluence-hybrid-daily-sync`) BEFORE
  `graphrag-delta-sync` with an execution buffer (e.g., Confluence at 03:15,
  GraphRAG at 03:45). If delta sync executes first, updated pages lag by a full
  24 hours before reaching the knowledge graph.

## Cron monitor job (`graphrag-ner-status`) — RETIRED 2026-09-11

The every-3-7min status cron (`graphrag-ner-status`, job_id `b326ff7ec3f1`,
ran `/opt/netops-graph/check_ner_status.sh`) racked up 12+ `Interrupted by
shutdown before terminal completion` / `Fire claim ownership lost` failures
in a single 24h window — far past the "1-2 isolated occurrences" that were
once considered normal gateway-restart noise. Root cause was correct (gateway
restarts tearing down in-flight `terminal()` calls) but the polling interval
was too aggressive relative to gateway restart frequency, making it a chronic
noise generator instead of a rare blip. **Fix applied 2026-09-11 ~20:00-03:00:
the job was retired** and replaced with two lower-frequency, purpose-split
jobs: `graphrag-delta-sync` (`45 3 * * *`, syncs Confluence->Neo4j delta,
reports failures loudly, silent on zero-change days) and
`graphrag-morning-health-report` (`0 8 * * *`, no_agent script health check).
If a NER/graph status monitor is needed again, do NOT poll more often than
every 15-30min, and prefer `no_agent: true` script jobs over LLM-agent jobs
for high-frequency checks (cheaper, and immune to the multi-turn interrupt
window — see `agent-observability-and-reporting` skill's "cron false-failure
during gateway restart" lesson before reintroducing frequent polling).

## Resuming after an interruption

Both `ingest_wiki_to_graph.py` and `entity_extraction.py` are idempotent —
rerunning skips files/docs already in their state JSON. Just relaunch the
same command; no flags needed to resume. Always verify actual DB state after
a long run, don't trust the log alone:
```bash
source /opt/netops-graph/.env
docker exec netops-graphrag-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (d:Document) RETURN count(d); MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c);"
```
