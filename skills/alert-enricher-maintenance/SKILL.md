---
name: alert-enricher-maintenance
description: Maintenance, troubleshooting, and evolution of the Infrastructure Alert Enricher service.
---
# Infrastructure Alert Enrichment

Skills and workflows for maintaining, troubleshooting, and evolving infrastructure alert enrichment services (specifically the `alert-enricher` project).

## Context
The `alert-enricher` is a FastAPI-based middleware that sits between monitoring systems (Zabbix) and notification platforms (Slack). It enriches raw alerts with deep infrastructure context from NetBox (via REST and MCP) and provides AI-driven diagnostics.

## Architecture
1. **Source**: Zabbix sends a JSON payload to `/enrich-alert`.
2. **Standard Enrichment**: REST API calls to NetBox to fetch device role, site, ASN, and primary IP.
3. **Advanced Enrichment (MCP)**: Stateful JSON-RPC over SSE calls to an MCP NetBox server to fetch changelogs and interface details.
4. **Knowledge Retrieval (Confluence)**: Local search over Confluence markdown files (`kb-sync/confluence-files/`) matching alert keywords/device metadata.
5. **AI Analysis**: Context (Alert + NetBox + MCP + Confluence) is sent to Gemini / LLM to formulate a rigorous, data-driven root cause hypothesis and specific remediation actions (avoiding generic checklists).

## Refactoring Pattern: Cron Script to FastAPI Service
A common evolution task is to migrate a legacy cron-based Python script to a modern, robust FastAPI service managed by `systemd`. This centralizes logic, improves security, and provides better observability.

### Workflow
1.  **Analysis & Discovery**:
    *   `read_file` the cron script (`infra-bot-enricher.py`), the target service code (`/opt/alert-enricher/main.py`), and the `systemd` unit file (`/etc/systemd/system/alert-enricher.service`).
    *   Use `cronjob(action='list')` to identify the legacy job responsible for running the script.

2.  **Security Hardening (Secrets Management)**:
    *   **Goal**: Eliminate all hardcoded secrets (tokens, keys) from source code and `systemd` unit files.
    *   Create a dedicated environment file (e.g., `/home/hermes/.private/enricher.env`).
    *   Update the `.service` file to use `EnvironmentFile=` instead of hardcoded `Environment=` lines.
        *   **Pitfall**: Direct edits to `/etc/` may be blocked. A safe workaround is to `write_file` the new unit to `/tmp/` and then use `terminal` with `sudo mv` to move it into place.
    *   Modify the Python service (`main.py`) to only use `os.getenv("...")` without any hardcoded fallbacks.

3.  **Code Consolidation & Modernization**:
    *   **Strategy**: For significant refactoring, a series of `patch` calls is fragile. Prefer generating the complete, final Python code and using a single `write_file` call to replace the old service file atomically.
    *   Integrate the logic from the cron script (e.g., polling a Slack channel) as an `asyncio` background task within the FastAPI service's startup event.
    *   Replace legacy logic (e.g., regex/keyword-based parsing) with modern, robust calls to primary tools (e.g., using Gemini via `delegate_task` for analysis).

4.  **Deployment & Validation**:
    *   Reload the `systemd` daemon to apply changes to the unit file: `sudo systemctl daemon-reload`.
    *   Restart the service: `sudo systemctl restart alert-enricher.service`.
    *   Monitor for correct operation: `sudo journalctl -u alert-enricher.service -f --no-pager` and `tail -n 50 /var/log/alert-enricher/app.log`.
    *   **Background Polling Validation**: When porting polling loops into FastAPI `asyncio.create_task`, verify that all thread and deduplication helpers (e.g., `is_new_thread`) are fully implemented and error-handled; do not pause legacy cron jobs (`infra-bot-slack-monitor` / `infra-bot-slack-enricher`) until the in-process polling loop is verified error-free.

5.  **Decommissioning Legacy Components**:
    *   Once the new service is validated and processing all workflows correctly, pause the old cron job: `cronjob(action='pause', job_id='...')`.
    *   Rename the old script to mark it as deprecated, e.g., `mv script.py script.py.DEPRECATED`.

### Secret Recovery
- **Guidance, not Access**: The agent cannot read secrets. If the user does not have them, guide them on how to find them using safe commands like `grep` on old, non-production config files or by pointing them to the relevant UI (e.g., `https://api.slack.com/apps`).

---

## Operations

### Deployment & Maintenance
- **Path**: `/opt/alert-enricher`
- **Directories**: 
  - Logs: `/var/log/alert-enricher/`
  - Persistence: `/var/lib/alert-enricher/` (Deduplication and Event Index)
- **Service**: Managed via `systemd` (check `alert-enricher.service`).
- **Dependencies**: Managed via `requirements.txt`. Use a virtual environment (`.venv`).
- **Port Selection**: Default to `8080` if `8000` is occupied by existing Docker containers.

