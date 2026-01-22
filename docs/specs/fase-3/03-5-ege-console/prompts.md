# Fase 3 — Etapa 3.5: Prompts (Claude Code)

PROMPT 3.5.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-5-ege-console/spec.md` e siga como contrato.
2) Mapear no código:
   - APIs existentes para proposals/pins/releases/traces
   - como o rollback governado foi implementado (Etapa 2.4)
   - como o console atual faz auth e redirects
3) Produzir:
   - `docs/specs/fase-3/03-5-ege-console/gaps.md` (gaps + plano mínimo)
   - `docs/specs/fase-3/03-5-ege-console/api.md` (read model do console)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.5.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Permitir apenas uma ação mutável: rollback governado (para pinned_release_id), com confirmação explícita.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-5-ege-console/spec.md` e siga como contrato.
2) Implementar rotas e templates do console EGE.
3) Implementar rollback via console chamando o mecanismo governado (sem atalhos).
4) Adicionar testes cobrindo:
   - auth
   - render
   - rollback bloqueado/permitido
5) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
