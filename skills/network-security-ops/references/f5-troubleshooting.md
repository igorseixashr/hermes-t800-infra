# F5 Troubleshooting Reference

## Connectivity & MCP Troubleshooting
- **API Resolution Failures:** If `mcp_f5_mcp_*` tools fail with `NameResolutionError` or `ConnectionPool` timeouts, do NOT rely on local DNS. Use the IP retrieved from NetBox directly.
- **Credential Rotation:** Always verify if `NET_USER` / `NET_PASS` (from `~/.bashrc.d/network-creds.env`) have been updated in the environment before retrying connection/API calls.
- **Health Check Flow:**
  1. Retrieve primary IP from NetBox.
  2. Use `curl` via `Bun.spawn` (if API call fails via MCP) to attempt a test request to `/mgmt/shared/echo-query`.
  3. Validate if the management port (443) is accessible via `terminal` (`nc -zv <IP> 443`).

## Common Alert Scenarios
- **Pool Member Down:** Identify virtual server -> pool -> node. Check monitors.
- **Resource Exhaustion:** Check system CPU/RAM/Conn count.
- **Config Sync:** Verify HA pair status (`show cm sync-status`).
