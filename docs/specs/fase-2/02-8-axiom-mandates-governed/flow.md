# AXIOM MVP - Governed Mandates Flow

**Data:** 2026-01-18
**Tipo:** Fluxo de governança para PROMPT 2.8.1
**Status:** IMPLEMENTADO (PROMPT 2.8.2)

---

## Resumo Executivo

Este documento define o fluxo de governança para mandatos via EGE proposals, permitindo que instituições criem, aprovem e apliquem mudanças em mandatos sem edição direta de arquivos.

---

## 1. Contexto Atual

### 1.1 Como Mandates São Carregados Hoje

| Modo | Fonte | Carregamento |
|------|-------|--------------|
| **Single-dept** | `<bundle>/mandates.json` | `_load_mandates_single_mode()` em `loader/load_bundle.py:503-526` |
| **Multi-dept** | `<bundle>/departments/<dept>/mandates.json` | `_load_mandates_multi_mode()` em `loader/load_bundle.py:529-559` |

**Fluxo atual:**
1. Bundle é carregado no startup (`load_bundle()`)
2. Mandates são lidos de arquivos JSON estáticos
3. `set_mandates(dept_id, mandate_def)` armazena em memória global `_mandates: Dict[str, MandateDef]`
4. Runtime consulta `get_mandates(dept_id)` para avaliar requests

### 1.2 Limitação Atual

- **Sem governança**: Mudança de mandato requer editar arquivo e fazer rebuild/redeploy
- **Sem auditoria**: Não há registro de quem/quando/por que alterou mandatos
- **Sem aprovação**: Qualquer pessoa com acesso ao bundle pode alterar

---

## 2. Modelo Proposto: Governed Mandates via EGE

### 2.1 Conceito

Reutilizar o mecanismo de EGE proposals (já implementado para drift/pins) para governar mudanças em mandatos:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MANDATE PROPOSAL FLOW                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. PROPOSE                                                     │
│     Admin → API → Create MandateProposal                        │
│                   (operation: create | update | revoke)         │
│                   Status: OPEN                                  │
│                   Ledger: MANDATE_PROPOSED                      │
│                                                                 │
│  2. DECIDE                                                      │
│     Admin → API → Accept/Reject Proposal                        │
│                   Status: DECIDED                               │
│                   Ledger: MANDATE_APPROVED/REJECTED             │
│                                                                 │
│  3. APPLY (if approved)                                         │
│     System → Update governed_mandates.json                      │
│              Reload mandates into runtime                       │
│              Ledger: MANDATE_APPLIED                            │
│                                                                 │
│  4. RUNTIME                                                     │
│     Request → Evaluate mandate (governed takes precedence)      │
│               Allow/Deny based on mandate rules                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Decisão de Abordagem: Opção A vs Opção B

| Critério | **Opção A: Override Governado** | **Opção B: Rebuild Bundle** |
|----------|--------------------------------|----------------------------|
| Complexidade | Média | Alta |
| Tempo de aplicação | Imediato (hot-reload) | Requer rebuild + deploy |
| Consistência | Override layer sobre bundle | Bundle único (imutável) |
| Auditoria | Governado separado do bundle | Tudo no bundle |
| Rollback | Simples (remover override) | Requer redeploy de bundle anterior |

**Recomendação: Opção A (Override Governado)**

Justificativa:
1. Menor fricção para mudanças de mandato
2. Separação clara: bundle = contrato técnico, governed = política institucional
3. Consistente com padrão existente (institution_config já faz override de comportamentos)
4. Permite rollback rápido sem rebuild

---

## 3. Fluxo Detalhado

### 3.1 PROPOSE: Criar Proposta de Mandato

**Endpoint:** `POST /admin/institutions/{institution_id}/mandates/proposals`

**Operações suportadas:**
- `create`: Adicionar novo mandato
- `update`: Alterar mandato existente
- `revoke`: Revogar mandato existente

**Request:**
```json
{
  "operation": "create",
  "dept_id": "finance",  // opcional (null = single-mode)
  "mandate": {
    "mandate_id": "expense-limit-manager",
    "endpoint_sig": "POST /finance/expenses",
    "phase": "pre",
    "allowed_roles": ["manager"],
    "limits": [
      {
        "rule_type": "numeric_max",
        "field_path": "amount",
        "value": 10000
      }
    ],
    "valid_from": "2026-01-20T00:00:00Z",
    "valid_until": "2026-12-31T23:59:59Z"
  },
  "reason": "Permitir managers aprovar despesas até R$10.000"
}
```

