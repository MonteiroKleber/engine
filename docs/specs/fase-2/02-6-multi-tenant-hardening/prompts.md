# Fase 2 — Etapa 2.6: Prompts (Claude Code)

PROMPT 2.6.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-6-multi-tenant-hardening/spec.md` e siga como contrato.
2) Liste todas as ENVs/configs que influenciam paths e isolamento, com evidência no código:
   - ledger path
   - state store dir
   - bundles/releases dirs
   - institutions registry dir
3) Identifique quais combinações podem quebrar isolamento por acidente (multi-tenant + path absoluto).
4) Produza:
   - `docs/specs/fase-2/02-6-multi-tenant-hardening/matrix.md`
   - `docs/specs/fase-2/02-6-multi-tenant-hardening/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.6.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa (MVP institucional):
- Em modo institucional/multi-tenant (quando `require_institution_header_for_runtime=true`):
  - `ENGINE_LEDGER_PATH` e `ENGINE_STATE_STORE_DIR` **não podem** ser paths absolutos.
  - Se forem absolutos, o runtime deve **falhar hard no startup/preflight** com erro determinístico (não “tolerar”, não “auto corrigir”).
  - Justificativa: um path absoluto bypassa o namespace e pode causar vazamento cross-tenant.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-6-multi-tenant-hardening/spec.md` e siga como contrato.
2) Implementar guardrails para misconfiguração:
   - quando multi-tenant estiver ativo, bloquear overrides perigosos (`ENGINE_LEDGER_PATH`, `ENGINE_STATE_STORE_DIR` absolutos)
   - adicionar preflight/health que falha determinístico (mensagem clara + código) ao detectar a misconfig
3) Adicionar testes:
   - multi-tenant ativo + override absoluto perigoso → falha determinística
   - modos permitidos (dev/single-tenant ou quando `require_institution_header_for_runtime=false`) seguem funcionando

Regras:
- Mudanças mínimas e com testes.
- Atualizar `matrix.md` e `gaps.md` com status final.
[[CLAUDE_CODE_END]]
