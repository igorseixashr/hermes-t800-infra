#!/usr/bin/env bash
# =====================================================================
# HERMES T-800 INFRA - DIAGNÓSTICO E HEALTH CHECK
# =====================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}  HERMES T-800 INFRA - HEALTH CHECK DO AMBIENTE     ${NC}"
echo -e "${BLUE}=====================================================${NC}\n"

# 1. Checagem do Docker
echo -n "[*] Verificando Docker Engine: "
if systemctl is-active --quiet docker || docker info >/dev/null 2>&1; then
    echo -e "${GREEN}ONLINE ✓${NC}"
else
    echo -e "${RED}OFFLINE ou sem permissão ✗${NC}"
fi

# 2. Checagem dos Containers da Fundação
echo -n "[*] Container LiteLLM (litellm-proxy): "
if docker ps --format '{{.Names}}' | grep -q "litellm-proxy"; then
    echo -e "${GREEN}UP ✓${NC}"
else
    echo -e "${RED}DOWN ✗${NC}"
fi

echo -n "[*] Container Redis (redis-cache): "
if docker ps --format '{{.Names}}' | grep -q "redis-cache"; then
    echo -e "${GREEN}UP ✓${NC}"
else
    echo -e "${RED}DOWN ✗${NC}"
fi

echo -n "[*] Container Hindsight: "
if docker ps --format '{{.Names}}' | grep -q "hindsight"; then
    echo -e "${GREEN}UP ✓${NC}"
else
    echo -e "${YELLOW}OFF (Opcional)${NC}"
fi

echo -n "[*] Container Neo4j GraphRAG: "
if docker ps --format '{{.Names}}' | grep -q -E "neo4j|hermes-neo4j"; then
    echo -e "${GREEN}UP ✓${NC}"
else
    echo -e "${YELLOW}OFF (Módulo opcional não iniciado)${NC}"
fi

# 3. Teste de Conectividade HTTP do LiteLLM
echo -n "[*] Conectividade API LiteLLM (http://localhost:4000/health/liveliness): "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4000/health/liveliness 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}OK (HTTP 200) ✓${NC}"
else
    echo -e "${RED}FALHA (HTTP $HTTP_CODE) ✗${NC}"
fi

# 4. Checagem do Hermes CLI
echo -n "[*] Binário do Hermes Agent CLI: "
if command -v hermes >/dev/null 2>&1; then
    HERMES_VER=$(hermes --version 2>/dev/null || echo "instalado")
    echo -e "${GREEN}DETECTADO ($HERMES_VER) ✓${NC}"
else
    echo -e "${RED}NÃO ENCONTRADO NO PATH ✗${NC}"
fi

# 5. Checagem das Skills de Infra
echo -n "[*] Skills de Infraestrutura em ~/.hermes/skills: "
if [ -d "$HOME/.hermes/skills" ]; then
    SKILL_COUNT=$(find "$HOME/.hermes/skills" -name "SKILL.md" | wc -l)
    echo -e "${GREEN}${SKILL_COUNT} skills carregadas ✓${NC}"
else
    echo -e "${YELLOW}Diretório de skills não encontrado${NC}"
fi

echo -e "\n${BLUE}=====================================================${NC}"
echo -e "${BLUE}  Diagnóstico concluído!                            ${NC}"
echo -e "${BLUE}=====================================================${NC}"
