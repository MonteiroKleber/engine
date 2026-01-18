# IDL Canônica v1.x — Especificação

**Data:** 2026-01-18
**Versão:** 1.1
**Etapa:** 02 — IDL Canônica e Artefatos

---

## 1. Visão Geral

Este documento define a estrutura canônica da Interface Definition Language (IDL) do Libervia Engine MVP. A IDL descreve contratos institucionais que governam o comportamento do sistema em runtime.

### 1.1 Princípio Fundamental

> **Nenhuma execução fora de mandato.**

### 1.2 Semântica de Contratos Ausentes vs Regras Não-Aplicáveis

| Situação | Comportamento Canônico MVP |
|----------|----------------------------|
| **Contrato institucional ausente** (arquivo não existe) | Bundle inválido → **SAFE_MODE** |
| **Contrato presente, regra não concede** (request não autorizado) | Request negado → **deny** com evento no ledger |

Esta distinção é fundamental:
- **SAFE_MODE** = falha de validação do bundle no boot (sistema não opera)
- **deny** = decisão de governança em runtime (sistema opera, request negado)

---

## 2. Contratos Institucionais

### 2.1 Contratos Mínimos Obrigatórios (Decisão MVP)

| Contrato | Arquivo | Descrição | Status no Código |
|----------|---------|-----------|------------------|
| **Policies** | `policies.json` | Regras de validação de campos | **GAP**: tratado como opcional |
| **Mandates** | `mandates.json` | Delegações de autoridade | **GAP**: tratado como opcional |
| **Autonomy** | `autonomy.json` | Níveis de autonomia L0..L4 | **GAP**: tratado como opcional |

**Decisão Oficial (2026-01-17):**
- `policies.json`, `mandates.json`, `autonomy.json` são **contratos institucionais mínimos obrigatórios**.
- Se qualquer um estiver **ausente** no bundle executável, o bundle é **inválido** e o runtime deve entrar em **SAFE_MODE**.
- Não existe "modo permissivo" por ausência de contrato.

### 2.2 Contratos Operacionais

| Contrato | Arquivo | Obrigatório | Descrição |
|----------|---------|-------------|-----------|
| RBAC | `rbac.json` | Sim (via manifest) | Controle de acesso baseado em roles |
| SoD | `sod.json` | Sim (via manifest) | Segregação de deveres |
| Approvals | `approvals.json` | Sim (via manifest) | Políticas de aprovação |
| Invariants | `invariants.json` | Sim (via manifest) | Invariantes de domínio |
| Workflows | `workflows.json` | Sim (via manifest) | Definição de fluxos de trabalho |
| OpenAPI | `openapi.yaml` | Não | Especificação da API |

### 2.3 Metadados de Bundle

| Arquivo | Obrigatório | Descrição |
|---------|-------------|-----------|
| `bundle.manifest.json` | Sim | Metadados e hashes do bundle |
| `contract_ledger.json` | Sim (via manifest) | Placeholder para registro de auditoria |

---

## 3. Schema de bundle.manifest.json (Real v8.1.1)

O loader consome o manifest no seguinte formato:

```json
{
  "name": "finance-pilot",
  "version": "1.0.0",
  "description": "Finance pilot bundle for Libervia Engine",
  "contracts": [
    {
      "file": "contract_ledger.json",
      "sha256": "SHA256:71fbeddb02e9a3155f2483d237dcb5ec6f9b52b0204c01c01fcab042fecdeed3",
      "required": true
    },
    {
      "file": "rbac.json",
      "sha256": "SHA256:5a75d6bdef3e08d8dce63dac535aa9fd5ff489f1efbfcaf7bd5f2d52806d2439",
      "required": true
    }
  ]
}
```

**Campos:**
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do bundle |
| `version` | string | Versão semver |
| `description` | string | Descrição do bundle |
| `contracts` | array | Lista de contratos |
| `contracts[].file` | string | Nome do arquivo |
| `contracts[].sha256` | string | Hash no formato `SHA256:<hex>` |
| `contracts[].required` | boolean | Se `true` e arquivo ausente → SAFE_MODE |

**Evidência:** [load_bundle.py:351](../../../../src/engine/loader/load_bundle.py) — `contracts = manifest.get("contracts", [])`

**Hash Format:** O loader aceita hashes com ou sem prefixo `SHA256:` (normalizado em [verify_hashes.py:23](../../../../src/engine/loader/verify_hashes.py)).

---

