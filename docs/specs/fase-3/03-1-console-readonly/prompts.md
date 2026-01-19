# Fase 3 — Etapa 3.1: Prompts (Claude Code)

PROMPT 3.1.1 (Diagnóstico + decisão de stack)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-1-console-readonly/spec.md` e siga como contrato.
2) Descubra o que já existe no repo para UI/console:
   - existe frontend (React/Vite/Next) ou não?
   - existe API admin/read-only suficiente ou não?
3) Proponha a opção mínima para o console:
   - Opção A: UI servida pelo próprio FastAPI (Jinja/HTMX ou static)
   - Opção B: React/Vite separado consumindo APIs
4) Liste os endpoints read-only já existentes e os que faltam.
5) Produza:
   - `docs/specs/fase-3/03-1-console-readonly/stack.md` (decisão A/B + justificativa)
   - `docs/specs/fase-3/03-1-console-readonly/api.md` (lista de endpoints read-only)
   - `docs/specs/fase-3/03-1-console-readonly/gaps.md` (gaps + plano mínimo)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.1.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Stack do console: **Opção A** (FastAPI + Jinja2 + HTMX).
- Console mínimo em modo **read-only**.

Regras (reforços obrigatórios):
- Não expor ações mutáveis no console.
- Não chamar endpoints mutáveis (`POST/PUT/PATCH/DELETE`) a partir do console.
- Se existir necessidade de auth, usar o mecanismo já existente (ex.: token/admin), sem criar IAM novo nesta etapa.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-1-console-readonly/spec.md` e siga como contrato.
2) Implementar o console read-only usando FastAPI + templates Jinja2 e interações mínimas (HTMX se útil, sem exagero).
3) Se faltarem APIs read-only, implemente os endpoints mínimos necessários.
4) Adicionar testes mínimos para os endpoints criados.
5) Atualizar `docs/specs/fase-3/03-1-console-readonly/stack.md`, `docs/specs/fase-3/03-1-console-readonly/api.md`, `docs/specs/fase-3/03-1-console-readonly/gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
