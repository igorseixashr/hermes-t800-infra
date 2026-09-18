---
name: netbox-mcp-deployment
description: Deploy and configure NetBox MCP server via Docker.
version: 1.0.0
author: T-800 InfraOps / Hermes Agent
license: MIT
metadata:
  hermes:
    category: devops
    tags: [netbox, mcp, docker, infra, api]
---

# NetBox MCP Deployment Skill

Deploy and configure the official NetBox Model Context Protocol (MCP) server using Docker with HTTP transport and automatic host startup. This enables read-only LLM integration with NetBox infrastructure data.

## When to Use
Use when setting up NetBox MCP integration for AI agents, connecting LLMs to NetBox data, or deploying containerized MCP servers on infrastructure hosts.

## Prerequisites
- Docker and Docker Compose installed on the host.
- A NetBox instance URL (e.g. `https://netbox.corp.io/`).
- A NetBox API Token with read-only permissions (service account recommended).

## How to Run
1. Create a `.env` file with environment variables:
   ```env
   NETBOX_URL=https://netbox.corp.io/
   NETBOX_TOKEN=<your-netbox-api-token>
   ```
2. Create `docker-compose.yml`:
   ```yaml
   services:
     netbox-mcp:
       image: netboxlabs/netbox-mcp-server:latest
       container_name: netbox-mcp-server
       restart: unless-stopped
       env_file:
         - .env
       environment:
         - TRANSPORT=http
         - HOST=0.0.0.0
         - PORT=8000
       ports:
         - "127.0.0.1:8000:8000"
   ```
3. Start the container:
   ```bash
   docker compose up -d
   ```

## Quick Reference
- **Image Hub:** `netboxlabs/netbox-mcp-server:latest` (use Docker Hub, not GHCR).
- **Transport Mode:** `TRANSPORT=http` with `HOST=0.0.0.0` and `PORT=8000`.
- **Restart Policy:** `restart: unless-stopped` for automatic host startup.

## Pitfalls
- **Port Alignment:** Ensure `config.yaml` points to port `8000` (`http://localhost:8000/mcp`), as the container maps port 8000 internally and externally.
- **MCP HTTP Headers:** Direct HTTP JSON-RPC client requests must include both `Content-Type: application/json` and `Accept: application/json, text/event-stream` headers, otherwise the server returns `Not Acceptable: Client must accept both application/json and text/event-stream`.
- **Registry Source:** Do not use `ghcr.io/netboxlabs/...` as it may require authentication; use `netboxlabs/netbox-mcp-server:latest` from Docker Hub.
- **Token Permissions & v2 Tokens:** NetBox v4.5+ uses v2 tokens formatted as `nbt_<key>.<plaintext>` requiring `Authorization: Bearer nbt_<key>.<plaintext>`. Legacy 40-char tokens or incorrect headers return `{"detail":"Invalid v1 token"}`. Ensure service account tokens match the expected NetBox version format.
- **Network Routing & Internal DNS:** Ensure the host/container has routing access to internal NetBox endpoints (e.g. corporate VPN/VLANs) if NetBox is hosted on private IP space (`10.x.x.x`). Connection timeouts indicate network segregation rather than MCP configuration issues.

## Verification
Verify the server is running and responding to HTTP requests:
```bash
docker ps --filter name=netbox-mcp-server
curl -i http://localhost:8000/
```
