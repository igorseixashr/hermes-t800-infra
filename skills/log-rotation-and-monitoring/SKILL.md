---
name: log-rotation-and-monitoring
description: Gerencia rotacionamento de logs por data e visualização gráfica via Chart.js.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [log, monitoramento, devops, chartjs, rotacionamento]
    category: devops
---

# Log Rotation and Monitoring Skill

This skill governs the systematic logging and monitoring of applications on Linux servers, specifically focusing on path-based log rotation and the integration of live monitoring components with web-based visualizations.

## Procedure
1.  **Rotacionamento Semanal**: Implementar diretórios baseados na data atual (ANO/MES/semana). Use a função `get_log_path()` que calcula o caminho dinâmico para garantir que arquivos de log cresçam dentro de hierarquias gerenciáveis.
    ```python
    def get_log_path(log_dir: Path) -> Path:
        now = datetime.now()
        week = (now.day - 1) // 7 + 1
        target_dir = log_dir / str(now.year) / f"{now.month:02d}" / f"week_{week}"
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "results.csv"
    ```
2.  **Monitoramento Web**: Para prover gráficos sem fechar a interface, utilizar:
    - **Back-end**: Endpoint `/history/{host}/{port}` para extrair dados específicos de um arquivo de log ativo. Se as células do CSV carregam várias métricas (`L 17.1 | J 1.2 | P95 20.0`), extraia TODAS com regex separados (`L\s+([\d.]+)`, `J\s+([\d.]+)`, `P95\s+([\d.]+)`) e devolva `{"timestamp","rtt","jitter","p95","raw"}` por ponto — assim o front-end pode plotar múltiplas séries sem mudar o backend depois.
    - **Front-end**: CDN `Chart.js` para renderizar visualizações (tipo `line`) em elementos `<canvas>`.

### Gráfico multi-série + zoom por seleção (Chart.js)
Pattern validado para enriquecer o gráfico de latência com P95, jitter e zoom interativo:
- **Múltiplos datasets no mesmo eixo de ms**: latência (linha sólida), P95 (linha tracejada `borderDash: [6,4]`), jitter (linha sólida fina). Use `scales: { y: { beginAtZero: true } }` — assim o jitter fica rente ao zero e só "salta" visualmente quando há problema (comportamento desejado de detector). Cada dataset com `spanGaps: true, pointRadius: 0` para lidar com buracos (NOK/timeout) e não poluir.
- **Zoom drag-to-select**: precisa de DOIS scripts CDN além do Chart.js, na ordem: `hammerjs@2.0.8` e depois `chartjs-plugin-zoom@2.0.1`. Config: `plugins.zoom = { pan:{enabled:true,mode:"x",modifierKey:"shift"}, zoom:{ drag:{enabled:true,backgroundColor:"rgba(...)"}, mode:"x" } }`. Arrastar o mouse seleciona o período; Shift+arrastar faz pan.
- **Botão "Resetar zoom"**: adicione `<button id="chartResetZoomBtn">` no modal e ligue no `_wireModal()` (com guarda `if (rb)`): `rb.addEventListener("click", () => { if (chartInstance && chartInstance.resetZoom) chartInstance.resetZoom(); })`. `resetZoom()` é método da instância do Chart, fornecido pelo plugin.
- Mantenha a disciplina de transfer: edite local → `py_compile` → base64+MD5 → backup timestampado → deploy → restart via systemd. Valide na homologação primeiro, depois replique nos demais hosts (on-prem + AWS via SSM).
3.  **Deploy e Troubleshooting**:
    - **Antes de reiniciar, descubra COMO o serviço roda.** Quase sempre é systemd (`uvicorn monitor_web:app`). Rode `ss -tulnp | grep :<porta>` → `systemctl status <pid>`. Se for systemd-managed, `fuser -k <porta>/tcp` é INÚTIL — o systemd respawna na hora (às vezes lendo o arquivo no meio da edição → comportamento errático). Use `systemctl restart <service>`. (Detalhe completo no umbrella `service-daemon-ops`, Regra 0.)
    - **NUNCA edite o arquivo remoto via `sed`/`python -c` com o JS embutido.** O escaping de aspas e de `${...}` do template literal corrompe o arquivo silenciosamente (foi a causa de várias rodadas de retrabalho neste tipo de tarefa). Em vez disso: reconstrua o arquivo localmente, valide com `python3 -m py_compile`, transfira via **base64 com verificação de MD5**, recompile no servidor, e só então sobrescreva:
      ```bash
      # local: gerar b64 e md5
      base64 arquivo.py > arquivo.b64   # comparar md5sum dos dois lados
      # servidor:
      base64 -d arquivo.b64 > /tmp/arquivo.py
      md5sum /tmp/arquivo.py            # deve bater com o local
      python3 -m py_compile /tmp/arquivo.py && cp /tmp/arquivo.py /opt/.../arquivo.py
      systemctl restart <service>
      ```
    - **Injeção de ícone/handler no front-end: use `addEventListener`, não `onclick` com string interpolada.** Construa o `<td>`/`<span>` via DOM e anexe o handler com `icon.addEventListener("click", () => showChart(host, port))`. Strings com `onclick="showChart('${t.host}', ${t.port})"` quebram repetidamente no pipeline de patch.
    - **Comando travando/expirando no gate de aprovação → quebre a cadeia em comandos isolados.** Comandos compostos (`scp && ssh ... && systemctl restart`) que contêm uma operação flagrada (restart de serviço, write em path de sistema) podem ficar presos no gate de aprovação e expirar (`BLOCKED: Command timed out without user response`). NÃO reenvie o mesmo comando composto nem tente contornar — peça o OK ao usuário e então rode **um passo por vez** (gera b64 → scp → decode+md5+py_compile → backup+cp → restart), cada um aprovável individualmente. Efeito colateral: se um passo intermediário foi bloqueado, artefatos como o `.b64` podem não existir ainda — recrie-os antes de seguir.

