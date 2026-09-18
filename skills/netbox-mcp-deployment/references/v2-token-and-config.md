# NetBox v2 Token & MCP Configuration Reference

- NetBox v4.5+ uses v2 tokens in the format `nbt_<key>.<plaintext>`.
- Authentication header: `Authorization: Bearer nbt_<key>.<plaintext>`.
- Docker MCP server container env vars:
  - `NETBOX_URL`: NetBox API endpoint (e.g. `https://netbox.corp.io/`)
  - `NETBOX_TOKEN`: `nbt_t4EbHIOlRLw7.3lUuxsNp33c6gTaWpF2OuISIJtsccJ3jRNlHPar4`
  - `TRANSPORT`: `http`
  - `PORT`: `8000`
- Hermes Agent client config (`~/.hermes/config.yaml`):
  ```yaml
  netbox_mcp:
    timeout: 60
    transport: http
    url: http://localhost:8000/mcp
  ```
