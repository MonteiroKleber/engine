# Fase 2 — Etapa 2.5: Prompts (Claude Code)

PROMPT 2.5.1 (Diagnóstico + design mínimo)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-5-multi-dept-parity/spec.md` e siga como contrato.
2) Mapeie no código atual:
   - como o runtime seleciona dept (path/rotas)
   - como bundles são carregados por dept
   - como state_store e ledger são namespaced por dept+institution
3) Identifique gaps para rodar 2 depts em paralelo de forma limpa.
4) Produza:
   - `docs/specs/fase-2/02-5-multi-dept-parity/flow.md` (fluxo e diagrama)
   - `docs/specs/fase-2/02-5-multi-dept-parity/gaps.md` (gaps + decisões)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.5.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisões oficiais desta etapa (não discutir, apenas implementar):
- Segundo departamento do piloto: `support` com endpoint mínimo mutável `POST /support/tickets`.
- Multi-dept parity exige lookup **por dept** para: approvals, SoD e invariants (além de policies/mandates/autonomy).
- Bundles devem ser válidos (contratos required=true presentes); ausência → SAFE_MODE.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-5-multi-dept-parity/spec.md` e siga como contrato.
2) Implementar multi-dept parity:
   - criar 2º dept bundle (ex.: support-pilot)
   - garantir seleção correta do dept e isolamento de state/ledger
   - adicionar handlers/endpoints mínimos para o 2º dept (se necessário)
3) Adicionar testes E2E cobrindo:
   - finance vs support (mesma instituição)
   - matriz 2x2 (duas instituições x dois depts)

Regras:
- Sem permissividade por ausência de contract: bundle inválido → SAFE_MODE.
- Eventos críticos devem conter dept_id.

Documentação:
- Atualizar `flow.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
