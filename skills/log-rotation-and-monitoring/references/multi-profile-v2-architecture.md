# Multi-perfil v2 — evoluindo o probe single-config para perfis isolados

Quando o usuário pede para transformar o monitor single-config (um `targets.txt`,
um `dns.txt`, uma engine a 1s, CSV semanal) num sistema **multi-perfil** com tela
de configuração, controle start/stop e banco por perfil, este é o desenho validado
(FPDC Generic Connectivity Tester v2, homologado em 10.166.41.250 lado a lado com a v1).

## Princípio de deploy: lado a lado, NÃO in-place
Uma reescrita arquitetural grande (~60% backend, ~70% frontend) NÃO substitui a v1
direto. Suba a v2 num **serviço systemd separado** (`fpdc-tester`), **porta separada**
(8001), **diretório próprio** (`/opt/fpdc-tester/`), venv próprio. A v1 (porta 8000)
fica intacta como fallback. Só promove pra 8000 quando o usuário validar visualmente.
O instalador da v2 é uma cópia do `install.sh` da v1 com nomes/porta/dirs trocados e
variáveis de ambiente `FPDC_*` no unit.

## Promoção/cutover: v2 assume a porta 8000 (aposentando a v1)
Depois que o usuário valida a v2 na 8001 e pede para promover (ou já manda fazer
in-place direto), o cutover por host é simples e reversível. SEMPRE confirme com o
usuário se a v1 deve ser apenas parada+desabilitada (recomendado, vira fallback) ou
removida. Procedimento (cada passo aprovável isolado — restart de serviço passa pelo
gate):
1. **Backup** da config v1 (`cp -p /opt/probe_web/targets.txt{,.bak-cutover}` e idem `dns.txt`).
2. **Parar + desabilitar a v1**: `systemctl stop dns-tcp-monitor-api && systemctl disable dns-tcp-monitor-api` (libera a porta 8000; NÃO remove o unit → religável se algo der errado).
3. **Flipar a porta da v2 para 8000 no unit** (se ela já estava na 8001):
   `sed -i "s/FPDC_PORT=8001/FPDC_PORT=8000/; s/--port 8001/--port 8000/" /etc/systemd/system/fpdc-tester.service` → `systemctl daemon-reload && systemctl restart fpdc-tester`.
   Em host onde a v2 ainda nem existe, instale direto com `sudo FPDC_PORT=8000 bash install.sh` (o instalador aceita override por env e a migração do perfil RSFN puxa o `targets.txt`/`dns.txt` locais daquele host — cada host preserva os seus).
4. **Validar na 8000**: `systemctl is-active fpdc-tester` + `curl -o /dev/null -w '%{http_code}' http://localhost:8000/` (200) + `/profiles` listando o perfil RSFN com o nº de alvos/DNS esperado.
- Detalhe: perfis criados pela tela de config (ex.: um `ELO-FABRIC` que o usuário adicionou durante o teste) **persistem** em `/opt/fpdc-tester/profiles/` e sobrevivem ao cutover — confirma que a UI de config grava de verdade.
- O usuário pode preferir aplicar o cutover **em todas as N máquinas de uma vez** (on-prem + AWS via SSM) em vez de uma-por-vez; respeite a escolha, mas mantenha backup+validação por host.

## Modularização (vs. arquivo único da v1)
A v1 era um `monitor_web.py` monolítico (~1200 linhas). A v2 quebra em módulos —
mais fácil de editar com `patch`/`write_file` e de testar isoladamente:
- `storage.py`   — SQLite por perfil/semana, query_history / query_summary / cleanup.
- `profiles.py`  — ProfileManager (CRUD de JSON), normalização, migração da v1.
- `probes.py`    — núcleo TCP/UDP/ICMP/DNS extraído sem alterar comportamento (reuso).
- `engine.py`    — ProfileEngine (um por perfil) + Orchestrator (repouso vs ativo).
- `app.py`       — FastAPI: rotas, WebSocket, /stats Prometheus.
- `web_ui.py`    — HTML/JS embutido (string única `HTML_PAGE`).

## Modelo de perfil (JSON, um arquivo por perfil)
`<PROFILES_DIR>/<slug>.json`. NÃO use pares `targets_X.txt`/`dns_X.txt` soltos
(dessincronizam). Campos: `name`, `interval_normal` (60), `interval_active` (1),
`dns_servers[]`, `targets[]` (`{host,port,proto,service}`). `slugify()` (regex
`[^A-Za-z0-9_-]+` → `_`) gera nome de arquivo/dir seguro, compartilhado entre
storage e profiles para casar perfil↔banco.

## Migração automática da v1 (zero perda)
No `startup`, `pm.migrate_from_v1_if_empty(V1_TARGETS, V1_DNS, "RSFN")`: se não há
nenhum perfil, lê os `targets.txt`/`dns.txt` legados (mesmo parser tolerante da v1 —
3º campo = dica de DNS, ignorado) e cria o perfil inicial. Idempotente: se já há
perfis, não faz nada. Caminhos legados vêm de env (`FPDC_V1_TARGETS`/`FPDC_V1_DNS`).
No cutover, manter esses envs apontando pro `/opt/probe_web` local garante o pedido
recorrente do usuário de "preservar os targets/dns atuais" — cada host migra os seus.