**Response:**
```json
{
  "proposal_id": "uuid-...",
  "status": "OPEN",
  "operation": "create",
  "created_at": "2026-01-18T14:30:00Z",
  "created_by": "admin@institution"
}
```

**Ledger Event:** `MANDATE_PROPOSED`

### 3.2 DECIDE: Aprovar ou Rejeitar

**Endpoint:** `POST /admin/institutions/{institution_id}/mandates/proposals/{proposal_id}/decide`

**Request:**
```json
{
  "decision": "approve",  // ou "reject"
  "reason": "Aprovado pelo comitê de governança"
}
```

**Response:**
```json
{
  "proposal_id": "uuid-...",
  "status": "DECIDED",
  "decision": "approve",
  "decided_at": "2026-01-18T15:00:00Z",
  "decided_by": "governance@institution"
}
```

**Ledger Events:**
- Se aprovado: `MANDATE_APPROVED`
- Se rejeitado: `MANDATE_REJECTED`

### 3.3 APPLY: Aplicar Mandato Aprovado

**Automático após aprovação:**

1. Carregar `governed_mandates.json` atual
2. Aplicar operação (create/update/revoke)
3. Salvar novo `governed_mandates.json`
4. Atualizar `set_mandates()` em memória
5. Emitir `MANDATE_APPLIED` no ledger

**Ledger Event:** `MANDATE_APPLIED`
```json
{
  "event_type": "MANDATE_APPLIED",
  "payload": {
    "proposal_id": "uuid-...",
    "operation": "create",
    "mandate_id": "expense-limit-manager",
    "applied_at": "2026-01-18T15:00:01Z",
    "effective_from": "2026-01-20T00:00:00Z"
  }
}
```

### 3.4 REVOKE: Revogar Mandato

**Operação especial via proposal:**

```json
{
  "operation": "revoke",
  "dept_id": "finance",
  "mandate_id": "expense-limit-manager",
  "reason": "Mandato expirou e não será renovado"
}
```

**Ledger Event:** `MANDATE_REVOKED`

---

## 4. Storage Model

### 4.1 Estrutura de Arquivos

```
<institution_root>/
├── governed_mandates/
│   ├── mandates.jsonl           # Append-only history
│   ├── proposals.jsonl          # Proposals append-only
│   └── state.json               # Current effective mandates
│
├── depts/<dept_id>/governed_mandates/
│   ├── mandates.jsonl           # Per-dept history
│   ├── proposals.jsonl          # Per-dept proposals
│   └── state.json               # Per-dept state
```

### 4.2 governed_mandates/state.json

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-01-18T15:00:01Z",
  "mandates": [
    {
      "mandate_id": "expense-limit-manager",
      "endpoint_sig": "POST /finance/expenses",
      "phase": "pre",
      "allowed_roles": ["manager"],
      "limits": [...],
      "valid_from": "2026-01-20T00:00:00Z",
      "valid_until": "2026-12-31T23:59:59Z",
      "status": "active",
      "created_by_proposal": "uuid-...",
      "created_at": "2026-01-18T15:00:01Z"
    }
  ]
}
```

---

## 5. Precedência de Mandatos

### 5.1 Ordem de Avaliação

```python
def get_effective_mandates(dept_id: str) -> MandateDef:
    """Retorna mandatos efetivos (governados + bundle)."""

    # 1. Carregar governados (prioridade)
    governed = load_governed_mandates(dept_id)

    # 2. Carregar do bundle
    bundle_mandates = get_mandates_from_bundle(dept_id)

    # 3. Merge: governados sobrescrevem bundle por mandate_id
    effective = merge_mandates(bundle_mandates, governed)

    return effective
```

### 5.2 Regras de Merge

| Cenário | Resultado |
|---------|-----------|
| mandate_id só no bundle | Usa bundle |
| mandate_id só no governado | Usa governado |
| mandate_id em ambos | **Governado vence** |
| mandate_id revogado no governado | **Mandato removido** (não existe) |

---

## 6. Integração com EGE Existente

### 6.1 Reutilização de Padrões

| Componente | Já Existe | Reutilizar |
|------------|-----------|------------|
| Proposal JSONL append-only | `ege_proposals.py` | Padrão de storage |
| State folding | `load_current_state()` | Pattern de computar estado |
| Ledger events | `_emit_proposal_event()` | Pattern de eventos |
| File locking | `_get_file_lock()` | Concurrency |

### 6.2 Novo Módulo Proposto

```
src/engine/core/governed_mandates.py

