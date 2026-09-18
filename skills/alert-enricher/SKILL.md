---
name: alert-enricher
description: Enriquecimento de alertas Zabbix com dados do NetBox e diagnósticos de IA.
usage: Recebe payload do Zabbix, consulta NetBox via MCP e gera análise técnica.
---

# Alert Enricher (Zabbix + NetBox + LLM)

Skill especializada em receber alertas de infraestrutura (Zabbix), enriquecer com contexto de inventário (NetBox) e gerar diagnósticos acionáveis usando LLM.

## Trigger Conditions
- Recebimento de alertas via Webhook do Zabbix.
- Solicitação manual de análise de log ou alerta de rede.

## Procedure

### 0. Automação de Aprendizado (Hindsight)
- Sempre que um incidente for resolvido com sucesso, utilize o script `scripts/retain-incident.py` para salvar o aprendizado.
- **Uso**: `python3 scripts/retain-incident.py "<descrição da solução>"`
- Isso garante que alertas recorrentes sejam automaticamente enriquecidos com a solução histórica no próximo disparo.

### 1. Data Cleaning & Extraction
- **BGP Normalization**: Remover prefixos `1.4.` de OIDs de SNMP que aparecem em mensagens de BGP.
- **Peer IP Extraction**: Identificar IPs de vizinhos BGP em triggers/descrições usando regex: `(?:peer|neighbor|bgp)[^\d]*([\d]{1,3}(?:\.[\d]{1,3}){3})`.
- **Hostname Sanitization**: Remover prefixos de fabricante (ex: `Cisco Router Catalyst`, `Nexus Switch`), chaves `{}` e espaços extras.
- **Hostname Sanitization**: Remover prefixos de fabricante (ex: `Cisco Router Catalyst`, `Nexus Switch`), chaves `{}` e espaços extras. Normalizar numeração (ex: substituir `-1-`, `-2-` por `-01-`, `-02-`) para bater com padrões de inventário.

### 2. Context Gathering (NetBox)
⚠️ **CRITICAL PERFORMANCE OPTIMIZATION (READ FIRST)**:
Antes de fazer qualquer chamada ao MCP do NetBox, **leia atentamente o histórico da thread do Slack**. 
Se a mensagem inicial do alerta (postada pelo microsserviço Python) **já contém os detalhes do NetBox** (como *Device*, *Site*, *Role*, *Platform*, *Primary IP*, *ASN*, *Serial* e dados de *Peer BGP*), **NÃO realize consultas redundantes ao MCP**. Use os dados já impressos na thread diretamente para formular seu diagnóstico. Isso reduz a latência da resposta de minutos para segundos.

Se as informações estiverem ausentes ou incompletas, utilize as ferramentas de MCP do NetBox para coletar apenas o necessário, preferencialmente em paralelo:
1. **Device Details**: Nome, Role, Site, Platform, Serial, Tenant e ASN via `mcp_netbox_get_devices`.
2. **Interfaces**: Listar via `mcp_netbox_get_interfaces(params={"device_id": ID})`.
3. **Historical State & Flapping**: Utilizar `session_search` com o hostname e/ou Peer IP para identificar se o alerta é recorrente ou se houve "falsos positivos" de recuperação (ex: BGP mudando de IDLE para ACTIVE).
3. **IP Addresses**: Buscar IPs associados ao device e ao Peer BGP.
    - *Heurística*: Se a busca direta pelo IP do Peer falhar, busque o prefixo (`mcp_netbox_get_prefixes`) que contém o IP. Analise o nome/descrição do prefixo (ex: `TRANSIT-FGT-CORE`) para deduzir o papel do vizinho (ex: Firewall FortiGate). Ver `references/bgp-peer-identification-heuristics.md`.
4. **Site Context & Redundancy**: Listar outros dispositivos no mesmo `site_id` para identificar pares redundantes (ex: CORE-01 vs CORE-02) e comparar estados.
6. **Recent Changes**: Buscar os últimos 3 changelogs/entries do device (Atenção: ver Pitfalls sobre este endpoint).

### 3. Slack Delivery (Threaded Deep Dive Pattern)
- **Identidade e Persona (T-800)**: Sempre se apresente e se refira a si mesmo como **T-800** (ou **T-800 InfraOps**), NUNCA como "Hermes" (Hermes é apenas a plataforma de execução/runtime). Em diagnósticos, respostas e threads no Slack, a persona oficial perante a equipe corp/corp é exclusivamente **T-800**.
- **Fuzzy Rack Search**: Se o Hostname falhar, busque pelo Rack ID via `dcim/racks` usando o sufixo do nome (ex: `R2C03`) para localizar dispositivos adjacentes.
- **API Permissions (403/404)**: O endpoint `extras/object-changes` pode retornar 404 (versão antiga da API) ou 403 (falta de permissão) no ambiente corp. Se falhar, não insista; relate como "Indisponível no momento".
- **False 'Resolved' Status**: O Zabbix pode dar OK se o estado BGP mudar (ex: 1 para 3), mas apenas o estado 6 (Established) garante o serviço UP. Sempre verifique o histórico da sessão para confirmar se não é um flap.
- **SSH Connectivity**: Em ambientes como a corp/Equinix, o acesso SSH ao IP de gerência (`mgmt0`) pode sofrer timeout ou exigir saltos específicos. Se o ping responder mas o SSH falhar, verifique ACLs de gerência ou use o console OOB se disponível.
- **Invisible Devices (Partner/Legacy)**: Se o Hostname não existir no NetBox (`dcim/devices`), ele provavelmente é um **ALP (Autorizador Legado de Parceiro)** ou equipamento B2B localizado em site de terceiro. 
    1. Busque pelo Hostname no Jira/Confluence (docs legadas e cards de infra).
    2. Busque por Circuitos (`circuits/circuits`) ou VLANs com o nome do parceiro.
    3. Verifique o estado do Peer BGP nos Core Switches do site correspondente (ver `references/partner-legacy-device-investigation.md`).
    4. **[NOVO]** Equipamentos Sodexo ALP são sabidamente EoL e recorrentes em alertas de indisponibilidade (veja histórico de `SODEXO-ALP-1` em `references/sodexo-legacy-infrastructure.md`). Não realizar intervenções automáticas; confirmar se o alerta é um 'flap' de transporte (parceiro/Algar/Tivit) antes de acionar on-site.