## Publicar a app no Git (fim de ciclo)
Quando a app server-side estiver validada e o usuário pedir para subir num repo (ex.: org compartilhada `corp-payments/<repo>`):
1. **Confira acesso e branch default** antes: `gh repo view <org>/<repo> --json defaultBranchRef,viewerPermission`. Repo compartilhado → use **branch + Pull Request**, nunca push direto na `main`.
2. **Exclua os artefatos de runtime** do commit — eles são gigantes e voláteis. Crie um `.gitignore` cobrindo `results.csv`, `logs/`, `*.bak*`, `*.old`, `__pycache__/`, `*.log`. Depois de `git add`, **confirme** que nada indevido entrou: `git status --short | grep -iE "pycache|results.csv|logs/"` deve voltar vazio. (O `results.csv` de produção pode ter centenas de MB.)
3. **Garanta que o arquivo commitado == o de produção**: `md5sum` do arquivo local que você versiona vs. `ssh <host> md5sum /opt/.../monitor_web.py`. Devem bater. Versione a cópia exata, não uma reconstrução de memória.
4. **Empacote o deploy junto**: `requirements.txt` (de `pip freeze | grep -iE "fastapi|uvicorn|dnspython"`), o unit systemd em `deploy/`, `README.md`, e versões `.sample` dos arquivos de config (`dns.txt.sample`, `targets.txt.sample`, `config.json.sample`) para não vazar config viva.
5. Commit + `git push -u origin <branch>` + `gh pr create --base main`. Não faça merge sem o usuário pedir.

