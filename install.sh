#!/usr/bin/env bash
# =====================================================================
# HERMES T-800 INFRA - INSTALADOR GUIADO DE AMBIENTE
# =====================================================================
# Desenvolvido para Engenheiros de Infraestrutura e Redes.
# Automatiza a instalação da Fundação de IA (LiteLLM + Redis), Hermes Agent,
# MCP Servers e Base de Conhecimento (Confluence + Neo4j GraphRAG).
# =====================================================================

set -e

# Cores e Estilos ANSI
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/hermes-infra"
HERMES_CONFIG_DIR="$HOME/.hermes"

clear

echo -e "${CYAN}${BOLD}"
cat << "EOF"
=======================================================================
   ████████╗         ██████╗  ██████╗  ██████╗     ██╗███╗   ██╗███████╗██████╗  █████╗ 
   ╚══██╔══╝         ██╔══██╗██╔═████╗██╔═████╗    ██║████╗  ██║██╔════╝██╔══██╗██╔══██╗
      ██║    ███████╗╚██████╔╝██║██╔██║██║██╔██║    ██║██╔██╗ ██║█████╗  ██████╔╝███████║
      ██║    ╚══════╝ ██╔══██╗████╔╝██║████╔╝██║    ██║██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║
      ██║             ██████╔╝╚██████╔╝╚██████╔╝    ██║██║ ╚████║██║     ██║  ██║██║  ██║
      ╚═╝             ╚═════╝  ╚═════╝  ╚═════╝     ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝
=======================================================================
EOF
echo -e "${NC}"
echo -e "${BOLD}Bem-vindo ao instalador do Hermes T-800 InfraOps!${NC}"
echo -e "Este assistente irá preparar seu ambiente de IA para operações de rede, cloud e sistemas."
echo -e "Você será guiado passo a passo, mesmo que seja novo no mundo de IA e Linux.\n"

# Função para pausar e continuar
press_enter() {
    echo -e "${YELLOW}Pressione [ENTER] para continuar...${NC}"
    read -r
}

# ---------------------------------------------------------------------
# ETAPA 1: DIAGNÓSTICO E PRÉ-REQUISITOS DO SISTEMA
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 1/7] Verificando Pré-Requisitos do Sistema${NC}"
echo -e "Vamos verificar se o seu sistema possui as ferramentas básicas necessárias:\n"

# 1.1 Verificar SO
echo -e "  • Sistema Operacional: $(uname -s) ($(uname -m))"

# 1.2 Verificar Docker
echo -n "  • Docker Engine: "
if command -v docker >/dev/null 2>&1; then
    echo -e "${GREEN}Instalado ($(docker --version | cut -d' ' -f3 | tr -d ',')) ✓${NC}"
else
    echo -e "${RED}Não instalado ✗${NC}"
    echo -e "\n${YELLOW}O Docker é essencial para rodar os servidores de IA (LiteLLM, Redis, Neo4j).${NC}"
    read -p "Deseja que o instalador instale o Docker automaticamente agora? (s/N): " install_docker_choice
    if [[ "$install_docker_choice" =~ ^[sS]$ ]]; then
        echo -e "${CYAN}Instalando Docker oficial...${NC}"
        curl -fsSL https://get.docker.com | sudo sh
        sudo usermod -aG docker "$USER"
        echo -e "${GREEN}Docker instalado! (Caso dê erro de permissão posteriormente, faça logoff e login).${NC}"
    else
        echo -e "${RED}Erro: O Docker é obrigatório para continuar. Instale-o e execute este script novamente.${NC}"
        exit 1
    fi
fi

# 1.3 Verificar Docker Compose
echo -n "  • Docker Compose: "
if docker compose version >/dev/null 2>&1; then
    echo -e "${GREEN}Instalado ✓${NC}"
else
    echo -e "${RED}Não detectado ✗ (Instalando plugin do compose...)${NC}"
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null || sudo dnf install -y docker-compose-plugin 2>/dev/null || true
fi

