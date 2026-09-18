"""
Alert-Enricher Microservice
Serviço assíncrono para captura e enriquecimento de alertas de infraestrutura (Zabbix/Prometheus)
utilizando contexto do NetBox (DCIM/IPAM) e análise diagnóstica com LLM (LiteLLM/Hermes).
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("alert-enricher")

app = FastAPI(
    title="Alert Enricher Service",
    description="Enriquecimento inteligente de alertas com NetBox e IA",
    version="1.0.0"
)

# -----------------------------------------------------------------------------
# Configurações via Variáveis de Ambiente
# -----------------------------------------------------------------------------
NETBOX_URL = os.getenv("NETBOX_URL", "http://localhost:8000/api").rstrip("/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000/v1").rstrip("/")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-hermes-infra-master-key")
LLM_MODEL = os.getenv("LLM_MODEL", "hermes-primary")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Cache de deduplicação simples em memória (ID do evento -> timestamp)
DEDUP_CACHE: Dict[str, datetime] = {}
DEDUP_TTL_MINUTES = int(os.getenv("DEDUP_TTL_MINUTES", "30"))

http_client = httpx.AsyncClient(timeout=25.0, verify=False)

# -----------------------------------------------------------------------------
# 1. Consulta Contextual ao NetBox
# -----------------------------------------------------------------------------
async def query_netbox(hostname: str, ip: Optional[str] = None) -> Dict[str, Any]:
    """Consulta informações do equipamento no NetBox (DCIM e IPAM)."""
    context = {"device": None, "ip_info": None}
    
    if not NETBOX_URL or not NETBOX_TOKEN:
        logger.warning("NetBox não configurado (URL ou Token ausentes). Pulando consulta.")
        return context

    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Accept": "application/json"
    }

    try:
        # Busca Device pelo nome
        clean_name = hostname.split(".")[0].strip()
        dev_res = await http_client.get(
            f"{NETBOX_URL}/dcim/devices/?name__ic={clean_name}&limit=1",
            headers=headers
        )
        if dev_res.status_code == 200:
            results = dev_res.json().get("results", [])
            if results:
                dev = results[0]
                context["device"] = {
                    "name": dev.get("name"),
                    "role": dev.get("role", {}).get("name") if isinstance(dev.get("role"), dict) else dev.get("device_role", {}).get("name"),
                    "site": dev.get("site", {}).get("name"),
                    "platform": dev.get("platform", {}).get("name"),
                    "serial": dev.get("serial"),
                    "primary_ip": dev.get("primary_ip", {}).get("address") if dev.get("primary_ip") else None
                }
    except Exception as e:
        logger.error(f"Erro ao consultar device no NetBox: {e}")

    # Se fornecido IP ou identificado no alerta, consulta no IPAM
    target_ip = ip or (context["device"]["primary_ip"] if context["device"] else None)
    if target_ip:
        clean_ip = target_ip.split("/")[0].strip()
        try:
            ip_res = await http_client.get(
                f"{NETBOX_URL}/ipam/ip-addresses/?address={clean_ip}&limit=1",
                headers=headers
            )
            if ip_res.status_code == 200:
                results = ip_res.json().get("results", [])
                if results:
                    context["ip_info"] = results[0]
        except Exception as e:
            logger.error(f"Erro ao consultar IP no NetBox: {e}")

    return context

# -----------------------------------------------------------------------------
# 2. Análise Diagnóstica via LLM (LiteLLM)
# -----------------------------------------------------------------------------
async def generate_diagnostic(alert_data: dict, netbox_context: dict) -> str:
    """Solicita ao modelo de IA uma análise técnica baseada no alerta e contexto do NetBox."""
    prompt = f"""
Você é o T-800 InfraOps, especialista sênior em redes, telecomunicações e infraestrutura crítica.
Recebemos um novo alerta do sistema de monitoramento que precisa de análise e triagem imediata.

DADOS DO ALERTA:
- Título/Trigger: {alert_data.get('trigger_name', alert_data.get('event_name', 'Alerta Geral'))}
- Host/Equipamento: {alert_data.get('hostname', 'Desconhecido')}
- Severidade: {alert_data.get('severity', 'High')}
- Detalhes/Valor: {alert_data.get('item_value', alert_data.get('details', 'N/A'))}

CONTEXTO DO NETBOX (DCIM/IPAM):
{json.dumps(netbox_context, indent=2, ensure_ascii=False)}

