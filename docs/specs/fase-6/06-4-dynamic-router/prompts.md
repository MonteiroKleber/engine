# Etapa 6.4 — Prompts (Claude Code)

PROMPT 6.4.1 (Diagnóstico: onde plugar router dinâmico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-4-dynamic-router/spec.md` e siga como contrato.
2) Mapeie:
   - onde o FastAPI app é criado e routers são incluídos
   - onde `load_bundle()` ocorre no lifespan
   - onde `OperationRegistry` fica disponível após 6.1
3) Proponha o ponto mínimo de integração para registrar rotas dinâmicas sem quebrar rotas existentes.
4) Identifique riscos de colisão de rota e como tratá-los no modo `idl` vs `both`.

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-4-dynamic-router/map.md`
- `docs/specs/fase-6/06-4-dynamic-router/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.4.2 (Implementação mínima: ENGINE_API_MODE + add_api_route)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-4-dynamic-router/spec.md`.
2) Mudança mínima. Não remover rotas legacy.
3) Decisão desta etapa (para eliminar ambiguidade de dept):
   - O router dinâmico deve suportar **os dois formatos**:
     - **single-dept**: usar o `path` do `OperationSpec` como está (ex.: `/finance/expenses`)
     - **multi-dept**: registrar também um path variante `"/d/{dept_id}" + path` (ex.: `/d/{dept_id}/finance/expenses`)
       e, no handler, usar o `dept_id` vindo do path param para resolver o `OperationSpec` correto no registry.
   - Não registrar rotas “por dept fixo” (ex.: `/d/finance/...` hardcoded). Sempre usar `{dept_id}`.

Tarefa:
1) Introduzir `ENGINE_API_MODE=legacy|idl|both` (default `legacy`).
2) Implementar registro de rotas dinâmicas a partir do `OperationRegistry`:
   - registrar no startup (lifespan) após `load_bundle()`
   - usar `app.add_api_route(...)` para cada operação
   - registrar 1 ou 2 rotas por operação:
     - base: `path` (single-dept)
     - dept: `"/d/{dept_id}" + path` (multi-dept)
3) Implementar handler wrapper único para dispatch:
   - resolver `OperationSpec`
   - chamar dispatcher correto (6.2/6.3)
4) Tratar colisões:
   - em `idl`: falhar startup determinístico se colidir com rota existente
   - em `both`: não registrar rota idl colidente e registrar aviso determinístico
5) Testes (sem HTTP real):
   - usar `TestClient` para:
     - subir app em `ENGINE_API_MODE=idl` e chamar `POST /finance/expenses`
     - validar que retorna `pending_approval` e `approval_id`
     - chamar `POST /approvals/{id}/decide` e validar `COMMITTED`
   - testes multi-dept (mínimo):
     - com bundle multi, chamar `POST /d/finance/finance/expenses` (ou equivalente do contrato) e validar resolução do dept_id
   - teste de colisão (modo idl falha / modo both ignora)
6) Atualizar docs:
   - `spec.md` status IMPLEMENTADO
   - `map.md` e `gaps.md`

Restrições:
- Não mexer na semântica dos gates.
- Não reimplementar approvals/workflow; usar dispatcher.
[[CLAUDE_CODE_END]]