# 1.4 Verificar Python e Git
echo -n "  • Python 3: "
if command -v python3 >/dev/null 2>&1; then
    echo -e "${GREEN}Instalado ($(python3 --version)) ✓${NC}"
else
    echo -e "${RED}Python 3 não encontrado ✗${NC}"
    sudo apt-get install -y python3 python3-pip 2>/dev/null || sudo dnf install -y python3 python3-pip 2>/dev/null
fi

echo -e "\n${GREEN}${BOLD}✓ Pré-requisitos do sistema validados!${NC}\n"
press_enter

# ---------------------------------------------------------------------
# ETAPA 2: CONFIGURAÇÃO DA FUNDAÇÃO DE IA (LiteLLM + REDIS)
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 2/7] Configuração da Fundação de IA (LiteLLM + Redis)${NC}"
echo -e "O que é o LiteLLM? Ele funciona como um 'proxy reverso universal' para modelos de IA."
echo -e "Ele permite que o Hermes se conecte a qualquer provedor (OpenAI, Gemini, Claude, Groq)"
echo -e "com balanceamento de carga, fallback automático e cache em memória (Redis) para economizar tokens.\n"

# Preparar diretório da stack
sudo mkdir -p "$INSTALL_DIR/docker/config"
sudo chown -R "$USER":"$USER" "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/docker/"* "$INSTALL_DIR/docker/"

# Configuração de chaves de API
ENV_FILE="$INSTALL_DIR/docker/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/docker/.env.example" "$ENV_FILE"
fi

echo -e "${CYAN}Agora vamos configurar suas chaves de API de IA.${NC}"
echo -e "Dica: Você precisa de pelo menos UMA chave para o sistema funcionar."
echo -e "Se ainda não tem, o Google Gemini oferece um plano gratuito excelente para testes.\n"

read -p "1. Possui chave do Google Gemini? (Deixe em branco para pular): " input_gemini
if [ -n "$input_gemini" ]; then
    sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$input_gemini|" "$ENV_FILE"
fi

read -p "2. Possui chave da OpenAI (ChatGPT)? (Deixe em branco para pular): " input_openai
if [ -n "$input_openai" ]; then
    sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$input_openai|" "$ENV_FILE"
fi

read -p "3. Possui chave da Anthropic (Claude)? (Deixe em branco para pular): " input_anthropic
if [ -n "$input_anthropic" ]; then
    sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$input_anthropic|" "$ENV_FILE"
fi

read -p "4. Possui chave da Groq (Ultra rápida)? (Deixe em branco para pular): " input_groq
if [ -n "$input_groq" ]; then
    sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$input_groq|" "$ENV_FILE"
fi

read -p "5. Possui chave do OpenRouter? (Deixe em branco para pular): " input_openrouter
if [ -n "$input_openrouter" ]; then
    sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$input_openrouter|" "$ENV_FILE"
fi

# Gerar chaves aleatórias para Redis e LiteLLM se forem default
RANDOM_REDIS=$(openssl rand -hex 12 2>/dev/null || echo "hermes_redis_sec_$(date +%s)")
RANDOM_LITE=$(openssl rand -hex 16 2>/dev/null || echo "sk-hermes_$(date +%s)")
sed -i "s|hermes_redis_secret_password_change_me|$RANDOM_REDIS|" "$ENV_FILE"
sed -i "s|sk-hermes-infra-master-key-change-me|$RANDOM_LITE|" "$ENV_FILE"

echo -e "\n${CYAN}Subindo containers da Fundação (Redis + LiteLLM + Hindsight)...${NC}"
cd "$INSTALL_DIR/docker"
docker compose -f docker-compose.llm-stack.yml up -d

echo -n "Aguardando inicialização do LiteLLM (porta 4000)... "
for i in {1..20}; do
    if curl -s http://localhost:4000/health/liveliness >/dev/null 2>&1; then
        echo -e "${GREEN}ONLINE! ✓${NC}"
        break
    fi
    sleep 2