### Integration (Zabbix 5.0)
- **JS Compatibility**: Zabbix 5.0's JavaScript engine **does not support `hmac()`**.
- **Security**: Use the `INSECURE_NO_AUTH` mode or rely on network-level security (IP allowlists) when integrating with legacy Zabbix versions that cannot sign payloads easily.
- **Payload**: Use `CurlHttpRequest` to POST JSON directly to `/enrich-alert`.

### Slack Hygiene
- **Channel Strategy**: Keep the main channel (`C0123456789`) clean with summaries only.
- **Thread Delegation**: Move all troubleshooting and "Deep Dive" analysis into threads.
- **Socket Mode**: Prefer Socket Mode or Hermes-delegated interactions over public HTTP callback buttons to avoid "unverified URL" security warnings in Slack.
- **Channel Reconfiguration Synchronization**: Reconfigurar o canal de destino/triagem exige atualização em 3 camadas complementares para evitar que o pipeline quebre silenciosamente:
  1. Unit do systemd (`/etc/systemd/system/alert-enricher.service`): `POLLING_CHANNEL_ID` e `WEBHOOK_CHANNEL_ID`.
  2. Serviço FastAPI (`/opt/alert-enricher/main.py`): garantir declaração no topo de `POLLING_CHANNEL_ID`, `WEBHOOK_CHANNEL_ID` e `SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", WEBHOOK_CHANNEL_ID)` (evita `NameError` em `send_to_slack` e no endpoint `/health`).
  3. Scripts de cron (`~/.hermes/scripts/infra-bot-monitor.py` e `~/.hermes/scripts/infra-bot-enricher.py`): atualizar `DEST_CHANNEL`. Se divergirem, as mensagens coletadas pelo monitor não chegam à fila do enricher.
- **Proactive Unified Enrichment**: Alertas recebidos no webhook Zabbix (`/enrich-alert`) devem adotar o mesmo formato padronizado (`🚨 *Novo Alerta de Rede (Zabbix)*`) e postar imediatamente a triagem e o diagnóstico profundo na thread (`thread_ts`), sem aguardar interação manual (`analisar`).
- **Slack Thread Roots Lacking `thread_ts`**: In the Slack API, top-level messages posted to a channel lack the `thread_ts` attribute until a reply exists. Workers querying `conversations.history` to enrich threads must evaluate `thread_ts = msg.get("thread_ts") or msg["ts"]` and ensure `msg["ts"] == thread_ts` so that newly created root alerts are captured.
- **Webhook vs. Polling Message Formats**: Alertas diretos do webhook Zabbix (`/enrich-alert`) produzem cards informativos (`🚨 <Severity> - <Hostname>`) com opção sob demanda (`analisar` na thread). Já alertas copiados pelos monitores de chamados (`infra-bot-monitor.py`) possuem títulos padronizados (`Novo Chamado Detectado`, `Novo Alerta de Rede`, etc.) e são automaticamente enriquecidos via LLM na thread pelo `infra-bot-enricher.py`. Alertas Zabbix no canal comum não recebem diagnóstico automático na thread a menos que explicitamente integrados ao filtro do enricher.
- **Channel Variable Alignment**: Ensure channel environment variable names in systemd (`WEBHOOK_CHANNEL_ID` / `POLLING_CHANNEL_ID`) match the variable references in code (`os.getenv(...)`) — naming divergence triggers unhandled `NameError` or silent drop during `send_to_slack`.
- **Channel Configuration Sync**: When changing triage/alert channels, update both the FastAPI service (`alert-enricher.service` + `main.py`) and background triage cron jobs (`infra-bot-monitor.py` / `infra-bot-enricher.py` under `~/.hermes/scripts/`), which maintain separate `DEST_CHANNEL` constants.

### Troubleshooting
1. **Check Process**: `ps aux | grep alert-enricher` or `systemctl status alert-enricher`.
2. **Check Logs**: `tail -f /var/log/alert-enricher/app.log`.
3. **Validate Healthcheck**: Always run `curl -s http://localhost:8080/health | jq .` after config or code changes; a 500 indicates unhandled runtime/environment variables missing in `main.py` (e.g. `LLM_URL`, `SLACK_CHANNEL_ID`).
- **Slack**: Bots using `slack_sdk` require proper token authentication. If `slack_sdk.errors.SlackApiError: not_authed` occurs:
  - Verify that `SLACK_BOT_TOKEN` is present in the environment.
  - **Cron Execution**: When running as a cron job, the environment is isolated. Explicitly load tokens using `dotenv` or by exporting them in the cron command/script. Never rely on the shell's `.bashrc` or local exported variables.
  - **Environment Hygiene**: Ensure `SLACK_BOT_TOKEN` is loaded securely. Do not hardcode tokens in scripts.

## Implementation Details
- **MCP via HTTP/SSE**: The service implements a custom SSE parser for MCP JSON-RPC. 
- **Slack Interactivity**: Handles `view_submission` for modals and `block_actions` for thread continuations.

## References
- `references/mcp-python-sse.md`: Implementation pattern for calling MCP servers from Python without a dedicated library.
- `templates/alert-enricher.service`: Systemd unit template.
