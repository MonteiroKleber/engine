# Fase 2 — Etapa 2.7: Prompts (Claude Code)

PROMPT 2.7.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-7-legacy-bridge-readonly/spec.md` e siga como contrato.
2) Mapeie o que já existe de “legado” no código:
   - allow/deny legacy routes
   - qualquer estrutura de asset/bridge
   - ledger/eventos relacionados
3) Proponha o modelo mínimo de `LegacyAsset` e quais eventos entrarão no ledger.
4) Produza:
   - `docs/specs/fase-2/02-7-legacy-bridge-readonly/model.md`
   - `docs/specs/fase-2/02-7-legacy-bridge-readonly/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.7.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisões oficiais desta etapa (não discutir, apenas implementar):
- `asset_id`: aceitar string estável; se for UUID ok, mas não exigir UUID no MVP.
- `source_location` (file): deve ser path **relativo** ao root da instituição/dept; proibir absoluto e `..` (anti path traversal).
- `schema extraction`: mínimo seguro, sem inferência; apenas metadados (CSV: headers; JSON: top-level keys).
- Verificação: sob demanda apenas (sem scheduler) no MVP.


Decisão oficial desta etapa:
- O primeiro conector read-only será **arquivo local** (CSV/JSON), porque é determinístico e não depende de infra externa.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-7-legacy-bridge-readonly/spec.md` e siga como contrato.
2) Implementar `engine.legacy_bridge`:
   - registrar `LegacyAsset` (id, tipo, path, metadata)
   - criar snapshot hash (SHA256 dos bytes do arquivo)
   - verificar drift sob demanda
   - registrar eventos no ledger (append-only)
3) Implementar CLI:
   - `python -m engine.legacy_bridge register --institution ... --dept ... --asset-id ... --path ...`
   - `python -m engine.legacy_bridge verify --institution ... --dept ... --asset-id ...`

Testes obrigatórios:
- Register cria registro append-only e evento no ledger
- Verify em conteúdo igual → OK
- Verify após alterar 1 byte → `LEGACY_DRIFT_DETECTED`

Regras:
- Read-only: verify não pode escrever no arquivo legado.
- Paths devem respeitar isolamento (institution/dept).

Documentação:
- Atualizar `model.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