done

echo -e "\n${GREEN}${BOLD}✓ Fundação de IA ativa e rodando localmente!${NC}\n"
press_enter

# ---------------------------------------------------------------------
# ETAPA 3: INSTALAÇÃO E CONFIGURAÇÃO DO HERMES AGENT CLI
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 3/7] Instalação do Hermes Agent CLI & Skills de Infra${NC}"
echo -e "O Hermes Agent é o assistente autônomo que executa diagnósticos, gera comandos"
echo -e "e interage com sua infraestrutura.\n"

if ! command -v hermes >/dev/null 2>&1; then
    echo -e "${CYAN}Instalando Hermes Agent CLI oficial...${NC}"
    curl -fsSL https://raw.githubusercontent.com/NousResearch/Hermes-Agent/main/scripts/install.sh | bash || {
        echo -e "${YELLOW}Tentando instalação alternativa via pipx/pip...${NC}"
        python3 -m pip install --user hermes-agent || true
    }
else
    echo -e "${GREEN}Hermes Agent já está instalado! ✓${NC}"
fi

# Criar estrutura ~/.hermes
mkdir -p "$HERMES_CONFIG_DIR/skills"

# Gerar config.yaml a partir do template substituindo a master key
echo -e "${CYAN}Configurando ~/.hermes/config.yaml...${NC}"
sed "s|\${LITELLM_MASTER_KEY}|$RANDOM_LITE|g" "$SCRIPT_DIR/config/hermes-config.yaml.template" > "$HERMES_CONFIG_DIR/config.yaml"

# Copiar skills sanitizadas
echo -e "${CYAN}Carregando pacote com 27 skills especializadas em infraestrutura...${NC}"
cp -r "$SCRIPT_DIR/skills/"* "$HERMES_CONFIG_DIR/skills/"

# Criar identidade T-800 personalizada
cat << 'SOUL_EOF' > "$HERMES_CONFIG_DIR/SOUL.md"
# Identity
You are "T-800 InfraOps", a senior network, security, cloud, and infrastructure engineering agent.

# 1. Primary Role
Diagnose, plan, and execute changes across hybrid cloud, enterprise networks (Cisco, Juniper, Fortinet, F5), and Linux systems.

# 2. Decision-Making Style
Hypothesis-first. State the suspected cause, the verification check, and the rollback plan before taking actions.

# 3. Initiative Level
Autonomous for read-only diagnostics, data gathering, config drafting, and analysis. Ask for approval before making state-changing or destructive commands.

# 4. Language & Tone
Respond in PT-BR; keep technical content, CLI commands, and configurations in English. Direct, actionable, and concise.
SOUL_EOF

echo -e "${GREEN}${BOLD}✓ Hermes Agent e Skills de Infraestrutura configurados com sucesso!${NC}\n"
press_enter

# ---------------------------------------------------------------------
# ETAPA 4: MÓDULO OPCIONAL - BASE DE CONHECIMENTO (CONFLUENCE + NEO4J)
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 4/7] Módulo de Conhecimento (Confluence Sync + Neo4j GraphRAG)${NC}"
echo -e "Este módulo permite que o T-800 leia a wiki da sua empresa (Confluence),"
echo -e "converta páginas em Markdown e crie um Grafo de Conhecimento no Neo4j."
echo -e "Assim, o agente sabe de cor suas topologias, faixas de IP e procedimentos operacionais (SOPs).\n"

