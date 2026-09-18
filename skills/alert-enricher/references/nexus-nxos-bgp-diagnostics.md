# Nexus (NX-OS) BGP Diagnostics

Referência para diagnóstico de sessões BGP em switches Nexus 5k/7k/9k baseada em estados operacionais.

## BGP States & Implications

### Idle (1)
- **Causa**: BGP foi configurado mas está administrativamente "down" ou aguardando um evento (como rota para o peer).
- **Remote ID 0.0.0.0**: BGP nem tentou iniciar o handshake.

### Connect (2)
- **Comportamento**: BGP está aguardando a conclusão do handshake TCP.

### Active (3)
- **Comportamento**: O switch está ativamente enviando pacotes `TCP SYN` (porta 179) mas **não recebe** resposta (`SYN-ACK`).
- **Hipóteses**:
  - Falta de rota para o peer (verificar `show ip route <peer_ip>`).
  - ACL ou Firewall bloqueando porta 179.
  - Peer não está configurado para aceitar conexão deste IP (Source Interface mismatch).

### OpenSent (4)
- **Comportamento**: Handshake TCP concluído. Switch enviou pacote `BGP OPEN` e aguarda o do vizinho.
- **Hipóteses**: Mismatch de ASN, problemas de MTU ou MD5 password errada.

### OpenConfirm (5)
- **Comportamento**: Ambos enviaram `OPEN` e `KEEPALIVE`. Aguardando confirmação final.

### Established (6)
- **Comportamento**: Sessão funcional.

## Comandos Críticos (NX-OS)
- `show ip bgp neighbors <IP> [vrf <VRF>]`: Mostra contadores, timers e motivo da última queda.
- `show ip bgp summary [vrf all | vrf <VRF>]`: Resumo de peers no contexto da VRF.
- `ping <IP> [vrf <VRF>]`: Teste de alcance de Camada 3.
- `show ip route <IP> [vrf all | vrf <VRF>]`: Localiza a VRF e rota específica do peering.
- `show ip arp [vrf <VRF>] | include <IP>`: Validação de resolução ARP na VRF do parceiro.

## BFD Integration & Echo Function Failures

No NX-OS, quando o BFD está configurado para monitoramento rápido (`bfd live-detection` ou `bfd` sob o neighbor BGP), a queda da sessão BGP frequentemente ocorre com o syslog:
`%BFD-5-SESSION_STATE_DOWN: BFD session ... to neighbor ... on interface ... has gone down. Reason: Echo Function Failed.`

Isso indica que pacotes de eco do BFD (enviados de forma síncrona de um lado e retornados pelo outro) pararam de ser devolvidos, o que aponta diretamente para falhas na camada física (L1), enlace (L2) ou plano de dados, antes mesmo dos timers normais do BGP expirarem.

### Sequência Sistemática de Diagnóstico BGP/BFD (NX-OS):

Quando uma sessão BGP/BFD cair devido a "Echo Function Failed" e o estado BGP estiver em `Idle`/`Active`:

1. **Checar o Neighbor BGP detalhadamente:**
   ```bash
   show ip bgp neighbor <IP>
   ```
   *Verificar o campo `Last reset` (ex: "due to bfd session down") e se há `Description` indicando o provedor/identificação do circuito.*

2. **Validar alcance de Camada 3:**
   ```bash
   ping <IP> count 3
   ```
   *Se receber `Destination Host Unreachable` (originado pelo próprio IP do switch), o switch não está conseguindo resolver o ARP do IP vizinho.*

3. **Inspecionar a Tabela ARP:**
   ```bash
   show ip arp <IP>
   show ip arp vlan <VLAN_ID>
   ```
   *Se a tabela estiver vazia (0 entries), indica ausência total de resposta ARP do peer.*

4. **Verificar Estado da Interface Física & LLDP:**
   ```bash
   show interface status | include <Interface>
   show lldp neighbors
   ```
   *Se a interface física estiver `connected` (UP) mas o ARP/BGP falhar, o switch pode estar conectado a um patch switch ou switch local do datacenter (ex: Ascenty, Equinix), mas o circuito real da operadora está interrompido além desse equipamento intermediário.*

5. **Análise de MAC Table na VLAN do Peer:**
   ```bash
   show mac address-table vlan <VLAN_ID>
   ```
   *Se o único MAC aprendido na VLAN for o do switch local (ex: do parceiro de datacenter), mas o MAC do roteador da operadora não aparecer na VLAN, o circuito está quebrado no trecho externo da operadora (transporte fora do cage).*

6. **Revisar a Configuração de BFD e Interface lógica:**
   ```bash
   show running-config interface Vlan<VLAN_ID>
   show running-config bgp
   ```
   *Confirmar se os timers de BFD estão corretos (ex: `bfd interval 999 min_rx 999 multiplier 3`).*

