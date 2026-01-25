# Expansão (Engine) — Plano em Fases

Objetivo: expandir o engine para suportar, de forma incremental e auditável, um bundle “real” (ex.: Bazari MVP de governança),
sem quebrar o caminho canônico já validado:

`DSL v1.2.2 → IRCS v1 → ISE → bundle → OperationRegistry → IDL Router → Dispatcher → Gates → Ledger`

## Princípios (não negociáveis)

- **Mudanças mínimas e incrementais**: cada fase fecha um DoD com hard gates (tests + proof).
- **Sem regressão do golden path**: Finance (e bundles migrados existentes) continuam passando.
- **Sem relaxar segurança**: `ENGINE_AUTH_MODE=strict` continua token-based; nada de spoof.
- **Sem “bundle meio-válido”**: Proof offline e migration checks continuam determinísticos em `ENGINE_API_MODE=idl`.
- **Sem redesign do router**: rotas dinâmicas continuam derivadas do OperationRegistry.

## Contexto (por que existe esta expansão)

O bundle Bazari MVP (governança de moderação) demanda binds que hoje ainda não são totalmente suportados no runtime:

- operações de “lista” (hoje o DSL não tem `bind.kind=list`; precisa de semântica de list via `read`)
- `delete` genérico (ex.: chat block)
- `transition` (workflows)
- `approval` (aplicar decisões e transições por approvals)

Por isso, o plano abaixo separa **CRUD genérico** primeiro, depois **transições**, depois **approvals/workflows**.

---

## Fases

### 01 — Dispatcher CRUD genérico (Bazari MVP “data/control plane”)

**Objetivo:** suportar entidades novas (ex.: `ContentReport`, `ChatReport`, `ChatBlock`, `ModerationAction`) no state store com:

- `create`
- `read` (inclui “list” quando a rota não tem id no path)
- `delete` (mínimo necessário)

**Não inclui:** workflow/transition genérico, approvals genéricos.

**Entregas:**
- `docs/specs/expansao/01-dispatcher-crud-bazari/spec.md`
- `docs/specs/expansao/01-dispatcher-crud-bazari/prompts.md`
- testes novos em `tests/` cobrindo strict/idl via TestClient

Status: ⏳ PENDENTE

---

### 02 — Dispatcher transitions (workflows) limitado ao subset do DSL atual

**Objetivo:** executar `bind.kind=transition` para workflows do bundle (subset seguro):

- `set_state("<STATE>")`
- `set_field("<field>", "<literal>")` (sem funções como `now()`)
- `bump_version(1)`

**Não inclui:** engine genérico de workflow DSL completo; apenas executor de passos suportados.

Status: ⏳ PENDENTE

---

### 03 — Approvals genéricos para “cases” (ModerationAction)

**Objetivo:** suportar `bind.kind=approval` (request/decide) para cases diferentes de Expense:

- registrar “approval_index” → (entity, entity_id)
- aplicar SoD/invariants antes de commit
- decidir approval e disparar transições finais (Approve/Reject/Revert)

Status: ⏳ PENDENTE

---

### 04 — Bundle Bazari MVP “IDL-ready” (compilação canônica + E2E em PROD/STRICT/IDL)

**Objetivo:** com runtime expandido, compilar IR → bundle e instalar na instituição Bazari, provando:

- Proof offline PASS
- migration checks PASS
- E2E via HTTP (strict tokens) para 10–15 endpoints do MVP

Status: ⏳ PENDENTE

---

### 05 — Hardening e cutover (observabilidade + política de depreciação)

**Objetivo:** consolidar telemetria, status console e política de evolução do bundle (release/pin/rollback) para Bazari.

Status: ⏳ PENDENTE

