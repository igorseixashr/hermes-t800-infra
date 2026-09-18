# Calling MCP via HTTP/SSE in Python

When building a service that consumes an MCP server over HTTP/SSE (like the `alert-enricher`), use the following pattern with `httpx`.

## SSE Parsing
MCP responses over SSE prefix data with `data:`.

```python
def _parse_sse(text: str):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            if data_str:
                return json.loads(data_str)
    return None
```

## Stateful Session Workflow
1. **Initialize**: Call `/mcp` with `method: initialize`. Extract `Mcp-Session-Id` from headers.
2. **Call Tool**: Call `/mcp` with `Mcp-Session-Id` header and `method: tools/call`.
3. **Handle Response**: Parse the SSE body to get the tool results.

## Example Request
```python
resp = await client.post(
    f"{mcp_base}/mcp",
    headers={"Mcp-Session-Id": session_id},
    json={
        "jsonrpc": "2.0",
        "method":  "tools/call",
        "id":      call_id,
        "params":  {
            "name":      tool_name,
            "arguments": arguments,
        },
    },
)
```
