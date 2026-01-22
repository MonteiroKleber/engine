# Fase 4 — Etapa 4.7: Prompts (Claude Code)

PROMPT 4.7.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-7-prod-packaging/spec.md` e siga como contrato.
2) Mapear no repo:
   - como o runtime é iniciado hoje (dev/prod)
   - quais envs são obrigatórias (ex.: `ENGINE_CONSOLE_SESSION_SECRET`, tokens/admin, data root)
   - onde ficam data roots, bundles, releases, ledgers, traces
3) Propor o caminho mínimo de packaging:
   - Opção A: `docker-compose.yml` (um serviço)
   - Opção B: `systemd` unit + script
4) Produzir:
   - `docs/specs/fase-4/04-7-prod-packaging/runbook.md`
   - `docs/specs/fase-4/04-7-prod-packaging/checklist.md`
   - `docs/specs/fase-4/04-7-prod-packaging/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.7.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Implementar **Opção B (systemd + scripts)**, porque já existe e é o caminho mínimo para piloto.
- Docker fica explicitamente fora do escopo desta etapa.

Você está no repositório `/home/bazari/engine`.

Contrato (obrigatório):
1) Siga `docs/specs/fase-4/04-7-prod-packaging/spec.md`.
2) Use `docs/specs/fase-4/04-7-prod-packaging/runbook.md` e `docs/specs/fase-4/04-7-prod-packaging/checklist.md` como autoridade do que precisa funcionar.
3) Use `docs/specs/fase-4/04-7-prod-packaging/gaps.md` como checklist: feche o que for “ALTA” e marque o resto como “ACEITO” com justificativa.

Tarefa:
1) Fechar os gaps prioritários (ALTA) identificados no diagnóstico:
   - Atualizar `engine.env.example` (ou arquivo equivalente) para refletir as ENVs realmente necessárias em produção (inclui `ENGINE_CONSOLE_SESSION_SECRET` e `ENGINE_ISE_ADMIN_TOKEN`).
   - Implementar scripts de backup/restore do data root (mínimo seguro):
     - backup: compactar `ENGINE_DATA_ROOT` (ou root efetivo) com preservação de permissões
     - restore: restaurar para um diretório vazio e validar integridade mínima (sem “merge” silencioso)
2) Sincronizar preflight:
   - `ops/scripts/preflight.sh` (se existir) deve refletir as regras de `src/engine/core/preflight.py`, ou ser removido/descontinuado com nota no runbook.
3) Adicionar “smoke checks” operacionais (sem harness novo):
   - script simples (shell) que valida que o serviço responde (ex.: `GET /health` ou rota equivalente) e que `/console/login` está acessível.
4) Garantir que o runbook/checklist descrevem exatamente os comandos reais para:
   - instalar dependências / configurar env
   - iniciar/parar o serviço (systemd)
   - rodar preflight
   - executar backup/restore
5) Atualizar `docs/specs/fase-4/04-7-prod-packaging/gaps.md` com status final (RESOLVIDO/ACEITO) e evidências (paths/commands).

Saída esperada:
- Patch mínimo + docs (e scripts em `ops/` se aplicável).
[[CLAUDE_CODE_END]]
