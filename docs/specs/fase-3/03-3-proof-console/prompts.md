# Fase 3 — Etapa 3.3: Prompts (Claude Code)

PROMPT 3.3.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-3-proof-console/spec.md` e siga como contrato.
2) Mapear:
   - como `/console/proof` foi implementado na Etapa 3.2
   - qual estrutura de resultado retorna `engine.proof.verify_bundle_offline()` (campos)
   - quais códigos de erro `PROOF_*` existem
3) Produzir:
   - `docs/specs/fase-3/03-3-proof-console/gaps.md` (gaps + plano mínimo)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.3.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Manter console estritamente read-only.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-3-proof-console/spec.md` e siga como contrato.
2) Melhorar a UX de prova no console:
   - detalhar checks e failures
   - adicionar export JSON (download)
   - linkar diretamente para contract_detail quando aplicável
3) Adicionar testes cobrindo PASS/FAIL e export.
4) Atualizar `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