read -p "Deseja configurar o Confluence Sync e Neo4j GraphRAG agora? (s/N): " setup_graphrag
if [[ "$setup_graphrag" =~ ^[sS]$ ]]; then
    echo -e "\n${CYAN}Configuração do Confluence & Grafo:${NC}"
    read -p "URL do Confluence (ex: https://sua-empresa.atlassian.net/wiki): " conf_url
    read -p "E-mail de Acesso: " conf_user
    read -s -p "API Token do Confluence: " conf_token
    echo ""
    read -p "Chaves dos Espaços para sincronizar (separados por vírgula, ex: INFRA,REDES): " conf_spaces

    # Atualizar .env
    if [ -n "$conf_url" ]; then sed -i "s|^CONFLUENCE_URL=.*|CONFLUENCE_URL=$conf_url|" "$ENV_FILE"; fi
    if [ -n "$conf_user" ]; then sed -i "s|^CONFLUENCE_USERNAME=.*|CONFLUENCE_USERNAME=$conf_user|" "$ENV_FILE"; fi
    if [ -n "$conf_token" ]; then sed -i "s|^CONFLUENCE_API_TOKEN=.*|CONFLUENCE_API_TOKEN=$conf_token|" "$ENV_FILE"; fi
    if [ -n "$conf_spaces" ]; then sed -i "s|^CONFLUENCE_SPACES=.*|CONFLUENCE_SPACES=$conf_spaces|" "$ENV_FILE"; fi

    # Iniciar Neo4j
    echo -e "\n${CYAN}Iniciando container do Neo4j GraphRAG...${NC}"
    cd "$INSTALL_DIR/docker"
    docker compose -f docker-compose.neo4j.yml up -d
    
    # Copiar scripts auxiliares
    sudo mkdir -p "$INSTALL_DIR/scripts"
    cp "$SCRIPT_DIR/scripts/"* "$INSTALL_DIR/scripts/"
    chmod +x "$INSTALL_DIR/scripts/"*

    # Instalar dependências Python no ambiente do usuário
    pip install neo4j mcp --quiet || true

    echo -e "${GREEN}✓ Módulo Confluence + Neo4j GraphRAG habilitado!${NC}"
else
    echo -e "${YELLOW}Módulo Confluence/Neo4j pulado. Você pode ativá-lo a qualquer momento depois.${NC}"
fi

echo ""
press_enter

# ---------------------------------------------------------------------
# ETAPA 5: CONECTORES MCP DE INFRAESTRUTURA (NETBOX, CISCO, ETC)
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 5/7] Conectores MCP (Model Context Protocol)${NC}"
echo -e "O MCP permite ao Hermes se conectar a ferramentas externas de rede como NetBox (IPAM)."

read -p "Você utiliza o NetBox na sua empresa e gostaria de configurá-lo? (s/N): " setup_netbox
if [[ "$setup_netbox" =~ ^[sS]$ ]]; then
    read -p "URL do NetBox (ex: https://netbox.empresa.local): " netbox_url
    read -s -p "API Token do NetBox: " netbox_token
    echo ""
    
    # Exportar no bashrc do usuário para persistência
    echo "export NETBOX_URL=\"$netbox_url\"" >> "$HOME/.bashrc"
    echo "export NETBOX_TOKEN=\"$netbox_token\"" >> "$HOME/.bashrc"
    echo -e "${GREEN}✓ NetBox configurado!${NC}"
fi

echo ""
press_enter

# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# ETAPA 6: MÓDULO OPCIONAL - ENRIQUECIMENTO DE ALERTAS (ZABBIX + NETBOX + IA)
# ---------------------------------------------------------------------
echo -e "[Etapa 6/7] Módulo: Enriquecimento Inteligente de Alertas (Alert Enricher)"
echo -e "O que é o Alert Enricher?"
echo -e "É um microsserviço que recebe webhooks de alertas do Zabbix ou Prometheus,"
echo -e "cruza dados no NetBox para descobrir fabricante, site, modelo e vizinhos BGP,"
echo -e "passa pelo LiteLLM/Hermes para gerar a causa-raiz e comandos CLI de validação,"
echo -e "e posta o diagnóstico completo em uma thread no Slack ou Telegram.
"

