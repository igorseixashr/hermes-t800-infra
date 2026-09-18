# BGP Peer Idle (0.0.0.0) Diagnostic

No Cisco IOS/IOS-XE, quando um alerta do Zabbix reporta o estado BGP como `idle (1)` e o `Remote Peer Identifier` como `0.0.0.0`, isso indica que o processo BGP não conseguiu sequer estabelecer a conexão TCP com o vizinho para trocar o pacote OPEN (onde o ID seria aprendido).

### Principais Causas
1. **No Route to Host**: O roteador não tem uma rota na tabela (RIB) para o IP do neighbor. Sem rota, o BGP não sabe por qual interface sair e permanece em `Idle`.
2. **Source Interface Down**: Se `update-source` estiver configurado (ex: Loopback), e essa interface estiver em `down`, o processo BGP não consegue bindar o socket local.
3. **Configuration Mismatch**: O neighbor está configurado mas o processo BGP está em `shutdown` ou a VRF está incorreta.
4. **TCP Filtering**: ACLs ou Firewalls no caminho bloqueando a porta TCP 179, impedindo que o ID seja descoberto via pacotes de controle.

### Comandos de Validação
```bash
# Verificar roteamento
show ip route <NEIGHBOR_IP>

# Verificar estado da interface de origem
show ip interface brief | include <INTERFACE_NAME>

# Detalhes do neighbor
show ip bgp neighbors <NEIGHBOR_IP>
```