## Instalador automatizado (install.sh / uninstall.sh)
Quando o usuário pedir um instalador que "instala módulos, copia arquivos e cria o systemd service", entregue um `install.sh` **idempotente** versionado junto da app. Padrão validado:
1. `set -euo pipefail` + `require_root` (checa `EUID`). Use `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` para achar os artefatos.
2. **Deps de sistema**: detecte o gerenciador (`apt-get`/`dnf`/`yum`) e instale `python3 python3-venv python3-pip` + `ping` (`iputils-ping` no apt, `iputils` no dnf/yum).
3. **Usuário de serviço**: crie grupo/usuário system (`useradd --system --no-create-home --shell /usr/sbin/nologin`, com fallback `/sbin/nologin`).
4. **Copie a app** para `/opt/...`; **NUNCA sobrescreva config viva** (`config.json`, `dns.txt`, `targets.txt`) — copie só se ausente, usando o `.sample` como fallback (`copy_if_absent`).
5. **Venv isolado** em `/opt/.../venv` (mais limpo que python global): `python3 -m venv`, `pip install -r requirements.txt`, `chown` recursivo p/ o usuário de serviço. O unit systemd aponta `ExecStart=/opt/.../venv/bin/python -m uvicorn ...`.
6. **Gere o unit** com heredoc, `systemctl daemon-reload && enable && restart`.
7. **post_check**: `systemctl is-active --quiet` + `curl -o /dev/null -w '%{http_code}'` esperando 200.
8. Inclua `uninstall.sh` (`stop`/`disable`/`rm` unit + `daemon-reload`; flag `--purge` remove `/opt/...`).
9. **Valide de verdade**: `bash -n` local, depois rode no servidor de homologação e confirme que o serviço migrou pro venv e responde 200 antes de versionar. Migrar pro venv via instalador é efeito colateral desejável (deixa o deploy reprodutível).

## Deploy num servidor de produção que JÁ roda a app (upgrade in-place)
Quando o mesmo serviço já existe num segundo host (produção) com código mais antigo e o usuário pede o deploy preservando a config local daquele host:
1. **Mapeie o estado atual ANTES de tocar em nada**: `ssh <host>` → `ls -la /opt/probe_web` (versão/tamanho do código), `systemctl is-active/is-enabled <service>`, `ss -tulnp | grep :<porta>`, e capture os arquivos a preservar (`dns.txt`, `targets.txt`, `config.json`). Cada host tem config própria (ex.: targets RSFN ≠ targets de homologação).
2. **Pré-valide o formato da config de produção contra o parser NOVO antes do deploy.** Targets de produção podem usar variações de formato (ex.: `host,port,dns_hint` com 3 campos). Extraia a lógica de `load_targets` e rode contra o `targets.txt` real do host num sandbox — confirme que todos os alvos parseiam e que não há regressão (ex.: DNS porta 53 continua TCP). Não descubra incompatibilidade depois de derrubar produção.
3. **Backup timestampado obrigatório**: `mkdir /opt/probe_web/backup-pre-deploy-$(date +%Y%m%d-%H%M%S)` e copie pra lá o código antigo, os 3 configs e o unit systemd (`sudo cp /etc/systemd/system/<service>.service ...`). É o rollback imediato.
4. **Transfira via base64+MD5** (mesma disciplina da seção de troubleshooting) para staging em `/tmp`, e rode o **mesmo `install.sh` idempotente** — ele já faz `copy_if_absent`, então **preserva** `dns.txt`/`targets.txt`/`config.json` existentes e atualiza só o `monitor_web.py`.
5. **Validação pós-deploy específica de produção**: confirme `md5sum` do código == o versionado; `cat dns.txt`/`targets.txt` == os originais (preservados); unit aponta pro venv; `/status` carrega o nº esperado de targets com status OK; DNS resolvendo hostnames reais; `/history` retornando pontos; rotação `logs/<ANO>/<MES>/week_N/` criada.
6. **Não delete o `results.csv` antigo gigante sem o usuário pedir** — só deixe de usá-lo (a nova estrutura `logs/` assume). Ofereça arquivar/remover como passo separado.

