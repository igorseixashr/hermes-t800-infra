---
name: fortinet-network-ops
description: Procedures for managing, troubleshooting, and configuring Fortinet (FortiGate) network infrastructure.
---

# Fortinet Network Operations
Procedures for managing, troubleshooting, and configuring Fortinet (FortiGate) network infrastructure.

## Trigger Conditions
- Any request involving FortiGate devices (add, list, configure, troubleshoot).
- Tasks involving firewall policies, static routes, or Virtual IPs (VIPs) on FortiGate.

## Operational Workflow
1. **Device Management:**
   - Use `mcp_fortigate_mcp_list_devices` to check registered devices.
   - Use `mcp_fortigate_mcp_add_device` to register new devices (requires username/password or API token).
   - Use `mcp_fortigate_mcp_test_device_connection` immediately after adding.
   - Use `mcp_fortigate_mcp_remove_device` when done (as per Enterprise/Core security cleanup standards).

2. **Troubleshooting & Diagnostics:**
   - Always run `mcp_fortigate_mcp_get_device_status` to verify hardware/firmware details.
   - Use `mcp_fortigate_mcp_get_routing_table` or `mcp_fortigate_mcp_list_static_routes` for path debugging.
   - Use `mcp_fortigate_mcp_list_interfaces` and `mcp_fortigate_mcp_get_interface_status` to check link/traffic status.

3. **Security Configuration:**
   - Follow 'staged-commit' pattern: `create` or `update` (staged) → `commit` (verify) → `push` (if applicable).
   - Verify existing objects using `list_address_objects` or `list_service_objects` before creating new ones to prevent duplicates.

## Pitfalls
- **SSH Host Key Failures:** If encountering `Bad server host key: Invalid key length` or rejections even with algorithm flags:
    1. Do NOT force repeated attempts as this may trigger lockout.
    2. Check connectivity via ICMP first.
    3. If legacy hardware is confirmed, attempt one manual connection with `-o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o Ciphers=aes256-ctr` to diagnose.
    4. If failure persists, pivot to alternate collection (SNMP, NetBox, or Jumpbox) rather than brute-forcing the handshake.

- **Manual Log Collection Pattern:** Se o SSH estiver bloqueado para execução de comandos remotos, solicite ao usuário a coleta manual para análise:
    1. `systemctl list-units --type=service --state=failed`
    2. `systemctl status <nome-do-servico>`
    3. `journalctl -u <nome-do-servico> --no-pager -n 50`
- **Diagnóstico de Systemd:** Ao configurar novos serviços, lembre-se sempre de executar `sudo systemctl daemon-reload` após criar ou editar arquivos em `/etc/systemd/system/`. Verifique também o shebang de executáveis dentro de ambientes virtuais (.venv), pois caminhos hardcoded apontando para diretórios antigos (ex: `/home/user/` em vez de `/opt/app/`) causarão erros `status=203/EXEC` (Permission denied/Exec format error) que não são óbvios apenas pelas permissões de arquivo. Use `sed` ou re-criação do venv para corrigir caminhos absolutos.
- **Authentication:** Restrições de segurança (IP de origem, necessidade de Jump Host/Bastion ou chaves SSH específicas) podem causar `Permission denied`. Não tente forçar senhas via `sudo -S` ou pipes, pois é um vetor de ataque bloqueado. Use chaves SSH sempre que possível e garanta permissões 700 para `~/.ssh` e 600 para `authorized_keys`.
- **VDOMs:** If a device is multi-VDOM, ensure all commands specify the correct VDOM. Run `discover_vdoms` if unsure.
- **Cleanup:** As a policy for InfraOps, always remove temporary devices once the troubleshooting or configuration task is finished.
