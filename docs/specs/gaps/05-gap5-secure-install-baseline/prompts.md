# GAP 5 — Prompts (Claude Code) (produção)

PROMPT 05.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/gaps/05-gap5-secure-install-baseline/spec.md`.
2) Mapear:
   - quais envs são realmente obrigatórias para produção hoje
   - o que preflight valida hoje e o que falta
   - quais defaults de config são inseguros para produção
3) Propor patch mínimo de “install mode” (dev/prod) sem redesign.

Saída:
- `docs/specs/gaps/05-gap5-secure-install-baseline/gaps.md`
[[CLAUDE_CODE_END]]

PROMPT 05.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/gaps/05-gap5-secure-install-baseline/spec.md`.
2) Não adicionar Docker/cluster.

Nota (estado atual do repo):
- `ENGINE_INSTALL_MODE` já foi introduzido no GAP3 (`install_mode.py`). **Não recriar** nem renomear.

Tarefa:
1) Reusar `ENGINE_INSTALL_MODE` existente (dev/prod, default `dev`).
2) Implementar validações adicionais no preflight para modo produção:
   - ENGINE_ISE_ADMIN_TOKEN obrigatório
   - ENGINE_AUTH_MODE=strict obrigatório
3) Ajustar defaults/documentação em `ops/env/engine.env.example` para refletir baseline prod.
4) Garantir defaults seguros ao criar instituição quando `ENGINE_INSTALL_MODE=prod` (config ACTIVE.json).
5) Atualizar smoke check (se necessário) para cobrir console login.
6) Testes unitários do preflight e de criação de instituição para cada violação/default.

Saída:
- Patch mínimo + testes + atualização da doc do gap.
[[CLAUDE_CODE_END]]

PROMPT 05.3 (Ajuste obrigatório: remover “silent prod config”)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contexto:
- Hoje, em `ENGINE_INSTALL_MODE=prod`, a criação de instituição chama `_create_secure_config_if_prod()` mas **não falha** se não conseguir criar `config/ACTIVE.json` (operação “silent”).
- Para instalação honesta em produção, isso é inseguro: a instituição pode nascer sem baseline seguro.

Decisão oficial deste ajuste:
- Em `ENGINE_INSTALL_MODE=prod`, se falhar criar `institutions/<id>/config/ACTIVE.json` com defaults seguros, a criação da instituição deve **falhar determinísticamente** (não apenas logar).

Tarefa (patch mínimo):
1) Ajustar `src/engine/core/institutions.py`:
   - fazer `_create_secure_config_if_prod()` retornar `(ok, error_code, error_message)` (ou equivalente),
   - no fluxo de criação (`create_institution()`), se `prod` e `ok=False`, abortar e retornar erro.
2) Garantir erro determinístico (código estável) para “secure config creation failed in prod”.
   - Se já existir um código adequado em `src/engine/core/errors.py`, reutilizar.
   - Caso contrário, adicionar 1 código novo (ex.: `INSTITUTION_SECURE_CONFIG_REQUIRED`).
3) Atualizar testes:
   - Em `prod`, simular falha de `create_secure_config_for_institution()` e provar que:
     - a criação da instituição falha (não retorna institution válida),
     - o erro/código é determinístico.
   - Em `dev`, simular a mesma falha e provar que:
     - a criação continua funcionando (backward compatible).
4) Atualizar `docs/specs/gaps/05-gap5-secure-install-baseline/gaps.md` com status e evidência do comportamento final.

Restrições:
- Não mudar o schema do `ACTIVE.json`.
- Não introduzir UI/console onboarding novo.
- Mudança mínima, focada apenas em “prod não pode ser silent”.

Saída esperada:
- Patch mínimo + testes + atualização breve da documentação do GAP 5.
[[CLAUDE_CODE_END]]
