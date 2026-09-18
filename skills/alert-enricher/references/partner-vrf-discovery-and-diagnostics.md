# Diagnóstico Assertivo de Links de Parceiros e Mapeamento de VRFs (corp/corp)

## Contexto Arquitetural
Na arquitetura de telecom da corp/corp, links de comunicação dedicados com parceiros (bandeiras de cartão, autorizadores, adquirentes, bancos, TEFs e operadoras) são estritamente isolados em **VRFs dedicadas** (Virtual Routing and Forwarding) nos switches e roteadores de Core e Distribuição (Cisco Nexus NX-OS, Cisco IOS-XE e Juniper Junos).

**Regra Crítica:** Comandos de diagnóstico executados no contexto global (`default`) falham ou retornam dados vazios para esses links. É mandatório descobrir a VRF e contextualizar os comandos.

---

## 1. Pipeline de Descoberta de VRF (Multi-Tier)

### Camada 1: Descoberta via NetBox (Pré-conexão)
1. **Por IP do Peer:** Consulta `ipam/ip-addresses/?address=<PEER_IP>`. Se o objeto contiver o campo `vrf`, utiliza `vrf.name`.
2. **Por Prefixo:** Se o IP não tiver VRF direta, consulta `ipam/prefixes/?contains=<PEER_IP>`.
3. **Por Interface:** Se o alerta apontar uma porta física ou SVI, consulta `dcim/interfaces/?device_id=<DEV_ID>&name=<INTF>`.

### Camada 2: Inspeção na Configuração da Interface (In-Session)
Ao conectar via SSH (Netmiko/CLI):
- **Cisco NX-OS:**
  ```bash
  show running-config interface <target_intf>
  ```
  *Regex para VRF:* `\b(?:vrf\s+member|(?:ip\s+)?vrf\s+forwarding)\s+([A-Za-z0-9_-]+)`
- **Cisco IOS-XE / IOS:**
  ```bash
  show running-config interface <target_intf>
  ```
  *Regex para VRF:* `\b(?:ip\s+)?vrf\s+forwarding\s+([A-Za-z0-9_-]+)`
- **Juniper Junos:**
  ```bash
  show configuration interfaces <target_intf>
  show configuration routing-instances | match <target_intf> -B 2
  ```

### Camada 3: Varredura de Tabela de Rotas e BGP por Peer IP
Quando a interface não é conhecida de antemão:
- **Cisco NX-OS:**
  ```bash
  show ip route <peer_ip> vrf all
  ```
  *Captura:* `IP Route Table for VRF "<VRF_NAME>"` (se diferente de `default`, a VRF e a interface de saída aparecem no bloco).
  *Fallback BGP:* `show ip bgp summary vrf all` (procurar o IP sob `BGP summary information for VRF <VRF>`).
- **Cisco IOS-XE:**
  ```bash
  show ip route vrf * <peer_ip>
  ```
  *Captura:* `Routing Table: <VRF_NAME>`
- **Juniper Junos:**
  ```bash
  show route <peer_ip>
  ```
  *Captura:* `<VRF_NAME>.inet.0:` (qualquer routing instance diferente de `inet.0`).

---

## 2. Matriz de Comandos Assertivos por Plataforma

### Cisco NX-OS
* **BGP:**
  ```bash
  show ip bgp neighbors <peer_ip> vrf <vrf>
  show ip route <peer_ip> vrf <vrf>
  show ip arp vrf <vrf> | include <peer_ip>
  ping <peer_ip> vrf <vrf> count 3
  ```
* **Interface / Camada Física:**
  ```bash
  show interface <target_intf>
  show running-config interface <target_intf>
  show ip arp vrf <vrf>
  show mac address-table vlan <vlan_id>
  ```

### Cisco IOS-XE (ASR / Catalyst)
* **BGP:**
  ```bash
  show ip bgp vpnv4 vrf <vrf> neighbors <peer_ip>
  show ip route vrf <vrf> <peer_ip>
  show ip arp vrf <vrf> | include <peer_ip>
  ping vrf <vrf> <peer_ip> count 3
  ```

### Juniper Junos (MX / QFX)
* **BGP & Rota:**
  ```bash
  show bgp neighbor <peer_ip> instance <vrf>
  show route table <vrf>.inet.0 <peer_ip>
  ping <peer_ip> routing-instance <vrf> count 3
  ```
* **Interface:**
  ```bash
  show interfaces <target_intf> brief
  show configuration interfaces <target_intf>
  ```

---

## 3. Formatação no Relatório de Diagnóstico (Slack)
Sempre identificar explicitamente a VRF mapeada e sua origem:
```markdown
🔌 Evidência Coletada ao Vivo do Equipamento (CORE-01-SP4 — VRF: `CIELO` via Interface Ethernet1/10):
# show ip bgp neighbors 10.200.1.2 vrf CIELO
BGP neighbor is 10.200.1.2, remote AS 65100, BGP state = Idle
...
```
