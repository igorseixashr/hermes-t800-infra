---
name: confluence-batch-sync
description: Sincronização particionada de árvores grandes do Confluence para a base de conhecimento local (~/wiki).
---

# Sincronização Confluence (Base de Conhecimento Local)

Pipeline ATIVO (verificado em produção): `confluence_hybrid_sync.py`, agendado via cron, grava Markdown em `~/wiki/`. **Não confundir com o pipeline legado "gbrain"** (removido; backup em `~/removal-backup-gbrain-20260910/`) que usava `/opt/hermes/confluence_sync/raw`, `~/kb-sync/confluence-files/` e índice PGLite/pgvector — esses caminhos NÃO existem mais. Qualquer script/skill que os referencie está obsoleto; tratar como histórico, não como estado real.

## Arquitetura Atual
- **Script:** `~/.hermes/hermes-agent/scripts/confluence_hybrid_sync.py` — extrai espaços FOUND e STIS, converte XHTML→Markdown com wikilinks, descreve imagens/diagramas via Gemini (cache SHA256), mantém delta sync incremental.
- **Saída:** `~/wiki/FOUND/`, `~/wiki/STIS/`, estado em `~/wiki/.sync_state.json`.
- **Credenciais:** `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_API_TOKEN` em `~/.hermes/.env` (o script lê esse arquivo diretamente na inicialização, não `config.yaml`).
- **Agendamento:** cron job `confluence-hybrid-daily-sync` (`15 3 * * *` — 03:15 BRT, `deliver: local`). Ver via `cronjob_manage(action='list')`. Executa 30 min antes de `graphrag-delta-sync` (`45 3 * * *`).
- **Índice vetorial (`~/wiki/.vector_index.db`, script `~/.hermes/hermes-agent/scripts/wiki_vector_index.py`):** existe mas está ÓRFÃO — nenhum cron job o dispara. Não assumir que está sincronizado com o conteúdo atual do wiki; comparar o `mtime` do `.db` com a última execução do sync antes de reportá-lo como funcional.

## Procedimento de Health Check
1. Confirmar o job agendado: `cronjob_manage(action='list')` → procurar `confluence-hybrid-daily-sync`, checar `last_status`/`last_run_at`.
2. Ler o log do último run (fonte de verdade para contagem por espaço): `~/.hermes/cron/output/<job_id>/*.md` — nome do arquivo é o timestamp do run, pegar o mais recente.
3. Contagem total de páginas (recursivo — FOUND/STIS são subdiretórios): `find ~/wiki -name "*.md" | wc -l`.
4. Atividade recente: `find ~/wiki -name "*.md" -mmin -10080 | wc -l` ou últimos modificados: `find ~/wiki -name "*.md" -printf '%T@ %p\n' | sort -n | tail -5`.
5. Processo ativo (só relevante durante uma corrida manual — o job normal roda e termina): `ps aux | grep '[c]onfluence_hybrid_sync'`.

## Pitfalls
- **Caminhos legados são uma trap.** `/opt/hermes/confluence_sync/raw`, `~/kb-sync/confluence-files/`, PGLite/pgvector pertencem ao pipeline "gbrain" removido. Encontrar essas referências em script/skill antigo não significa que estão ativas.
- **Não confundir o índice vetorial órfão com sync ativo.** A existência de `.vector_index.db` não implica atualização — checar mtime.
- **A fonte de verdade é o job cron + seu log, não a presença do script no disco.** Um script existir em `scripts/` não implica que roda automaticamente; confirmar sempre via `cronjob_manage(action='list')`.
