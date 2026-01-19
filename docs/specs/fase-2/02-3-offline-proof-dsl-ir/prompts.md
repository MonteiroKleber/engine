# Fase 2 — Etapa 2.3: Prompts (Claude Code)

PROMPT 2.3.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-3-offline-proof-dsl-ir/spec.md` e siga como contrato.
2) Mapeie o que já existe no código para verificação offline:
   - verificação de hashes do loader (ex.: `verify_hashes.py`)
   - schema real de `contract_ledger.json` emitido pelo ISE
   - qualquer utilitário existente de “proof verify”
3) Liste o menor conjunto de mudanças para implementar o verificador offline desta etapa.

Saída esperada:
- `docs/specs/fase-2/02-3-offline-proof-dsl-ir/proof.md` (procedimento + exemplos)
- `docs/specs/fase-2/02-3-offline-proof-dsl-ir/gaps.md` (gaps + decisões)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.3.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-3-offline-proof-dsl-ir/spec.md` e siga como contrato.
2) Implementar um verificador offline (CLI) para validar um diretório de bundle:
   - manifest schema + hashes dos contracts
   - `contract_ledger.json` consistência com o manifest
   - validação de `source_idl_sha256`

Regras (reforços obrigatórios):
- A CLI deve funcionar **sem iniciar runtime**:
  - não inicializar FastAPI app/server
  - não rodar pipeline/orchestrator
  - não depender de DB/ledger runtime
  - somente leitura de arquivos do bundle + hashing + validações
- Segurança de path:
  - não permitir `contracts[].file` com path absoluto, `..`, ou escape por symlink (anti path traversal)
  - ler somente arquivos dentro do diretório do bundle
- Cross-check completo:
  - validar `contract_ledger.json.manifest_hash == SHA256(bundle.manifest.json)`
  - validar que `contract_ledger.json.contracts[]` bate 1:1 com `bundle.manifest.json.contracts[]` (mesmos `file` e hashes), sem extras
- Hashing:
  - aceitar `SHA256:<hex>` ou `<hex>` como entrada
  - comparar sempre pelo `<hex>`
  - exigir `<hex>` com 64 chars (SHA256) para `manifest_hash`, hashes de contracts e `source_idl_sha256`
- Erros determinísticos:
  - definir códigos `PROOF_*` estáveis
  - CLI deve retornar `exit 0` no PASS e `exit 1` no FAIL
  - saída deve ser padronizada (ex.: JSON report) para CI/auditoria

Testes obrigatórios:
- PASS: bundle gerado por DSL→IRCS→ISE (Etapas 2.1/2.2) valida offline
- FAIL: alterar 1 byte de um contract → falha
- FAIL: manifest hash inválido
- FAIL: `contract_ledger.json` inconsistente com manifest
- FAIL: `source_idl_sha256` ausente
- FAIL: `source_idl_sha256` inválido (não-hex ou tamanho != 64)

Nota de testes:
- Use `tmp_path` do pytest para criar bundles temporários (não escrever em `/tmp` fixo nem fora do workspace).

Documentação:
- Atualizar `docs/specs/fase-2/02-3-offline-proof-dsl-ir/proof.md` com comandos e exemplos.
- Atualizar `docs/specs/fase-2/02-3-offline-proof-dsl-ir/gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
