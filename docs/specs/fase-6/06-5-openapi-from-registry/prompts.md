# Etapa 6.5 — Prompts (Claude Code)

PROMPT 6.5.1 (Diagnóstico: estado do OpenAPI vs registry)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-5-openapi-from-registry/spec.md` e siga como contrato.
2) Mapeie:
   - como o FastAPI gera `/openapi.json` hoje (incluindo rotas dinâmicas 6.4)
   - quais campos do `OperationSpec` estão disponíveis para gerar OpenAPI (method, path, operation_id, errors, idempotency)
   - quais headers/auth precisam aparecer dependendo de `ENGINE_AUTH_MODE` e config de instituição
3) Proponha a menor mudança possível para alinhar OpenAPI com o registry:
   - Opção A: gerar um OpenAPI “overlay” a partir do schema do FastAPI
   - Opção B: montar um OpenAPI mínimo do zero a partir do registry

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-5-openapi-from-registry/map.md`
- `docs/specs/fase-6/06-5-openapi-from-registry/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.5.2 (Implementação mínima: OpenAPI alinhado ao registry)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-5-openapi-from-registry/spec.md`.
2) Mudança mínima.
3) Decisão oficial (resultado do diagnóstico 6.5.1):
   - Implementar a **Opção A (overlay)**: partir do OpenAPI gerado pelo FastAPI e aplicar um overlay derivado do
     `OperationRegistry` (operationId, headers, responses, securitySchemes).
   - Não montar um OpenAPI “do zero” nesta etapa.

Tarefa:
1) Implementar overlay do OpenAPI gerado pelo FastAPI:
   - `operationId` deve ser **exatamente** `OperationSpec.operation_id` (sem prefixo, sem transformação).
   - `errors` do `OperationSpec` devem virar `responses` no OpenAPI (mínimo: incluir status codes listados em `errors` com descrição).
   - `Idempotency-Key` deve aparecer como header param quando `idempotency=required` (apenas documentação nesta etapa).
   - Headers e auth:
     - Sempre: documentar `X-Institution-Id` como header quando exigido pela instituição.
     - `ENGINE_AUTH_MODE=strict`: documentar `X-Actor-Token`.
     - `ENGINE_AUTH_MODE=dev`: documentar `X-Actor-Id` e `X-Actor-Roles`.
   - Tags:
     - mínimo aceitável: derivar tags do prefixo do path (ex.: `/finance/...` → `finance`).
   - Schemas:
     - manter genérico nesta etapa (não inventar tipagem completa); usar `additionalProperties: true` quando necessário.
2) Expor `/d/{dept_id}/openapi.json`:
   - endpoint read-only que retorna o OpenAPI filtrado para o dept selecionado (view do schema, não um schema novo).
   - deve validar `dept_id` com as mesmas regras do runtime (depts instalados/ativos) e retornar erro determinístico quando aplicável.
3) Adicionar testes:
   - `TestClient` chama `/openapi.json` e valida presença de paths/operationId
   - valida presença de parâmetros/header docs
   - valida `dept_id` path param em rotas multi
   - valida `/d/{dept_id}/openapi.json` retorna schema filtrado para o dept
4) Atualizar docs:
   - `spec.md` status IMPLEMENTADO
   - `map.md` e `gaps.md` com evidências.

Restrições:
- Não remover legacy OpenAPI (se existir).
- Não alterar semântica do router/dispatcher.
[[CLAUDE_CODE_END]]
