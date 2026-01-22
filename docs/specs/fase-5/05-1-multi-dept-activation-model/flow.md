# 05-1 Multi-Dept Activation Model — Flow & Design

**Status:** IMPLEMENTED
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato), mapeamento do código atual

---

## 1. Estado Atual do Sistema

### 1.1 Como Bundle/Dept é Resolvido Hoje

```
┌─────────────────────────────────────────────────────────────────┐
│  Requisição HTTP                                                 │
│  POST /d/finance/finance/expenses                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  dept_routing_middleware (server.py:664-706)                     │
│  ├── resolve_dept_from_path() → extrai "finance" do URL         │
│  ├── validate_dept() → verifica se dept existe no bundle        │
│  └── set_request_dept(request, "finance")                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Bundle Context (load_bundle.py)                                 │
│  ├── mode: "single" | "multi"                                    │
│  ├── departments: Dict[dept_id, DeptContracts]                   │
│  └── path: CURRENT symlink → bundle real                         │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Estrutura de Armazenamento Atual

```
var/institutions/{institution_id}/
├── institution.json                    # Metadata da instituição
├── bundles/
│   ├── CURRENT → finance-pilot        # Symlink para bundle ativo
│   ├── finance-pilot/                 # Bundle single-mode
│   │   ├── bundle.manifest.json
│   │   └── (contracts...)
│   └── multi-pilot/                   # Bundle multi-mode
│       ├── bundle.manifest.json
│       ├── contracts.json             # Lista depts disponíveis
│       ├── contract_ledger.json
│       └── departments/
│           ├── finance/
│           └── support/
├── config/
│   └── ACTIVE.json                    # InstitutionConfig (pinned hashes, etc.)
├── ledger.jsonl                       # Audit ledger
└── state_store.json                   # ou state_store.{dept}.json
```

### 1.3 O Que Existe Hoje

| Conceito | Existe | Onde |
|----------|--------|------|
| Bundle CURRENT (symlink) | ✅ | `bundles/CURRENT` |
| Pinned manifest SHA256 | ✅ | `config/ACTIVE.json` |
| Pinned ledger SHA256 | ✅ | `config/ACTIVE.json` |
| Pinned release_id | ✅ | `config/ACTIVE.json` |
| Default dept | ✅ | `config/ACTIVE.json → defaults.default_dept` |
| Default bundle name | ✅ | `config/ACTIVE.json → defaults.default_bundle_name` |
| **Active depts set** | ❌ | **NÃO EXISTE** |
| **Dept-level pinning** | ❌ | **NÃO EXISTE** |

### 1.4 Problema Atual

Hoje, quando um bundle multi-dept é carregado:

1. **TODOS os departamentos** do bundle ficam automaticamente disponíveis
2. Não há como "ativar" só alguns depts
3. Não há como "instalar" um dept sem ativá-lo
4. Não há registro no ledger de qual dept está ativo
5. Não há como fazer prova offline de quais depts estavam ativos em um momento

---

## 2. Modelo Canônico Proposto

### 2.1 Conceitos

| Termo | Definição |
|-------|-----------|
| **Instalado** | Dept existe no bundle carregado (disponível no disco) |
| **Ativo** | Dept está no "active depts set" e aceita requisições |
| **Pinned** | Dept tem hash de contrato registrado (opcional, para governance) |

### 2.2 Precedência de Resolução

```
┌─────────────────────────────────────────────────────────────────┐
│  Requisição: POST /d/{dept}/...                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Dept está no active_depts set?                               │
│     ├── SIM → continua                                           │
│     └── NÃO → 403 DEPT_NOT_ACTIVE                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Dept existe no bundle CURRENT?                               │
│     ├── SIM → continua                                           │
│     └── NÃO → 400 DEPT_UNKNOWN                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. (Opcional) Dept tem pin? Hash bate?                          │
│     ├── SIM → continua                                           │
│     └── NÃO → 503 DEPT_DRIFT_DETECTED (se ege_enforce_drift)    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ✅ Processa requisição
```

### 2.3 Storage: active_depts.json

**Localização:** `var/institutions/{institution_id}/active_depts.json`

**Formato:**
```json
{
  "schema_version": "1.0",
  "updated_at": "2026-01-20T18:00:00Z",
  "updated_by": "actor-uuid",
  "active_depts": [
    {
      "dept_id": "finance",
      "activated_at": "2026-01-20T17:00:00Z",
      "activated_by": "actor-uuid",
      "source_bundle": "multi-pilot",
      "pinned_contract_sha256": "SHA256:abc123..."
    },
    {
      "dept_id": "support",
      "activated_at": "2026-01-20T17:30:00Z",
      "activated_by": "actor-uuid",
      "source_bundle": "multi-pilot",
      "pinned_contract_sha256": null
    }
  ]
}
```

**Regras:**
- Array ordenado alfabeticamente por `dept_id` (determinismo)
- Cada dept_id aparece no máximo uma vez
- `pinned_contract_sha256` é opcional (null = sem pin)
- `source_bundle` é informativo (bundle de onde veio)

### 2.4 Eventos no Ledger

**Ativação de Dept:**
```json
{
  "seq": 42,
  "event_type": "DEPT_ACTIVATED",
  "timestamp": "2026-01-20T17:00:00Z",
  "actor_id": "actor-uuid",
  "payload": {
    "dept_id": "finance",
    "source_bundle": "multi-pilot",
    "pinned_contract_sha256": "SHA256:abc123..."
  }
}
```

**Desativação de Dept:**
```json
{
  "seq": 43,
  "event_type": "DEPT_DEACTIVATED",
  "timestamp": "2026-01-20T18:00:00Z",
  "actor_id": "actor-uuid",
  "payload": {
    "dept_id": "finance",
    "reason": "Manual deactivation"
  }
}
```

**Pin Update de Dept:**
```json
{
  "seq": 44,
  "event_type": "DEPT_PIN_UPDATED",
  "timestamp": "2026-01-20T19:00:00Z",
  "actor_id": "actor-uuid",
  "payload": {
    "dept_id": "finance",
    "previous_sha256": "SHA256:abc123...",
    "new_sha256": "SHA256:def456..."
  }
}
```

---

## 3. Fluxos de Operação

### 3.1 Fluxo: Ativar Dept

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /admin/institutions/{id}/depts/{dept_id}/activate          │
│  Header: X-Admin-Token                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Validar: dept existe no bundle CURRENT?                      │
│     └── NÃO → 400 DEPT_NOT_INSTALLED                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Validar: dept já está ativo?                                 │
│     └── SIM → 409 DEPT_ALREADY_ACTIVE                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Adicionar dept ao active_depts.json                          │
│  4. Emitir evento DEPT_ACTIVATED no ledger                       │
│  5. Retornar 200 OK                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Fluxo: Desativar Dept

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /admin/institutions/{id}/depts/{dept_id}/deactivate        │
│  Header: X-Admin-Token                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Validar: dept está ativo?                                    │
│     └── NÃO → 404 DEPT_NOT_ACTIVE                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. (Opcional) Validar: dept é o último ativo?                   │
│     └── SIM → 400 CANNOT_DEACTIVATE_LAST_DEPT                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Remover dept do active_depts.json                            │
│  4. Emitir evento DEPT_DEACTIVATED no ledger                     │
│  5. Retornar 200 OK                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Fluxo: Listar Depts

```
┌─────────────────────────────────────────────────────────────────┐
│  GET /admin/institutions/{id}/depts                              │
│  Header: X-Admin-Token                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Retorna:                                                        │
│  {                                                               │
│    "installed": ["finance", "hr", "support"],  // do bundle      │
│    "active": ["finance", "support"],           // do active_depts│
│    "inactive": ["hr"]                          // installed - active│
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Compatibilidade com Estado Atual

### 4.1 Regra de Fallback (Backward Compatibility)

Se `active_depts.json` **NÃO EXISTIR**:

1. **Bundle single-mode:** Usa dept padrão do config (`defaults.default_dept`)
2. **Bundle multi-mode:** Todos os depts do bundle são considerados ativos

Isso garante que instituições existentes continuem funcionando sem migração.

### 4.2 Migração

Não é necessária migração automática. O sistema funciona assim:

```
Se active_depts.json existe:
    → Usa active_depts.json como fonte de verdade
Se NÃO existe:
    → Fallback para comportamento atual (todos depts ativos)
```

A primeira vez que um admin chamar `/admin/.../depts/.../activate` ou `deactivate`:
- Sistema cria `active_depts.json` com estado atual
- A partir daí, usa o arquivo como fonte de verdade

---

## 5. Prova Offline

O modelo permite prova offline de quais depts estavam ativos em um momento:

1. **active_depts.json** é determinístico (ordenado, formato fixo)
2. **Ledger** contém eventos DEPT_ACTIVATED/DEACTIVATED com timestamps
3. **Verificador offline** pode:
   - Ler ledger até timestamp T
   - Reconstruir estado de active_depts naquele momento
   - Verificar se um dept específico estava ativo

---

## 6. Erros Determinísticos

| Código | Condição | HTTP |
|--------|----------|------|
| DEPT_NOT_INSTALLED | Dept não existe no bundle CURRENT | 400 |
| DEPT_NOT_ACTIVE | Dept existe mas não está em active_depts | 403 |
| DEPT_ALREADY_ACTIVE | Tentou ativar dept já ativo | 409 |
| DEPT_DRIFT_DETECTED | Pin existe mas hash não bate | 503 |
| CANNOT_DEACTIVATE_LAST_DEPT | Tentou desativar único dept ativo | 400 |

---

## 7. Diagrama de Estado

```
                    ┌─────────────────┐
                    │   NÃO EXISTE    │
                    │  (no bundle)    │
                    └────────┬────────┘
                             │
                     Deploy bundle
                     com dept
                             │
                             ▼
┌─────────────────┐        ┌─────────────────┐
│     INATIVO     │◄───────│   INSTALADO     │
│  (em bundle,    │        │  (em bundle,    │
│   não ativo)    │        │   sem active_   │
└────────┬────────┘        │   depts.json)   │
         │                 └────────┬────────┘
         │                          │
    activate()              Primeiro activate()
         │                  cria active_depts.json
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────┐
│                   ATIVO                      │
│         (em bundle E em active_depts)        │
└─────────────────────────────────────────────┘
         │
    deactivate()
         │
         ▼
┌─────────────────┐
│     INATIVO     │
└─────────────────┘
```

---

## 8. Resumo do Modelo

| Aspecto | Decisão |
|---------|---------|
| Storage | `active_depts.json` por instituição |
| Formato | JSON com array ordenado por dept_id |
| Eventos | DEPT_ACTIVATED, DEPT_DEACTIVATED, DEPT_PIN_UPDATED |
| Fallback | Se arquivo não existe, todos depts do bundle são ativos |
| Pinning | Opcional, por dept, hash SHA256 |
| Prova offline | Reconstruível a partir do ledger |
| Backward compat | 100% - nenhuma migração necessária |

---

## 9. Implementação (PROMPT 5.1.2)

### Arquivos criados

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `src/engine/core/active_depts.py` | ~400 | Core module para gerenciamento de depts ativos |
| `src/engine/api/admin_depts.py` | ~180 | Endpoints admin para activate/deactivate |
| `tests/test_active_depts.py` | ~580 | 15 testes unitários |

### Arquivos modificados

| Arquivo | Mudanças |
|---------|----------|
| `src/engine/core/errors.py` | +6 códigos de erro |
| `src/engine/api/server.py` | +15 linhas (middleware validation) |

### Endpoints disponíveis

```
GET  /admin/institutions/{id}/depts           → Lista installed/active/inactive
POST /admin/institutions/{id}/depts/{d}/activate
POST /admin/institutions/{id}/depts/{d}/deactivate
```

### Testes

```bash
PYTHONPATH=src python -m pytest tests/test_active_depts.py -v
# 15 passed
```
