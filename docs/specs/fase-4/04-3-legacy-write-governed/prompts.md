# Fase 4 — Etapa 4.3: Prompts (Claude Code)

PROMPT 4.3.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-3-legacy-write-governed/spec.md` e siga como contrato.
2) Mapear no código:
   - como o Legacy Bridge read-only está estruturado hoje
   - quais gates estão disponíveis no runtime (mandates/autonomy/approvals/sod/policies)
   - como gerar eventos no ledger em handlers
3) Propor o design mínimo do Outbox connector:
   - onde gravar
   - formato do arquivo (determinístico)
   - naming (case_id / request_id)
4) Produzir:
   - `docs/specs/fase-4/04-3-legacy-write-governed/gaps.md`
   - `docs/specs/fase-4/04-3-legacy-write-governed/api.md` (endpoints e payload)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.3.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Implementar 1 ação write via Outbox connector (file), sem aplicar direto no legado.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-3-legacy-write-governed/spec.md` e siga como contrato.
2) Implementar:
   - Outbox connector (write) com isolamento por institution/dept
   - 1 endpoint governado para enfileirar ação (ex.: `POST /bridge/write/increase_limit`)
   - eventos no ledger
3) Garantir gates:
   - mandates/autonomy/policies + approvals/SoD (se configurado) bloqueiam corretamente
4) Adicionar testes cobrindo allow/deny, isolamento e criação do outbox file.
5) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