## Deploy em instâncias AWS sem SSH (via SSM send-command)
Quando o host está na AWS e você NÃO tem SSH, mas tem AWS CLI com SSM (Session Manager), dá pra fazer o deploy inteiro por `aws ssm send-command` — executa shell como root sem shell interativo.
1. **Identidade e perfis**: `aws sts get-caller-identity` mostra conta/role atual. As instâncias-alvo costumam estar em **outras contas** — procure perfis SSO já configurados em `~/.aws/config` (`aws configure list-profiles | grep -i <termo>`; cheque `sso_account_id`/`sso_role_name`). Valide com `aws sts get-caller-identity --profile <perfil>`. Use `--profile <perfil> --region <região>` em todos os comandos.
2. **Descoberta de instâncias**: `aws ssm describe-instance-information --profile <p> --region <r>` lista as gerenciadas (Online). O ID que o usuário passou pode estar na conta/região errada — **varra todas as instâncias da conta certa** rodando um `send-command` de descoberta (`test -d /opt/probe_web && echo PRESENT; md5sum ...; systemctl is-active <svc>; ss -tulnp | grep :8000`) e ache a que realmente roda o probe. A app pode estar numa instância e região diferentes do que foi informado (ex.: alvo dito "us-east-1" estava em `sa-east-1`).
3. **Passar comandos sem brigar com aspas**: NUNCA monte `--parameters commands='...'` com aspas no shell — o parser do CLI quebra (`Expected: ',', received: '"'`). Em vez disso, escreva um JSON `{"commands":["<script>"]}` com `json.dump` e passe `--parameters file:///tmp/params.json`. Isso escapa aspas/`$()`/pipes corretamente.
4. **Transferir arquivos sem scp**: empacote os artefatos (`tar czf pkg.tgz monitor_web.py install.sh requirements.txt *.sample`), gere base64 (`base64 -w0`), e embuta o b64 num heredoc dentro do próprio script de deploy (`cat > pkg.b64 <<'B64EOF' ... B64EOF; base64 -d pkg.b64 > pkg.tgz; tar xzf ...`). ~20KB de b64 cabe folgado no limite do `send-command`. O script de deploy faz backup timestampado, extrai, roda o `install.sh` (que preserva config viva) e limpa o staging.
5. **Disparar em paralelo, coletar depois**: `send-command` é assíncrono — guarde o `CommandId` (`--query "Command.CommandId" --output text`), `sleep` (deploys com pip levam ~30-60s), e colha com `aws ssm get-command-invocation --command-id <id> --instance-id <id> --query "{Status:Status,Out:StandardOutputContent,Err:StandardErrorContent}"`. Para vários hosts de uma vez, `list-command-invocations --details`. Pode disparar nas N contas/regiões em paralelo (cada uma com seu `--profile`).
6. **Validação idêntica à de SSH**: md5 do código == versionado, configs preservados, unit no venv, `/status` com nº de targets esperado, `/ws` aceito (lib de WebSocket presente!), `logs/<ANO>/<MES>/week_N/` criada.
7. **Token SSO expira entre sessões.** Se um `aws ssm ...` retornar `Error when retrieving token from sso: Token has expired and refresh failed`, o login SSO precisa ser renovado — e isso é **interativo (OAuth no browser)**, o agente NÃO consegue completar sozinho. Peça ao usuário rodar `aws sso login --sso-session <nome>` (descubra o nome com `grep "sso-session" ~/.aws/config`; renova todos os perfis daquela sessão de uma vez). Atenção: `aws sso login` sem `--profile`/`--sso-session` pega o profile default (que pode não ter config SSO → erro `Missing the following required SSO configuration values`). Depois confirme com `aws sts get-caller-identity --profile <p> --query Account --output text` (deve voltar o nº da conta sem erro) e siga.
8. **Verifique acesso à CDN antes de deployar features que dependem de novos scripts externos.** Datasets multi-série não precisam, mas zoom (`hammerjs` + `chartjs-plugin-zoom`) sim. Teste em cada host (`curl -s -o /dev/null -w "%{http_code}" --max-time 8 https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@<ver>`; via SSM nas AWS) — todas precisam responder 200, senão o gráfico carrega sem o recurso novo.

## Evolução para multi-perfil (v2)
Quando o usuário pedir uma "nova versão" do probe com **perfis de teste** (conjuntos
isolados de targets/DNS), tela de configuração na UI, controle **start/stop com
temporizador** (repouso 60s para todos × ativo 1s para um perfil por vez), banco por
perfil e `/stats` Prometheus por perfil — o desenho completo e validado está em
`references/multi-profile-v2-architecture.md` (modularização, modelo JSON de perfil,
migração automática da v1, SQLite-por-perfil com retenção, Orchestrator repouso/ativo
com jitter de agendamento, endpoints por perfil, deploy lado-a-lado em porta separada).
Pontos-chave: **SQLite, nunca "pglite"** (pglite é JS/WASM, não serve backend Python);
suba a v2 **lado a lado** com a v1 (serviço/porta/dir próprios), não in-place; o estado
"ativo" não sobrevive a restart. A referência também cobre o **cutover/promoção** (v2
assumindo a porta 8000 e aposentando a v1: backup → stop+disable v1 → flip `FPDC_PORT`
no unit via sed → restart → validar; ou instalar direto com `FPDC_PORT=8000 bash install.sh`)
e o **versionamento da v2 em pasta nova** no Git sem tocar na pasta da v1.

