# Alert Enricher: Architecture, Flow & Performance Optimization

This reference document outlines the hybrid architecture of the Alert Enricher system at corp, the flow of message processing, and the performance optimizations implemented to solve the response delay.

## System Architecture & Components

The alert enrichment and diagnostics system is split into two layers:

1.  **FastAPI Alert-Enricher Service (`/opt/alert-enricher`)**
    *   **Port:** `8080` (FastAPI + Uvicorn)
    *   **Service:** `alert-enricher.service` (running as `hermes` user)
    *   **Role:** Acts as the ingestion gateway. It receives raw alerts from Zabbix, performs BGP-normalization and basic regex extraction, queries NetBox via HTTP REST, compiles a formatted "NetBox Affected Device" block, and posts it to Slack.
    *   **Data Store:** `/var/lib/alert-enricher/event_index.json` (persists incident-to-Slack-TS mappings).

2.  **Hermes Agent (Slack Gateway via Socket Mode)**
    *   **Role:** Acts as the conversational brain. Since the local server has no public IP or tunnel, Slack's interactive webhooks (`POST /slack/interact`) cannot reach port `8080`.
    *   **Mechanism:** Hermes connects via **Slack Socket Mode** (outbound WebSockets), bypassing firewall constraints.
    *   **Trigger:** When a user types `analisar` or asks a question in the alert thread (free response channel `C0123456789`), Hermes intercepts the message and loads the `alert-enricher` skill.

---

## Alert Pipeline & Context Loop

```
[Zabbix Alert] 
      │
      ▼ (POST /enrich-alert)
[FastAPI Service (8080)] ──(HTTP REST)──> [NetBox API]
      │
      ▼ (chat.postMessage)
[Slack Thread (C0123456789)]
      │
      ▼ (User types "analisar" in thread)
[Hermes Agent (Socket Mode)] ◄──(Socket)── [Slack SaaS]
      │
      ▼ (Triggers alert-enricher skill)
[Diagnostics Generation]
```

### The Performance Bottleneck (Identified May 2026)
Historically, when a user requested an analysis in the thread, the `alert-enricher` skill instructed Hermes to query NetBox via MCP to "gather context." 
This caused Hermes to sequentially call up to 7 NetBox MCP tools (`mcp_netbox_get_devices`, `mcp_netbox_get_interfaces`, etc.). Since each query took ~1.5s, the agent spent 15-20 seconds in redundant tool execution, resulting in overall thread response latencies of **70 to 110 seconds**.

---

## Performance Optimizations

### 1. Slack Thread History Reuse (Primary Fix)
Because the FastAPI service *already* parsed NetBox and printed the key details (Device, Site, Role, Platform, IPs, BGP Peer status) in the very first Slack message of the thread, **Hermes does not need to query NetBox again**.
*   **Action:** The skill instructions are patched. Hermes must parse the thread history first. If NetBox details are present, it **skips all MCP queries** and jumps directly to LLM diagnostics.
*   **Result:** Cuts execution time down to raw LLM generation latency (< 8 seconds).

### 2. Parallelizing Fallback MCP Queries
If NetBox details are missing from the thread and a query is absolutely necessary, the agent is instructed to emit multiple tool calls in parallel (a single LLM turn) rather than executing them sequentially.

### 3. MCP JSON-RPC Stdout Pollution
Some custom MCP servers in the stack (e.g., `ios_xe_mcp` or `splunk_mcp`) were found to write standard logging strings (e.g., `2026-05-20 02:12:03 - mcp...`) to `stdout` instead of `stderr`. This breaks the JSON-RPC standard and forces the Hermes MCP client to raise a `ValidationError` and reconnect, adding 3-5 seconds of latency to tool-heavy runs.
*   **Remedy:** Ensure all custom/dockerized MCP servers output logs exclusively to `stderr`.
