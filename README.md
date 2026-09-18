# 🤖 Hermes T-800 InfraOps — Starter Kit & Blueprint

Um kit completo, automatizado e guiado para implantar o **Hermes Agent** com foco em **Infraestrutura, Redes, Segurança e Cloud**.

Criado para engenheiros de infraestrutura, redes e SREs que desejam utilizar Inteligência Artificial avançada em suas operações diárias, mesmo que estejam começando agora no ecossistema de LLMs e Linux.

---

## 🏛️ Arquitetura do Sistema

```text
               ┌───────────────────────────────────────────────────┐
               │              SEU TERMINAL / CONSOLE               │
               │               (hermes cli / tui)                  │
               └─────────────────────────┬─────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                           HERMES AGENT ENGINE                               │
  │  • Identidade: T-800 InfraOps (Investigação por hipóteses & rollbacks)       │
  │  • 27 Skills de Infra: Cisco, Juniper BGP, Fortinet, F5, OWAMP, Zabbix, etc │
  │  • Ferramentas: Terminal, Leitura/Edição de Arquivos, Web Search, Scripts   │
  └──────────────┬───────────────────────────────┬──────────────────────────────┘
                 │                               │
                 │ (Consultas LLM)               │ (Protocolo MCP)
                 ▼                               ▼
  ┌──────────────────────────────┐ ┌────────────────────────────────────────────┐
  │   FUNDAÇÃO DE IA (Docker)    │ │        CONECTORES MCP (Extensões)          │
  │                              │ │                                            │
  │ ┌──────────────────────────┐ │ │  • NetBox MCP: Topologia & IPAM            │
  │ │      LiteLLM Proxy       │ │ │  • Neo4j GraphRAG: Grafo de Conhecimento   │
  │ │  (Unifica OpenAI, Gemini │ │ │  • Cisco / FortiGate MCPs: Status e Logs   │
  │ │   Claude, Groq e Ollama) │ │ └────────────────────────────────────────────┘
  │ └────────────┬─────────────┘ │
  │              ▼               │ ┌────────────────────────────────────────────┐
  │ ┌──────────────────────────┐ │ │     BASE DE CONHECIMENTO (Opcional)        │
  │ │       Redis Cache        │ │ │                                            │
  │ │ (Economia de tokens/cache│ │ │  • Confluence Sync: Extrai SOPs/Docs       │
  │ └──────────────────────────┘ │ │  • Neo4j 5.26: Grafo de nós & relações     │
  └──────────────────────────────┘ └────────────────────────────────────────────┘
```

---

## 🚀 Instalação Rápida (One-Liner)

Em sua máquina Linux (Ubuntu, Debian, RHEL, CentOS ou Rocky Linux):

```bash
# 1. Clone o repositório
git clone https://github.com/igorseixashr/hermes-t800-infra.git
cd hermes-t800-infra

# 2. Execute o instalador guiado
bash install.sh
```

O instalador irá:
1. Validar e instalar pré-requisitos (Docker, Docker Compose, Python, Git).
2. Perguntar quais chaves de IA você tem (Google Gemini, OpenAI, Claude, Groq, etc.).
3. Subir a stack do LiteLLM + Redis em Docker.
4. Instalar o Hermes Agent e copiar as 27 skills especializadas.
5. Perguntar se deseja ativar a sincronização do Confluence e Grafo Neo4j.
6. Rodar o diagnóstico de saúde e deixar tudo pronto.

---

## 📦 O que está incluído no pacote?

### 1. Fundação de IA (`docker/`)
* **LiteLLM Proxy:** Padroniza as chamadas de API. Você pode alternar entre Gemini, GPT-4o, Claude 3.5 Sonnet ou até modelos locais (Ollama) sem alterar uma linha de código do agente.
* **Redis Cache:** Guarda o cache de requisições idênticas para acelerar respostas e economizar dinheiro/tokens.
* **Hindsight:** Camada de memória semântica de longo prazo.

### 2. Pacote de 27 Skills de Infraestrutura (`skills/`)
Habilidades especializadas que ensinam o agente a operar equipamentos e protocolos:
* **Cisco:** Comandos e troubleshooting para Nexus (NX-OS), Catalyst, Mgmt-VRF e TFTP.
* **Juniper & BGP:** Operações de BGP, failover de links e engenharia de tráfego Junos.
* **Firewalls & Segurança:** Fortinet FortiGate, SSL/TLS Mismatch e mitigação de vulnerabilidades.
* **F5 BIG-IP:** Diagnóstico de Virtual Servers, Pools, monitores e LTM.
* **Observabilidade:** Monitoramento de latência OWAMP/TWAMP, dashboards Grafana e onboarding Zabbix SNMP.
* **Cloud Networking:** Monitoramento de AWS Direct Connect/Transit Gateway, Azure ExpressRoute e GCP Interconnect.
* **Containers & Linux:** Docker management, rotação de logs, Elastic Stack e systemd daemons.

### 3. Base de Conhecimento Confluence + Neo4j GraphRAG (`scripts/`)
* **`confluence_sync.py`:** Baixa automaticamente seus espaços de documentação e diagramas do Confluence e converte para Markdown limpo em `~/wiki/`.
* **`neo4j_graph_ingest.py`:** Extrai IPs, sub-redes, nomes de roteadores/switches e links de SOPs, montando um grafo interconectado.
* **`neo4j_mcp_server.py`:** Servidor MCP que permite ao agente consultar o grafo via linguagem natural ou queries Cypher.

---

## 💡 Como Usar no Dia a Dia

Após a instalação, abra seu terminal e digite:
```bash
hermes
```

### Exemplos de Perguntas e Tarefas para o T-800:

#### 1. Diagnóstico de Rede e Roteamento
> *"T-800, estou com perda de pacotes e suspeita de flapping na sessão BGP com o provedor. Quais comandos devo rodar no Juniper e o que devo procurar nos logs?"*

#### 2. Elaboração de Configurações
> *"Gere a configuração de uma nova VLAN 150 e uma interface SVI no Cisco Nexus NX-OS com HSRP ativo."*

#### 3. Troubleshooting de Firewalls
> *"Preciso liberar o tráfego da subnet 10.50.0.0/24 para o servidor web 192.168.10.20 na porta 443 no FortiGate. Monte os comandos via CLI."*

#### 4. Consultas na Base de Conhecimento Local (GraphRAG)
> *"T-800, consulte no grafo quais são os roteadores e sub-redes citados no documento de topologia do Datacenter."*

---

## 🛠️ Comandos de Manutenção e Diagnóstico

* **Testar o status do ambiente:**
  ```bash
  bash scripts/check_health.sh
  ```
* **Ver logs do LiteLLM (para ver as chamadas de IA acontecendo):**
  ```bash
  docker logs -f litellm-proxy
  ```
* **Reiniciar a fundação de IA:**
  ```bash
  cd /opt/hermes-infra/docker && docker compose -f docker-compose.llm-stack.yml restart
  ```
* **Sincronizar a documentação do Confluence manualmente:**
  ```bash
  python3 scripts/confluence_sync.py
  python3 scripts/neo4j_graph_ingest.py
  ```

---

## 🔒 Segurança e Privacidade

* **Local-First:** Todo o histórico de conversas, arquivos, banco de dados Redis e Neo4j rodam exclusivamente na máquina local.
* **Credenciais Protegidas:** Nenhuma chave de API ou credencial corporativa é compartilhada externamente. O arquivo `.env` fica restrito à máquina e está devidamente adicionado ao `.gitignore`.

---

**Desenvolvido com foco em alta eficiência operacional para Engenharia de Infraestrutura.**