## 4. Schema de contract_ledger.json (Real v8.1.1)

**Estado atual:** placeholder sem funcionalidade de prova offline.

```json
{
  "version": "1.0.0",
  "name": "contract_ledger",
  "description": "Ledger contract for finance-pilot bundle",
  "entries": []
}
```

**GAP:** O `contract_ledger.json` atual é um placeholder vazio. Não contém:
- Hashes dos contratos
- IDL hash
- Audit trail
- Prova offline de integridade

**Proposto (pós-mudança):** Ver seção 4.9 do documento original para schema desejado.

---

## 5. Schema de Contratos de Governança

### 5.1 policies.json (v1.1)

Define regras de validação aplicadas em runtime.

```json
{
  "policy_schema_version": "1.1",
  "policies": [
    {
      "policy_id": "string (único)",
      "phase": "pre|post",
      "endpoint_sig": "POST /finance/expenses|POST /approvals/{approval_id}/decide",
      "rule_type": "numeric_max|numeric_min|string_max_len|required_field|enum_allowlist",
      "field_path": "string (dot notation)",
      "value": "any (threshold/allowlist)",
      "message": "string (opcional)"
    }
  ]
}
```

**Regras de Validação:**
- `endpoint_sig` deve ser exatamente um dos endpoints permitidos
- `field_path` aceita apenas `[a-zA-Z0-9_.]`, sem dots consecutivos ou terminais
- `phase` deve ser `"pre"` ou `"post"`

**Evidência:** [policies_emit.py:13](../../../../src/engine/ise/emit/policies_emit.py)

### 5.2 mandates.json (v1.0)

Define delegações de autoridade.

```json
{
  "mandate_schema_version": "1.0",
  "mandates": [
    {
      "mandate_id": "string (único)",
      "actor_pattern": "string|regex",
      "endpoint_sig": "string",
      "phase": "pre|post",
      "conditions": {},
      "effect": "grant|deny"
    }
  ]
}
```

**Evidência:** [mandates.py](../../../../src/engine/core/mandates.py)

### 5.3 autonomy.json (v1.0)

Define níveis de autonomia do sistema.

```json
{
  "autonomy_schema_version": "1.0",
  "current_level": 0-4,
  "rules": [
    {
      "rule_id": "string",
      "endpoint_sig": "string",
      "phase": "pre|post",
      "required_level": 0-4
    }
  ]
}
```

**Níveis de Autonomia:**
| Level | Descrição |
|-------|-----------|
| L0 | Full human oversight required |
| L1 | Minimal autonomy |
| L2 | Moderate autonomy |
| L3 | High autonomy |
| L4 | Full autonomy |

**Evidência:** [autonomy.py:39](../../../../src/engine/core/autonomy.py)

---

## 6. Comportamento: Atual vs Canônico MVP

### 6.1 Carregamento de policies.json

**Comportamento atual (v8.1.1):**
```
Se policies.json existe:
  - Carregar e validar schema
  - Se inválido → SAFE_MODE
  - Se válido → usar para avaliação
Se policies.json NÃO existe:
  - set_policies(None, None)  # allow-all
```
**Evidência:** [load_bundle.py:472](../../../../src/engine/loader/load_bundle.py)

**Comportamento canônico MVP (decisão):**
```
Se policies.json existe:
  - Carregar e validar schema
  - Se inválido → SAFE_MODE
  - Se válido → usar para avaliação
Se policies.json NÃO existe:
  - enter_safe_mode(BUNDLE_CONTRACT_MISSING, ...)
```

### 6.2 Carregamento de mandates.json

**Comportamento atual (v8.1.1):**
```
Se mandates.json existe:
  - Carregar e validar schema
  - Se inválido → SAFE_MODE
  - Se válido → usar para avaliação
Se mandates.json NÃO existe:
  - set_mandates(None, None)  # allow-all
```
**Evidência:** [load_bundle.py:525](../../../../src/engine/loader/load_bundle.py)

**Comportamento canônico MVP (decisão):**
```
Se mandates.json NÃO existe:
  - enter_safe_mode(BUNDLE_CONTRACT_MISSING, ...)
```

### 6.3 Carregamento de autonomy.json

**Comportamento atual (v8.1.1):**
```
Se autonomy.json existe:
  - Carregar e validar schema
  - Se inválido → SAFE_MODE
  - Se válido → usar para avaliação
Se autonomy.json NÃO existe:
  - set_autonomy_for_dept(None, None)  # L4 full autonomy
```
**Evidência:** [load_bundle.py:584](../../../../src/engine/loader/load_bundle.py)

