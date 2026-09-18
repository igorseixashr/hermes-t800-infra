# BGP Peer Identification Heuristics

Esta referência detalha como identificar vizinhos BGP quando o endereço IP do Peer não está explicitamente documentado como um objeto `IP Address` no NetBox.

## 1. Prefix Inference
Quando o IP do peer (ex: `10.152.255.138`) não retorna resultados no IPAM:
1. **Search Prefixes**: Busque pelo prefixo que contém o IP (ex: `10.152.255.136/29` ou a rede pai `10.152.255.0/24`).
2. **Interpret Description**:
    - `TRANSIT-FGT-CORE`: O vizinho é um FortiGate (Firewall). O peering ocorre entre o Core Switch e o Firewall.
    - `TRANSIT-INET-RT`: O vizinho é um Edge Router (Internet).
    - `TRANSIT-RT-PARTNER`: O vizinho é um roteador de parceiro/B2B.
3. **Subnet Math**: Em prefixos `/29`, os IPs costumam seguir o padrão:
    - `.x`: Core-01 / Core-02 (IPs iniciais)
    - `.y`: Firewall-01 / Firewall-02 (IPs finais ou específicos do Gateway).
    *(Ajustar conforme o `site_id` e a convenção local).*

## 2. Redundancy Verification
Sempre compare o estado do peer no dispositivo alertado com o seu par redundante:
- **Ambos Down**: Problema provável no vizinho (FortiGate) ou no transporte comum (VLAN L2).
- **Apenas Um Down**: Problema provável na interface física local, configuração de BGP específica do membro ou rota específica do membro.

## 3. Credential Discovery
As credenciais para acesso CLI aos dispositivos de rede (read-only) para validação de `show` commands estão em:
- `~/.bashrc.d/network-creds.env`
- Variáveis: `NET_USER`, `NET_PASS`.
