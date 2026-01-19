# Fase 2 — Etapa 2.2: Prompts (Claude Code)

PROMPT 2.2.1 (Diagnóstico + mapa de integração)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-2-ise-ircs-to-bundle/spec.md` e siga como contrato.
2) Leia como referência:
   - `docs/specs/fase-2/02-1-idl-mandates-autonomy/ircs-v1-schema.md`
   - `src/engine/idl_dsl/` (Etapa 2.1) e confirme o output real do IRCS v1
3) No código atual, mapeie:
   - como o ISE compila hoje (entrypoints e modelos internos)
   - quais contratos são emitidos por quais emitters
   - onde é o melhor ponto para plugar “IRCS v1 → compilação”
4) Proponha um “adapter mínimo” IRCS v1 → (modelo interno atual) reaproveitando emitters, sem duplicação.
5) Produza um mini checklist (passos de implementação) e riscos.

Saída esperada (nesta mesma pasta):
- `docs/specs/fase-2/02-2-ise-ircs-to-bundle/map.md` (mapa com arquivos/funções)
- `docs/specs/fase-2/02-2-ise-ircs-to-bundle/gaps.md` (gaps/riscos + decisão recomendada)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.2.2 (Implementação mínima: IRCS v1 → bundle)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-2-ise-ircs-to-bundle/spec.md` e siga como contrato.
2) Implementar o caminho canônico:
   - input: `ir.json` (IRCS v1)
   - output: diretório de bundle compatível com o loader
3) Regras:
   - Não quebrar o caminho legado (JSON-IDL ad-hoc).
   - Não criar um pipeline paralelo de emitters se for evitável; preferir adapter IRCS→modelo interno.
   - `bundle.manifest.json` deve seguir o ABI do loader (contracts[] com `{file, sha256, required}`).
   - `contract_ledger.json` deve ser gerado pelo ISE com hashes coerentes e referenciar `source_idl_sha256`.
4) Adicionar uma CLI mínima (se não existir um entrypoint adequado):
   - `PYTHONPATH=src python -m engine.ise compile-ircs path/to/ir.json -o out_bundle_dir`

Testes obrigatórios:
1) Gerar um IR do Finance a partir da DSL:
   - usar `src/engine/idl_dsl` e `examples/finance.idl` (ou fixture equivalente)
2) Compilar o IRCS v1 para um bundle “temp” (pasta temporária de testes)
3) Carregar o bundle via loader e garantir:
   - status ACTIVE (não SAFE_MODE)
   - fluxo E2E mínimo do Finance funciona com o bundle gerado (create + approval decide)
4) Verificar manifest e contract_ledger:
   - contratos required=true presentes
   - sha256 correto e no formato esperado

Documentação:
- Atualizar `docs/specs/fase-2/02-2-ise-ircs-to-bundle/map.md` marcando o que foi implementado.
- Atualizar `docs/specs/fase-2/02-2-ise-ircs-to-bundle/gaps.md` removendo gaps fechados.

Restrições:
- Mudanças mínimas e com testes.
[[CLAUDE_CODE_END]]