read -p "Deseja importar e configurar o Alert Enricher agora? (s/N): " setup_enricher
if [[ "" =~ ^[sS]$ ]]; then
    sudo mkdir -p "/modules/alert-enricher"
    cp -r "/modules/alert-enricher/"* "/modules/alert-enricher/"
    ENRICHER_ENV="/modules/alert-enricher/config/enricher.env"
    if [ ! -f "" ]; then
        cp "/modules/alert-enricher/config/enricher.env.example" ""
    fi
    sed -i "s|sk-hermes-infra-master-key-change-me||" ""
    if [ -n "" ]; then sed -i "s|^NETBOX_URL=.*|NETBOX_URL=|" ""; fi
    if [ -n "" ]; then sed -i "s|^NETBOX_TOKEN=.*|NETBOX_TOKEN=|" ""; fi

    echo -e "
Notificações do Alerta:"
    read -p "Possui Bot Token do Slack (xoxb-...)? (Pressione Enter para pular): " slack_token
    if [ -n "" ]; then
        read -p "ID do Canal no Slack (ex: C0123456789): " slack_chan
        sed -i "s|^SLACK_BOT_TOKEN=.*|SLACK_BOT_TOKEN=|" ""
        sed -i "s|^SLACK_CHANNEL_ID=.*|SLACK_CHANNEL_ID=|" ""
    fi

    echo -e "
Deseja subir o container do Alert Enricher na porta 8080? (s/N): "
    read -r start_enricher_container
    if [[ "" =~ ^[sS]$ ]]; then
        cd "/modules/alert-enricher"
        docker compose -f docker-compose.enricher.yml up -d --build
        echo -e "✓ Alert Enricher rodando em http://localhost:8080/enrich-alert!"
    fi
else
    echo -e "Alert Enricher não iniciado. Os scripts e guias estão disponíveis em modules/alert-enricher/."
fi

echo ""
press_enter

# ---------------------------------------------------------------------
# ETAPA 7: HEALTH CHECK FINAL E PRIMEIROS PASSOS
# ---------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Etapa 7/7] Validação Final do Ambiente${NC}\n"

bash "$SCRIPT_DIR/scripts/check_health.sh"

echo -e "\n${GREEN}${BOLD}=======================================================================${NC}"
echo -e "${GREEN}${BOLD}           PARABÉNS! SEU HERMES T-800 INFRA ESTÁ PRONTO!              ${NC}"
echo -e "${GREEN}${BOLD}=======================================================================${NC}\n"

echo -e "${BOLD}Como começar:${NC}"
echo -e "  1. Digite ${CYAN}hermes${NC} no seu terminal para iniciar uma conversa com o agente."
echo -e "  2. Exemplos de comandos e pedidos que você pode fazer:"
echo -e "     • ${YELLOW}\"Qual o procedimento para verificar sessões BGP em roteadores Juniper?\"${NC}"
echo -e "     • ${YELLOW}\"Analise esse log de interface com flapping no switch Cisco e sugira a causa.\"${NC}"
echo -e "     • ${YELLOW}\"Crie um script para checar latência OWAMP/TWAMP entre dois pontos da rede.\"${NC}"
echo -e "     • ${YELLOW}\"Como configurar uma VIP e Pool no F5 BIG-IP via tmsh?\"${NC}\n"

echo -e "${BOLD}Comandos de Gerenciamento:${NC}"
echo -e "  • Diagnóstico do sistema:      ${CYAN}$SCRIPT_DIR/scripts/check_health.sh${NC}"
echo -e "  • Ver logs da fundação de IA:  ${CYAN}docker logs -f litellm-proxy${NC}"
echo -e "  • Reiniciar containers:        ${CYAN}cd $INSTALL_DIR/docker && docker compose -f docker-compose.llm-stack.yml restart${NC}\n"

echo -e "${MAGENTA}Obrigado por utilizar o Hermes T-800 InfraOps!${NC}\n"
