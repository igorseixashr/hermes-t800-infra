# Nexus Management Connectivity (mgmt0)

No ambiente corp/Equinix, a interface `mgmt0` dos switches Nexus é o padrão para gerência, mas possui particularidades operacionais.

## Connectivity Pitfalls

### 1. Management VRF
Diferente de routers IOS-XE, no NX-OS a interface `mgmt0` está obrigatoriamente na VRF `management`.
- **Efeito**: Pings e SSH vindos de fora devem estar devidamente roteados para esta VRF.
- **Troubleshooting**: Se o IP responde a ping mas o SSH dá timeout, verifique as `line vty` e se há uma ACL aplicada especificamente na VRF de gerência (`ssh server vrf management`).

### 2. Handshake Timeouts
Como observado em sessões recentes, o handshake SSH pode falhar por latência ou filtros de pacotes intermediários.
- **Sintoma**: `SSH connection error: Timed out while waiting for handshake`.
- **Ação**: Tente aumentar o timeout do cliente SSH ou verifique se o switch atingiu o limite de sessões VTY (`show users`, `show logging last 10`).

### 3. Out-of-Band (OOB) Switch
Os switches Nexus do RJ2 (CORE-01/02) estão conectados a switches de OOB (`EQX-RJ2-ADQ-OOB-SW-1/2`).
- **Recuperação**: Se a gerência direta falhar, o acesso via console server ou via IP do switch de OOB pode ser a única alternativa.

## Comandos de Verificação (Local Console/SSH)
```bash
show interface mgmt0
show ip route vrf management
show vrf detail management
show ssh server
```
