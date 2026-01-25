# Prompts — Expansão 05 (Hardening + Cutover Bazari)

## PROMPT 05.1 (Diagnóstico: telemetria + console status + runbook)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/expansao/05-hardening-cutover-bazari/spec.md` e siga como contrato.
2) Mapear com evidências (paths + símbolos) o que já existe hoje no engine para:
   - logging/request_id (middlewares)
   - ledger append-only por instituição
   - páginas do console (Status) e como injetar um “card” read-only
3) Propor o patch mínimo para:
   - registrar “IDL endpoint usage” somente quando a request for atendida por rota IDL
   - persistir por instituição (ex.: `<institution_root>/idl_telemetry.jsonl`)
   - agregar por endpoint_sig e “last_seen”

Saída esperada:
- `docs/specs/expansao/05-hardening-cutover-bazari/map.md`
- `docs/specs/expansao/05-hardening-cutover-bazari/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

---

## PROMPT 05.2 (Implementação mínima: telemetria determinística de uso IDL + console read-only)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/expansao/05-hardening-cutover-bazari/spec.md`.
2) Mudança mínima: não redesenhar dispatcher/router/auth.
3) Regressão proibida: `tests/test_finance_idl_mode_e2e.py` continua PASSANDO.
4) **Proibido deletar qualquer coisa** fora da allowlist (inclui arquivos untracked). Se precisar “limpar”, faça via `git restore` em arquivos tracked e pare.

Allowlist de patch (somente estes arquivos podem mudar/criar; qualquer outro é FAIL):
- `src/engine/core/idl_telemetry.py` (novo)
- `src/engine/core/idl_router.py` (1 hook mínimo para registrar quando a rota IDL realmente atendeu)
- `src/engine/console/routes.py` (expor agregados no Status)
- `src/engine/console/templates/status.html` (renderizar seção read-only)
- `tests/test_bazari_idl_telemetry_e2e.py` (novo)
- `docs/specs/expansao/05-hardening-cutover-bazari/spec.md` (marcar ✅ IMPLEMENTADO + evidências)

Objetivo:
- Em `ENGINE_API_MODE=idl`, registrar telemetria **somente** quando o request foi atendido por rota IDL.
- Em `ENGINE_API_MODE=legacy`, não registrar nada.
- Persistência: JSONL append-only por instituição (não usar DB).
- Console: seção “IDL Telemetry” na página Status mostrando:
  - contagem por endpoint_sig
  - último uso

Regras (hard):
A) Telemetria só pode ser ativada em `ENGINE_API_MODE=idl|both` (nunca em `legacy`).
B) Sem endpoints novos mutáveis.
C) Não registrar tokens/segredos no arquivo (PII mínimo: actor_id + endpoint_sig + timestamp).

Tarefas:
1) Implementar `src/engine/core/idl_telemetry.py`:
   - `record_idl_invocation(institution_id, endpoint_sig, method, path, actor_id, dept_id=None)`
   - `get_idl_telemetry_status(institution_id)` (agrega contagem + last_seen)
2) Hook no IDL router:
   - após dispatch bem-sucedido, chamar `record_idl_invocation(...)`.
3) Console:
   - Status mostra agregados (read-only).
4) Testes:
   - criar `tests/test_bazari_idl_telemetry_e2e.py` que:
     - sobe app em STRICT/IDL com um bundle Bazari Phase1 gerado no teste (mesmo padrão da Expansão 04)
     - chama 2 endpoints Bazari (ex.: `POST /reports`, `GET /moderation/actions`)
     - valida que o arquivo JSONL existe no institution_root e que o status agrega corretamente.
   - garantir que `tests/test_finance_idl_mode_e2e.py` continua passando.
5) Atualizar spec e marcar ✅ IMPLEMENTADO somente após hard gates.

Hard gates (colar saída literal no resumo final):
1) `PYTHONPATH=src python3 -m pytest tests/test_bazari_idl_telemetry_e2e.py -v`
2) `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) Anti-scope-creep (allowlist estrita):
   - `git diff --name-only` deve listar SOMENTE os arquivos acima.
4) Patch limpo (sem tmp/var):
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`
[[CLAUDE_CODE_END]]

