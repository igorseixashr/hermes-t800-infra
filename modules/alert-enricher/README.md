# 🚨 Alert Enricher — Enriquecimento Inteligente de Alertas

O **Alert Enricher** é um microsserviço assíncrono projetado para resolver o problema clássico de operações de infraestrutura: **alertas frios e sem contexto**.

---

## 🔍 O que ele faz?

Quando um alerta do Zabbix (ou Prometheus) dispara:
1. **Captura via Webhook:** Recebe o alerta via `POST /enrich-alert` instantaneamente.
2. **Consulta o NetBox (DCIM/IPAM):** Descobre automaticamente o site físico, fabricante, modelo, IP de gerência, vizinhos BGP e redundâncias do equipamento.
3. **Diagnóstico via IA (T-800 / LiteLLM):** Envia o alerta + contexto do NetBox para a LLM gerar:
   * 🎯 **Causa raiz provável** (Hipótese técnica clara).
   * ⚠️ **Impacto operacional** (se há redundância no site ou se isola clientes).
   * 🔍 **Comandos CLI prontos para validação** (Cisco, Junos, FortiGate, Linux).
   * 🛠️ **Plano de mitigação imediato**.
4. **Entrega no ChatOps (Slack / Telegram):** Publica uma thread com o diagnóstico formatado.
5. **Anti-Flap & Deduplicação:** Evita tempestades de alertas repetidos com janela de TTL configurável.

---

## ⚙️ Configuração no Zabbix (Webhook Media Type)

No seu Zabbix Server:
1. Vá em **Alerts > Media Types > Create media type**.
2. Tipo: **Webhook**.
3. Parâmetros:
   * `url`: `http://<IP-DO-HERMES>:8080/enrich-alert`
   * `hostname`: `{HOST.NAME}`
   * `ip`: `{HOST.IP}`
   * `trigger_name`: `{EVENT.NAME}`
   * `severity`: `{EVENT.SEVERITY}`
   * `event_id`: `{EVENT.ID}`
   * `item_value`: `{ITEM.LASTVALUE}`
4. Script JavaScript do Zabbix:
   ```javascript
   try {
       var params = JSON.parse(value);
       var req = new HttpRequest();
       req.addHeader('Content-Type: application/json');
       var resp = req.post(params.url, JSON.stringify(params));
       return resp;
   } catch (error) {
       Zabbix.log(3, 'Erro no Alert Enricher Webhook: ' + error);
       throw error;
   }
   ```

---

## 🚀 Como Executar

### Opção 1: Via Docker (Recomendado)
```bash
cd modules/alert-enricher
cp config/enricher.env.example config/enricher.env
# Edite com seus tokens do NetBox e Slack/Telegram
docker compose -f docker-compose.enricher.yml up -d --build
```

### Opção 2: Como Serviço Linux (Systemd)
```bash
sudo cp systemd/alert-enricher.service.example /etc/systemd/system/alert-enricher.service
sudo systemctl daemon-reload
sudo systemctl enable --now alert-enricher
```

---

## 🧩 Adaptação à sua Realidade
* O código em `src/main.py` é enxuto, limpo e modular. Você pode adicionar outros inventários (ex: ServiceNow, AWS EC2, LibreNMS) ou novos destinos de notificação (Microsoft Teams, Discord, PagerDuty).