Classes:
- MandateProposal (dataclass)
- MandateProposalState (dataclass)

Funções:
- create_mandate_proposal()
- decide_mandate_proposal()
- apply_mandate_proposal()
- load_governed_mandates()
- get_effective_mandates()
```

---

## 7. Diagrama de Sequência

```
Admin           API             ProposalRegistry     MandateStore      Ledger
  │              │                    │                   │              │
  │ POST /mandates/proposals          │                   │              │
  │─────────────────────────────────►│                   │              │
  │              │ validate proposal  │                   │              │
  │              │───────────────────►│                   │              │
  │              │                    │ append to JSONL   │              │
  │              │                    │───────────────────│              │
  │              │                    │                   │ MANDATE_PROPOSED
  │              │                    │                   │─────────────►│
  │◄─────────────────────────────────│                   │              │
  │ {proposal_id, status: OPEN}      │                   │              │
  │              │                    │                   │              │
  │ POST /proposals/{id}/decide      │                   │              │
  │─────────────────────────────────►│                   │              │
  │              │ validate decision  │                   │              │
  │              │───────────────────►│                   │              │
  │              │                    │ append decision   │              │
  │              │                    │───────────────────│              │
  │              │                    │                   │ MANDATE_APPROVED
  │              │                    │                   │─────────────►│
  │              │                    │                   │              │
  │              │                    │ apply to state    │              │
  │              │                    │──────────────────►│              │
  │              │                    │                   │ update state │
  │              │                    │                   │──────────────│
  │              │                    │                   │ MANDATE_APPLIED
  │              │                    │                   │─────────────►│
  │              │                    │                   │              │
  │              │ reload mandates    │                   │              │
  │              │◄──────────────────────────────────────│              │
  │◄─────────────────────────────────│                   │              │
  │ {status: DECIDED, decision: approve}                 │              │
```

---

## 8. Eventos de Ledger

### 8.1 Novos Event Types

| Event Type | Quando | Payload |
|------------|--------|---------|
| `MANDATE_PROPOSED` | Proposal criada | proposal_id, operation, mandate, reason |
| `MANDATE_APPROVED` | Proposal aprovada | proposal_id, decision, decided_by |
| `MANDATE_REJECTED` | Proposal rejeitada | proposal_id, decision, reason |
| `MANDATE_APPLIED` | Mandato aplicado | proposal_id, mandate_id, effective_from |
| `MANDATE_REVOKED` | Mandato revogado | mandate_id, reason |

### 8.2 Auditability

Cada evento no ledger inclui:
- `actor_id`: Quem realizou a ação
- `timestamp`: Quando
- `payload`: O que foi alterado
- Hash chain: Prova de integridade

---

## 9. CLI Commands

```bash
# Criar proposal
python -m engine.governed_mandates propose \
    --institution <uuid> \
    --dept finance \
    --operation create \
    --mandate-file mandate.json \
    --reason "Novo limite para managers"

# Decidir proposal
python -m engine.governed_mandates decide \
    --institution <uuid> \
    --proposal-id <uuid> \
    --decision approve \
    --reason "Aprovado"

# Listar mandatos governados
python -m engine.governed_mandates list \
    --institution <uuid> \
    --dept finance

# Listar proposals pendentes
python -m engine.governed_mandates proposals \
    --institution <uuid> \
    --status OPEN
```

---

## 10. Backward Compatibility

### 10.1 Garantias

1. **Bundle mandates continuam funcionando**: Se não houver governed_mandates, bundle mandates são usados
2. **Sem breaking changes**: Nenhuma API existente é alterada
3. **Opt-in**: Institucions escolhem quando usar governed mandates

### 10.2 Migration Path

1. **Fase 1**: Implementar governed_mandates (este incremento)
2. **Fase 2**: Instituições começam a usar proposals
3. **Fase 3**: (Opcional) Deprecar edição direta de mandates no bundle

---

## 11. Security Considerations

### 11.1 Authorization

- Apenas `admin` roles podem criar/decidir proposals
- Verificação via `admin_auth` middleware existente

### 11.2 Validation

- Schema validation igual a `parse_mandates_data()` existente
- endpoint_sig deve estar em `ALLOWED_ENDPOINT_SIGS`
- Validity window deve ser futuro ou atual

### 11.3 Immutability

- JSONL append-only garante que proposals não podem ser editadas
- Cada decisão é um novo record, não uma mutação
