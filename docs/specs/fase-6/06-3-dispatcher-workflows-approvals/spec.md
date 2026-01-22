# Etapa 6.3 — Dispatcher v2 (approvals + commit/reject)

**Status:** ✅ IMPLEMENTADO (2026-01-21)
**Pré-requisitos:** Etapa 6.1 ✅ (OperationRegistry) + Etapa 6.2 ✅ (Dispatcher CRUD)

## 1) Objetivo

Estender o dispatcher para executar operações do `OperationRegistry` com `bind.kind=approval`,
reutilizando o approvals engine existente para chegar a um fluxo institucional completo (pilot Finance)
**sem handlers fixos**:

`create expense` → `pending_approval` → `decide approve/reject` → `COMMITTED/REJECTED`.

Nota importante (realidade do engine hoje):
- `workflows.json` existe como contrato, mas **não existe um workflow engine genérico** que interprete e aplique
  transições arbitrárias descritas nesse contrato.
- Portanto, **workflow/transition genérico fica fora do escopo** desta etapa e será tratado em etapa posterior.

## 2) Estado atual (realidade do código)

- Workflows e approvals existem e já são usados pelos handlers legacy.
- O dispatcher v1 (6.2) cobre apenas `create/read` com gates pre.
- O endpoint `/approvals/{approval_id}/decide` existe e já executa gates e aplica decisão.

## 3) Decisões canônicas desta etapa

### 3.1 Sem rotas dinâmicas

- Ainda **não** publicar rotas dinâmicas no FastAPI (isso é etapa 6.4).
- Validação via testes chamando o dispatcher diretamente.

### 3.2 Reuso obrigatório dos motores existentes

- Não reimplementar workflow engine nem approvals engine.
- Dispatcher deve orquestrar os módulos existentes para:
  - criar approval request quando aplicável
  - aplicar decisão e produzir commit/reject

### 3.3 Determinismo e prova

- Mesmos inputs → mesma decisão/saída, sem heurística.
- Ledger deve registrar a mesma trilha já registrada no caminho legacy (não inventar “eventos novos” sem necessidade).

## 4) Modelo canônico de execução (approval)

Para `bind.kind=approval`:

Dois caminhos:

### 5.1 Criar approval request (quando operação dispara aprovação)

Entrada:
- `operation` com `bind: { kind=approval, workflow, transition, decision="approve|reject" }`
- `path_params` contendo `id` (entity id)

Saída mínima:
- `202` + `{ status: "pending_approval", approval_id, step }`

### 5.2 Decidir approval (aplicar decisão)

Entrada:
- `approval_id` (path param)
- `decision` (body)
- `reason` (body opcional)

Saída mínima:
- `200` + `{ status: "decided", decision, case_status }`

Notas:
- SoD deve bloquear auto-approve conforme contratos.
- Quorum/distinct_actors/expiry devem ser respeitados conforme approvals engine existente.

## 6) O que não pode mudar

- Não alterar semântica dos contratos approvals/workflows atuais.
- Não remover/alterar rotas legacy existentes.
- Não adicionar router dinâmico nesta etapa.

## 7) Critérios de aceite (Etapa 6.3)

- ✅ Existe implementação no dispatcher para:
  - ✅ `dispatch_approval_request(...)`
  - ✅ `dispatch_approval_decide(...)`
- ✅ Testes cobrem o fluxo Finance completo via dispatcher:
  - ✅ create expense (6.2) → approval pending
  - ✅ self-approve bloqueado (SoD)
  - ✅ manager approve → COMMITTED
  - ✅ manager reject → REJECTED
- ✅ Testes cobrem isolamento:
  - ✅ 2 instituições × 2 depts
- ✅ Testes validam invariants durante approve

## 8) Implementação (2026-01-21)

### 8.1 Arquivos Modificados

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/dispatcher.py` | Adicionado `dispatch_approval_request()` e `dispatch_approval_decide()` |
| `tests/test_dispatcher.py` | 14 novos testes de approvals (28 total) |

### 8.2 Novas Funções

```python
async def dispatch_approval_request(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Optional[Dict[str, str]] = None,
) -> DispatchResult:
    """Create expense with approval support.
    Returns 202 if approval required, 200 otherwise.
    """

async def dispatch_approval_decide(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    approval_id: str,
    decision: str,  # "approve" or "reject"
    reason: Optional[str] = None,
) -> DispatchResult:
    """Decide on approval with full gates + SoD + invariants."""
```

### 8.3 Pipeline de Execução

**dispatch_approval_request:**
1. RBAC gate
2. Policy PRE gate
3. Mandates PRE gate
4. Autonomy PRE gate
5. Check approvals policy for endpoint_sig
6. Persist entity to state store
7. If approval required: emit APPROVAL_REQUESTED, return 202
8. If no approval: return 200

**dispatch_approval_decide:**
1. Validate decision ("approve"/"reject")
2. Find APPROVAL_REQUESTED event
3. Check if already decided (→ 409)
4. Get rule from step
5. Check role can decide (→ 403)
6. SoD check (requester ≠ decider) (→ 409)
7. If approve:
   - Policy POST gate
   - Mandates POST gate
   - Autonomy POST gate
   - Invariants validation (→ 422)
8. Update entity status (COMMITTED/REJECTED)
9. Emit APPROVAL_DECIDED
10. Emit CASE_COMMITTED or CASE_REJECTED

### 8.4 Testes Implementados

| Classe | Testes | Cobertura |
|--------|--------|-----------|
| `TestDispatchApprovalRequest` | 2 | Create with/without approval |
| `TestDispatchApprovalDecide` | 7 | Approve, reject, SoD, role check, validation |
| `TestFullApprovalFlow` | 2 | Complete approve/reject flows |
| `TestApprovalMultiTenantIsolation` | 2 | 2 inst × 2 depts |
| `TestInvariantsValidation` | 1 | Invariant check during approve |
