# Etapa 6.2 — Prompts (Claude Code)

PROMPT 6.2.1 (Diagnóstico: como mapear CRUD do legacy → dispatcher)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-2-dispatcher-crud/spec.md` e siga como contrato.
2) Mapeie no código atual (com evidência):
   - como o state store é acessado (paths, helpers, formatos)
   - como o finance/support fazem create/read hoje (funções e passos)
   - quais gates são chamados e em qual ordem (RBAC/policy/mandates/autonomy)
   - quais códigos de erro determinísticos são usados em create/read
3) Proponha o patch mínimo para:
   - criar um dispatcher interno (`src/engine/core/dispatcher.py` ou equivalente)
   - reutilizar os gates existentes (não duplicar lógica)
   - persistir/ler entidades no state store no formato já existente

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-2-dispatcher-crud/map.md` (arquivos/funções + sequência)
- `docs/specs/fase-6/06-2-dispatcher-crud/gaps.md` (gaps/riscos e decisões para 6.2.2)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.2.2 (Implementação mínima: dispatcher create/read)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-2-dispatcher-crud/spec.md`.
2) Não implementar rotas dinâmicas nem mexer em `fastapi.add_api_route` nesta etapa.

Tarefa:
1) Criar o dispatcher interno para `create/read` reaproveitando:
   - RBAC
   - policy pre (se existir para o dept)
   - mandates/autonomy (endpoint_sig)
   - state store namespaced `(institution_id, dept_id)`
2) Integrar o dispatcher com `OperationRegistry`:
   - dispatcher recebe `OperationSpec` resolvida via `engine.core.operations`
3) Adicionar testes:
   - `finance-pilot`: `expense_create` via dispatcher (gera entity/id e ledger events esperados)
   - `finance-pilot`: `expense_get` via dispatcher (404 determinístico quando não existe)
   - isolamento (2 instituições × 2 depts), reaproveitando padrão de testes existente
4) Atualizar docs:
   - `docs/specs/fase-6/06-2-dispatcher-crud/spec.md` status IMPLEMENTADO
   - `map.md` e `gaps.md` com evidências.

Restrições:
- Não remover/alterar rotas legacy existentes.
- Não introduzir endpoint público novo.
- Mudanças mínimas e com testes.
[[CLAUDE_CODE_END]]