Gere uma resposta técnica estruturada em Markdown, objetiva e direta:
1. 🎯 Causa Raiz Provável (Hipótese técnica clara)
2. ⚠️ Impacto Operacional Estimado (Serviços e redundâncias afetadas)
3. 🔍 Comandos de Validação (CLI exatos para o operador executar no equipamento)
4. 🛠️ Plano de Ação & Mitigação
"""
    try:
        res = await http_client.post(
            f"{LITELLM_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LITELLM_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "Você é o T-800 InfraOps, engenheiro sênior de infraestrutura."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
        )
        if res.status_code == 200:
            data = res.json()
            return data["choices"][0]["message"]["content"]
        else:
            logger.error(f"Erro no LiteLLM: {res.status_code} - {res.text}")
            return "Não foi possível gerar a análise por IA (Falha na resposta do LiteLLM)."
    except Exception as e:
        logger.error(f"Exceção ao chamar LiteLLM: {e}")
        return f"Erro ao comunicar com LiteLLM: {str(e)}"

# -----------------------------------------------------------------------------
# 3. Notificação (Slack / Telegram)
# -----------------------------------------------------------------------------
async def send_notifications(alert_data: dict, netbox_context: dict, diagnosis: str):
    """Envia o alerta enriquecido para os canais configurados."""
    host = alert_data.get("hostname", "Host")
    trigger = alert_data.get("trigger_name", alert_data.get("event_name", "Alerta"))
    severity = alert_data.get("severity", "Info")

    # Slack Block Kit / Markdown
    if SLACK_BOT_TOKEN and SLACK_CHANNEL_ID:
        try:
            slack_msg = f"🚨 *[{severity}] Alerta Detectado:* `{trigger}`\n"
            slack_msg += f"🖥️ *Equipamento:* `{host}`\n"
            if netbox_context.get("device"):
                d = netbox_context["device"]
                slack_msg += f"📍 *NetBox:* Site: `{d.get('site')}` | Modelo: `{d.get('platform')}` | Função: `{d.get('role')}`\n"
            slack_msg += f"\n---\n*Análise Técnica T-800:*\n{diagnosis}"

            await http_client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": SLACK_CHANNEL_ID, "text": slack_msg}
            )
            logger.info("Notificação enviada ao Slack com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao enviar para o Slack: {e}")

    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_text = f"🚨 *[{severity}] {trigger}*\n"
            tg_text += f"🖥️ *Host:* `{host}`\n\n"
            tg_text += f"{diagnosis}"
            await http_client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": tg_text, "parse_mode": "Markdown"}
            )
            logger.info("Notificação enviada ao Telegram com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao enviar para o Telegram: {e}")

# -----------------------------------------------------------------------------
# 4. Pipeline Principal (Processamento em Background)
# -----------------------------------------------------------------------------
async def process_alert_pipeline(alert_data: dict):
    hostname = alert_data.get("hostname", alert_data.get("host", ""))
    ip = alert_data.get("ip", alert_data.get("host_ip", None))
    
    logger.info(f"Processando alerta para o host: {hostname}")
    
    # 1. NetBox Context
    netbox_context = await query_netbox(hostname, ip)
    
    # 2. Diagnóstico IA
    diagnosis = await generate_diagnostic(alert_data, netbox_context)
    
    # 3. Notificação
    await send_notifications(alert_data, netbox_context, diagnosis)

# -----------------------------------------------------------------------------
# 5. Endpoint de Entrada (Webhook)
# -----------------------------------------------------------------------------
@app.post("/enrich-alert")
async def enrich_alert(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para recebimento de alertas do Zabbix, Prometheus, etc.
    Payload esperado em JSON ou Form Data.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Payload inválido: {e}"}, status_code=400)

    event_id = str(payload.get("event_id", payload.get("id", "")))
    
    # Anti-flapping / Deduplicação
    now = datetime.utcnow()
    if event_id and event_id in DEDUP_CACHE:
        if now - DEDUP_CACHE[event_id] < timedelta(minutes=DEDUP_TTL_MINUTES):
            logger.info(f"Alerta {event_id} ignorado por deduplicação.")
            return {"status": "deduplicated", "event_id": event_id}

    if event_id:
        DEDUP_CACHE[event_id] = now

    # Enfileira processamento assíncrono para responder imediatamente ao webhook do Zabbix (evita timeout)
    background_tasks.add_task(process_alert_pipeline, payload)

    return {"status": "accepted", "event_id": event_id}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "alert-enricher"}