## Pitfalls
- **Tabela vazia ("os números não aparecem") em venv limpo = falta a lib de WebSocket.** A tabela popula via WebSocket (`/ws`); `uvicorn` puro NÃO traz suporte a WS. Num venv recém-criado pelo `install.sh`, `/ws` retorna **404** com `WARNING: No supported WebSocket library detected` no journal → a tabela nunca recebe dados. Passa despercebido quando o python global já tinha a lib. Fix de raiz no `requirements.txt`: use `uvicorn[standard]==<ver>` **e** fixe `websockets==<ver>` explicitamente. Fix imediato num host já instalado: `/opt/.../venv/bin/python -m pip install websockets && systemctl restart <service>`. Diagnóstico rápido: `journalctl -u <service> -n 15 | grep -i websocket` e teste real com um cliente `websockets.connect("ws://localhost:8000/ws")` que dá `recv()`. Antes de culpar o front-end de novo, cheque o `/ws` no servidor.
- **Emoji com surrogate pairs quebra o encode UTF-8 do Python.** Escrever `icon.textContent = "\uD83D\uDCC8"` (📈) dentro de uma HTML string Python causa `UnicodeEncodeError: surrogates not allowed` → endpoint `/` retorna HTTP 500. Use `String.fromCodePoint(0x1F4C8)` (ASCII puro no arquivo, emoji montado em runtime) ou cole o caractere literal real.
- **Header de CSV "largo" escrito vazio.** Se o CSV foi inicializado antes dos targets carregarem, o header sai só com `timestamp,dns` (sem as colunas dos alvos) e o `DictReader` do endpoint `/history` não acha a coluna → retorna 0 pontos mesmo com dados nas linhas. Fix: rotacione o header na escrita (recrie o header se o arquivo mudou de semana OU está vazio), e se o usuário não precisa dos dados, basta `rm` o CSV da semana atual — a app regenera com o header completo.
- **Cache de Browser**: Após alterações no front-end, o browser pode manter versões antigas dos scripts. Sempre peça ao usuário um hard-reload (Ctrl+F5).
- **Injeção de JS**: Ao injetar lógica dinâmica em `renderTable`, certifique-se de que o seletor `tbody.appendChild(tr)` não está sendo duplicado por patches repetidos.
- **Permissões de Arquivo**: Certifique-se de que o usuário da aplicação tem permissão de escrita no diretório `/opt/probe_web/logs/` e nos subdiretórios criados dinamicamente.

## Verification
- Verifique se a estrutura de pastas `/opt/probe_web/logs/<ANO>/<MES>/week_<N>/` foi criada.
- Teste o endpoint `/status` para garantir que o mecanismo de monitoramento está injetando dados.
- Verifique o log no navegador (F12) caso o gráfico não carregue, para descartar erros de sintaxe no JavaScript injetado.
- **O browser do agente NÃO alcança IPs on-prem/privados** (ele tem SSH/AWS-CLI, mas não rota de rede direta pro `http://10.x.x.x:8000/`). Quando `browser_navigate` der timeout, NÃO conclua que a app está quebrada — valide pelo lado servidor: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/` (via SSH/SSM), e confirme o front-end servido com greps no HTML (`curl -s http://localhost:8000/ | grep -oE '"(P95 \(ms\)|Jitter \(ms\))"'`, `grep -c chartjs-plugin-zoom`, `grep -c chartResetZoomBtn`) + um cliente WS real. A confirmação VISUAL final fica com o usuário (peça o Ctrl+F5).