## Storage: SQLite, NÃO "pglite"
Usuário pode pedir "pglite ou banco rápido" — **pglite é JS/WASM, não serve backend
Python**. O certo é `sqlite3` (stdlib, zero deps novas). Layout:
`<DATA_DIR>/<profile_slug>/<ISOYEAR>-W<ISOWEEK>.db`, tabela única `samples`
(`ts,host,port,proto,service,status,rtt_ms,dns`), índice `(host,port,proto,ts)`.
PRAGMA `journal_mode=WAL` + `synchronous=NORMAL`. Estatísticas (avg/p95/jitter/uptime)
viram SQL sobre a **semana inteira** (resolve o requisito "não só as últimas 500
samples"). Retenção: `cleanup_old(profile, keep_weeks=4)` apaga `.db`/`-wal`/`-shm`
das semanas além das 4 mais recentes. Migração de dados v1→SQLite: descartar
(CSV antigo vira backup); importar 977MB de CSV dá trabalho e pouco valor.

## Modelo de execução: repouso (todos, 60s) vs ativo (um, 1s, com timer)
- **REPOUSO (default):** TODOS os perfis testam a cada `interval_normal` (60s),
  continuamente — alimenta histórico/Prometheus de forma leve.
- **ATIVO:** no máximo **UM** perfil roda a cada `interval_active` (1s) por X minutos
  (default 10, **teto 120**, piso 1). Botão Start (com campo de minutos) + Stop.
  Ao expirar OU via Stop, volta ao repouso. **O estado ativo NÃO sobrevive a restart.**
- **Espalhar carga (jitter de agendamento):** no primeiro disparo de cada perfil em
  repouso, agende `now + random.uniform(0, interval_normal)` — senão todos os perfis
  disparam sincronizados e dão pico de CPU/rede. Efeito visível: o 1º sample de um
  perfil novo pode levar até 60s pra aparecer (não é bug).
- **Orchestrator loop:** tick a cada 0.5s; decide quem deve rodar (`now - last_round_ts
  >= interval`), expira o ativo (`now >= active_until`), grava cada rodada no SQLite.

## Endpoints (todos por perfil)
- `GET /profiles`, `GET/POST /profiles`, `DELETE /profiles/{name}` — CRUD (sem auth,
  como a v1; salvar recarrega as engines via `orch.reload_engines()`).
- `GET /control` / `POST /control/start` {profile,minutes} / `POST /control/stop`.
- `GET /status/{profile}` (snapshot tempo real), `GET /summary/{profile}` (semana
  inteira, **cache ~30s** — agregação sobre a semana pesa, e o summary não muda
  visivelmente a cada segundo; a tabela de cima segue tempo real via WS).
- `GET /history/{profile}/{host}/{port}?proto=tcp` (série pro gráfico).
- `WS /ws/{profile}` — snapshot + `control` status a cada 1s.

## Prometheus /stats por perfil
Renomear métricas para `fpdc_probe_*` com label `profile` (o usuário confirmou que
nada consome os nomes antigos `dns_tcp_*` — sempre pergunte antes de renomear se há
Grafana/alertas consumindo). Exporta TODOS os perfis de uma vez:
`fpdc_probe_rtt_ms{profile=...,host=...,port=...,proto=...}`, mais `avg_ms`,
`jitter_ms`, `p95_ms`, `uptime_pct`, `samples`, `status`, e `fpdc_probe_active{profile=...}`
(1 se em modo ativo). O `/stats` lê direto do storage (sem cache) → reflete o modo
ativo na hora, enquanto o `/summary` (cacheado 30s) pode atrasar — comportamento ok.

## UI (web_ui.py)
- Combobox de perfil no topo → troca dispara `connectWs()` + `refreshSummary()` (sem
  reload). WebSocket é por perfil: `ws://host/ws/<profile>`.
- Badge de modo (repouso/ATIVO) + campo minutos + Start/Stop + timer countdown.
- Tela "Configurar perfis" (modal): seletor + Novo/Excluir, nome, textarea de DNS,
  tabela de alvos editável (host/proto-dropdown/porta/serviço/remover), +Alvo, Salvar.
- Gráfico: reusa o pattern multi-série (latência/P95/jitter) + zoom do umbrella.
- Disciplina de wiring: listeners no `DOMContentLoaded` com guarda `if (el)` (a div do
  modal vem depois do `<script>` no HTML; sem a guarda dá `TypeError` que aborta o
  script inteiro e nenhuma tabela popula — mesmo sintoma do pitfall de WebSocket).

## Empacotamento/teste local antes do deploy
- `/tmp` no runtime do agente pode estar montado `noexec` → venv lá falha ao carregar
  `.so` nativos (pydantic_core: `failed to map segment from shared object`). Crie o
  venv de teste em `~/` (ex.: `~/fpdc-venv`) e rode a app de `~/fpdc-app/`.
- Teste cada módulo isolado (storage/profiles puro Python; engine com alvos locais
  `127.0.0.1:22`), depois suba a app inteira numa porta de teste (8099) em background,
  exercite via `curl` (criar perfil, start, status, summary, history, /stats) e
  valide a UI com `browser_navigate` em `localhost` (o browser alcança localhost, só
  não alcança os IPs on-prem/privados).

## Publicar a v2 no Git (pasta nova, v1 intacta)
Quando o usuário aprovar e pedir para versionar, crie uma **pasta nova** no repo
(ex.: `fpdc-connectivity-tester/`) — NÃO sobrescreva a pasta da v1 (`rsfn-probe-web`),
que fica como fallback. Layout versionado: `app/*.py`, `install.sh`, `uninstall.sh`,
`requirements.txt` (com `uvicorn[standard]` + `websockets` fixos!), `deploy/<svc>.service`
(capture o unit real gerado: `ssh host cat /etc/systemd/system/fpdc-tester.service`),
`README.md`, `.gitignore` (`data/`, `profiles/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.log`,
`__pycache__/`). Branch + PR (repo compartilhado), confira `git status --short` por nada
de runtime antes do commit.
