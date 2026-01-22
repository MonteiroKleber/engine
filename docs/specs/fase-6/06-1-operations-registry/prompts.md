# Etapa 6.1 — Prompts (Claude Code)

PROMPT 6.1.1 (Diagnóstico + mapa de pontos de integração)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-1-operations-registry/spec.md` e siga como contrato.
2) No código atual, mapeie com evidências:
   - como o bundle é carregado (single/multi)
   - quais contratos existem hoje por dept
   - onde “endpoint_sig” é normalizado (ex.: approvals/mandates/autonomy)
   - onde seria o lugar correto para armazenar um OperationRegistry em runtime
3) Identifique o menor caminho para introduzir `operations.json` sem quebrar bundles legados.

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-1-operations-registry/map.md` (arquivos/funções + proposta de integração)
- `docs/specs/fase-6/06-1-operations-registry/gaps.md` (gaps e decisões necessárias para 6.1.2)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

  PROMPT 6.1.2 (Implementação mínima: contrato `operations.json` + registry em loader)
  [[CLAUDE_CODE_START]]
  Você está no repositório `/home/bazari/engine`.

  Contrato:
  1) Siga `docs/specs/fase-6/06-1-operations-registry/spec.md`.
  2) Mudanças mínimas. Não implementar dispatcher nem rotas dinâmicas nesta etapa.
  3) IMPORTANTE (para manter escopo e evitar retrabalho):
    - **Não mexer** em `src/engine/ise/idl_parser.py` nem criar `IDLOperation` agora.
      O caminho canônico desta fase é **DSL v1.2.2 → IRCS v1 → adapter → ISE**, então o emit de `operations.json`
      deve partir do modelo já disponível (ex.: IRCS/ParsedIDL via `src/engine/ise/ircs_adapter.py`), sem redesenhar parser legado.
    - Não fazer refactor grande em `ALLOWED_ENDPOINT_SIGS` (duplicado em mandates/autonomy/policy) nesta etapa.
      Se precisar, apenas **consumir** o canônico já existente (sem unificar agora).

  Tarefa:
  1) ISE: emitir `operations.json` por dept:
    - single: `operations.json` no root do bundle
    - multi: `departments/<dept_id>/operations.json`
  2) Manifest: incluir `operations.json` como contract no `bundle.manifest.json`.
  3) Loader: carregar `operations.json` e construir `OperationRegistry` em memória por dept.
  4) API interna: expor uma função de lookup para testes (ex.: `get_operation_by_endpoint_sig(dept_id, endpoint_sig)`).

  Reforços (obrigatórios):
  - `operations.json` deve ser determinístico:
    - lista `operations[]` ordenada por (`method`, `path`, `operation_id`) antes de serializar
    - `endpoint_sig` sempre no formato já usado no runtime (ex.: `POST /finance/expenses`)
  - Segurança: `path` deve ser absoluto (começa com `/`) e não pode conter `..`.
  - Compatibilidade:
    - bundles legados sem `operations.json` continuam operando (modo legacy) e **não** entram SAFE_MODE por isso.
    - para bundles que incluírem `operations.json` no manifest, o loader valida hash normalmente.

  Testes obrigatórios:
  - Compilar bundle via ISE (DSL→IRCS→ISE) e verificar que `operations.json` existe e valida schema.
  - Loader carrega bundle e o registry resolve pelo menos:
    - `POST /finance/expenses`
    - `POST /approvals/{approval_id}/decide` (se estiver no contrato)
  - Legacy bundles sem `operations.json` continuam carregando (registry vazio/None sem crash).

  Documentação:
  - Atualizar `docs/specs/fase-6/06-1-operations-registry/spec.md` para marcar status “IMPLEMENTADO” e registrar decisões finais (se necessário).
  - Criar/atualizar `docs/specs/fase-6/06-1-operations-registry/map.md` e `gaps.md` com status final.

  Restrições:
  - Não remover/alterar rotas existentes.
  - Não alterar semântica dos gates.
  [[CLAUDE_CODE_END]]
