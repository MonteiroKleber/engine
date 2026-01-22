# Fase 4 — Etapa 4.6: Prompts (Claude Code)

PROMPT 4.6.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-6-agent-ops/spec.md` e siga como contrato.
2) Mapear no código:
   - onde `actor_id` aparece em eventos de ledger hoje (campos e payloads)
   - quais eventos representam negações (RBAC_DENIED, POLICY_DENIED, MANDATE_DENIED, AUTONOMY_INSUFFICIENT, etc.)
   - como o console já resolve `institution_id`/`dept_id` e faz auth
3) Propor o read model mínimo (sem DB):
   - funções para listar “últimos N eventos” por actor_id
   - funções para filtrar “denied attempts” por gate/código
   - um registry simples de agentes (append-only) e onde armazenar
4) Produzir:
   - `docs/specs/fase-4/04-6-agent-ops/api.md` (rotas console + read model)
   - `docs/specs/fase-4/04-6-agent-ops/gaps.md` (gaps + plano mínimo)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.6.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Console continua “security-first”: somente `GET` para Agent Ops (read-only).

Você está no repositório `/home/bazari/engine`.

Contrato (obrigatório):
1) Siga `docs/specs/fase-4/04-6-agent-ops/spec.md`.
2) Use `docs/specs/fase-4/04-6-agent-ops/api.md` como autoridade de rotas + read model.
3) Use `docs/specs/fase-4/04-6-agent-ops/gaps.md` como checklist de entrega (fechar/aceitar).

Nota de nomenclatura (evitar ambiguidade):
- O identificador canônico para query do ledger é `actor_id`.
- Se existir “agent registry”, ele deve referenciar `actor_id` (pode ter `display_name`, `roles`, `scopes`), mas a chave de lookup continua sendo `actor_id`.

Tarefa:
1) Leia `docs/specs/fase-4/04-6-agent-ops/spec.md` e siga como contrato.
2) Implementar:
   - read model simples em Python (sem DB) para query do ledger por actor_id e por denied attempts
   - UI no console com páginas:
     - `GET /console/agents`
     - `GET /console/agents/{actor_id}`
     - `GET /console/denied`
3) Definir “denied attempts” de forma determinística (sem heurística):
   - somente eventos em que a decisão foi negativa (ex.: `payload.allowed == false`, ou código/flag equivalente no payload).
   - não inferir por texto; usar campos estruturados.
4) Garantir isolamento por `(institution_id, dept_id)` e anti-inference (404 quando aplicável).
5) Adicionar testes cobrindo:
   - auth
   - render das páginas
   - filtros (denied)
   - isolamento (2 instituições × 2 depts)
6) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