**Comportamento canônico MVP (decisão):**
```
Se autonomy.json NÃO existe:
  - enter_safe_mode(BUNDLE_CONTRACT_MISSING, ...)
```

### 6.4 Avaliação em Runtime (quando contrato presente)

**Comportamento atual e canônico (idênticos quando contrato existe):**

| Gate | Request não autorizado |
|------|------------------------|
| policies | `PolicyEvalResult(allow=False)` → 422 |
| mandates | `MandateEvalResult(allow=False)` → 403 |
| autonomy | `AutonomyEvalResult(decision="deny")` → 403 |

Eventos são emitidos no ledger para todas as avaliações.

---

## 7. Estrutura de Bundle

### 7.1 Single-Mode Bundle (v8.1.1 atual)

```
finance-pilot/
├── bundle.manifest.json     (obrigatório)
├── contract_ledger.json     (obrigatório via manifest)
├── rbac.json                (obrigatório via manifest)
├── approvals.json           (obrigatório via manifest)
├── workflows.json           (obrigatório via manifest)
├── sod.json                 (obrigatório via manifest)
├── invariants.json          (obrigatório via manifest)
├── openapi.yaml             (opcional via manifest)
├── policies.json            (AUSENTE - GAP)
├── mandates.json            (AUSENTE - GAP)
└── autonomy.json            (AUSENTE - GAP)
```

**GAP:** O bundle `finance-pilot` atual não inclui `policies.json`, `mandates.json`, `autonomy.json`.

### 7.2 Single-Mode Bundle (canônico MVP)

```
bundle_name/
├── bundle.manifest.json     (obrigatório)
├── contract_ledger.json     (obrigatório)
├── rbac.json                (obrigatório)
├── approvals.json           (obrigatório)
├── workflows.json           (obrigatório)
├── sod.json                 (obrigatório)
├── invariants.json          (obrigatório)
├── openapi.yaml             (opcional)
├── policies.json            (OBRIGATÓRIO - institucional)
├── mandates.json            (OBRIGATÓRIO - institucional)
└── autonomy.json            (OBRIGATÓRIO - institucional)
```

### 7.3 Multi-Mode Bundle

```
bundle_name/
├── bundle.manifest.json
├── contract_ledger.json
├── contracts.json           (interdepartmental)
└── departments/
    └── <dept_id>/
        ├── rbac.json
        ├── approvals.json
        ├── workflows.json
        ├── sod.json
        ├── invariants.json
        ├── openapi.yaml
        ├── policies.json    (OBRIGATÓRIO por dept)
        ├── mandates.json    (OBRIGATÓRIO por dept)
        └── autonomy.json    (OBRIGATÓRIO por dept)
```

---

## 8. Endpoints Permitidos

Os contratos de governança (policies, mandates, autonomy) só podem referenciar endpoints explicitamente permitidos:

```python
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
})
```

**Evidência:** [policies_emit.py:13](../../../../src/engine/ise/emit/policies_emit.py), [autonomy.py:30](../../../../src/engine/core/autonomy.py)

Qualquer tentativa de usar um endpoint não listado resulta em erro de compilação.

---

## 9. Resumo de GAPs para MVP

| Item | Estado Atual | Estado Canônico MVP | Mudança Necessária |
|------|--------------|---------------------|-------------------|
| policies.json ausente | allow-all | SAFE_MODE | Alterar load_bundle.py |
| mandates.json ausente | allow-all | SAFE_MODE | Alterar load_bundle.py |
| autonomy.json ausente | L4 (full autonomy) | SAFE_MODE | Alterar load_bundle.py |
| contract_ledger.json | placeholder vazio | prova offline | Implementar schema completo |
| bundle finance-pilot | sem contratos institucionais | com contratos | Gerar contratos mínimos |

---

## 10. Referências

- [Gap Report v8.1.1](../01-baseline/gap-report.md) — Análise de gaps e risco crítico #1
- [Definition of Done](../../../pilot/DEFINITION_OF_DONE.md) — Critérios de aceite do pilot
- [Baseline v8.1.1](../01-baseline/baseline.md) — Estado atual do sistema

---

**Status:** ESPECIFICAÇÃO ATIVA
**Próxima Etapa:** Implementar SAFE_MODE por ausência de contrato institucional
**Data:** 2026-01-18