## Deployment & Troubleshooting (Rocky/RHEL/SELinux)
- **Port Conflict**: Evitar porta `8000` (comum em Docker proxies como `irdmi`). Usar `8080` para o serviço FastAPI.
- **Systemd Security**:
  - Permissões: Arquivos `.service` em `/etc/systemd/system/` devem ser `644` e pertencer ao `root:root`.
  - **SELinux**: Se o serviço falhar com "Permission Denied" após edição, execute `sudo restorecon -v /etc/systemd/system/<service_name>` para restaurar o contexto `systemd_unit_file_t`.
- **Zabbix 5.0 Compatibility**: Esta versão não possui a função `hmac()` no motor JS. Use o modo `INSECURE_NO_AUTH` no Hermes e o template `templates/zabbix-5.0-enricher-script.js`.

## Pitfalls
- **Slack Message Limits (`msg_too_long`)**: Detailed diagnostics with large NetBox dumps or full routing tables can exceed Slack's character limit. When generating reports, prioritize the *interpretation* and key *summary* over raw data dumps. If a large dump is necessary, use `write_file` to create a `.log` or `.txt` and upload it, or split into multiple messages.
- **Async Await**: Funções críticas de persistência (como `is_duplicate`, `index_set`, `index_update`) DEVEM ser aguardadas com `await`. Chamá-las de forma síncrona causa race conditions no EVENT_INDEX e falhas na deduplicação de alertas.
- **Fuzzy Rack Search**: Se o Hostname falhar, busque pelo Rack ID via `dcim/racks` usando o sufixo do nome (ex: `R2C03`) para localizar dispositivos adjacentes.
- **False 'Resolved' Status**: O Zabbix pode dar OK se o estado BGP mudar (ex: 1 para 3), mas apenas o estado 6 (Established) garante o serviço UP. Sempre verifique o histórico da sessão para confirmar se não é um flap.
- **SSH Connectivity**: Em ambientes como a corp/Equinix, o acesso SSH ao IP de gerência (`mgmt0`) pode sofrer timeout ou exigir saltos específicos. Se o ping responder mas o SSH falhar, verifique ACLs de gerência ou use o console OOB se disponível.
- **Invisible Devices (Partner/Legacy)**: Se o Hostname não existir no NetBox (`dcim/devices`), ele provavelmente é um **ALP (Autorizador Legado de Parceiro)** ou equipamento B2B localizado em site de terceiro. 
    1. Busque pelo Hostname no Jira/Confluence (docs legadas e cards de infra).
    2. Busque por Circuitos (`circuits/circuits`) ou VLANs com o nome do parceiro.
    3. Verifique o estado do Peer BGP nos Core Switches do site correspondente (ver `references/partner-legacy-device-investigation.md`).
    4. **[NOVO]** Equipamentos Sodexo ALP são sabidamente EoL e recorrentes em alertas de indisponibilidade (veja histórico de `SODEXO-ALP-1` em `references/sodexo-legacy-infrastructure.md`). Não realizar intervenções automáticas; confirmar se o alerta é um 'flap' de transporte (parceiro/Algar/Tivit) antes de acionar on-site.

## Commands Reference & LLM Docs
- `mcp_netbox_get_devices(params={"name": hostname})`
- `mcp_netbox_get_ip_addresses(params={"address": ip})`
- **NetBox LLM Documentation**: Documentação oficial injetada em `~/kb-sync/confluence-files/netbox-llms/` (`netbox-llms-full.md` e `netbox-llms-api-full.md`) para referência rápida de modelos de dados, DCIM, IPAM e endpoints da REST API.
- **Cisco NX-OS**: `show ip bgp neighbors <IP> [vrf <VRF>]`, `show ip route <IP> [vrf all|vrf <VRF>]`.
- **Linked Files**: 
  - `references/partner-vrf-discovery-and-diagnostics.md`: Descoberta em camadas de VRF e tshoot assertivo para links de parceiros (corp/corp).
  - `references/architecture-and-performance.md`: Detalhes de arquitetura híbrida (Uvicorn vs Socket Mode) e otimização de performance.
  - `references/bgp-snmp-normalization.md`: Normalização de OIDs.
  - `references/nexus-management-connectivity.md`: Troubleshooting de gerência mgmt0 em Nexus.
  - `references/ios-xe-bgp-idle-zero.md`: Estados BGP específicos de IOS-XE.
  - `references/sodexo-legacy-infrastructure.md`: Detalhes sobre roteadores Sodexo legados (ALP-1/2).
  - `references/partner-legacy-device-investigation.md`: Investigação de ativos legados/B2B (ALP) fora do NetBox.
  - `references/nexus-nxos-bgp-diagnostics.md`: Estados BGP específicos de Nexus.
