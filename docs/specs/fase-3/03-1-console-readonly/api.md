# AXIOM Console - API Endpoints Existentes

**Data:** 2026-01-18
**Tipo:** Inventário de endpoints para PROMPT 3.1.1
**Status:** IMPLEMENTADO (PROMPT 3.1.2)

---

## Resumo

O console read-only foi implementado **sem criar novos endpoints JSON**. Todos os dados necessários são obtidos via APIs admin existentes. O console adiciona apenas rotas HTML (`/console/*`).

---

## 1. Endpoints Read-Only Existentes

### 1.1 Institutions

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/admin/institutions` | Listar todas as institutions | X-Admin-Token |
| GET | `/admin/institutions/{id}` | Buscar institution por UUID | X-Admin-Token |
| GET | `/admin/institutions/by-slug/{slug}` | Buscar por slug | X-Admin-Token |

**Arquivo:** [admin_institutions.py](../../../src/engine/api/admin_institutions.py)

**Uso no console:** Página Home - lista de institutions para seleção.

---

### 1.2 Institution Config

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/admin/institutions/{id}/config` | Configuração atual | X-Admin-Key |
| GET | `/admin/institutions/{id}/config/history` | Histórico de mudanças | X-Admin-Key |

**Arquivo:** [admin_institution_config.py](../../../src/engine/api/admin_institution_config.py)

**Uso no console:**
- Página Status: exibir pinned_bundle_manifest_sha256, pinned_contract_ledger_sha256
- Página Status: exibir emergency_freeze, safe_mode_enabled

---

### 1.3 EGE (Drift & Pins)

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/admin/ege/proposals` | Listar proposals drift | X-Admin-Key |
| GET | `/admin/ege/pins/status` | Status de pins (pinned vs observed) | X-Admin-Key |

**Arquivo:** [admin_ege.py](../../../src/engine/api/admin_ege.py)

**Uso no console:**
- Página Status: drift_status (CLEAR, ACTIVE, UNPINNED)
- Página Bundles: pinned vs observed hashes

**Nota:** POST /admin/ege/drift/check é necessário para atualizar drift, mas console não deve chamar (é mutação). Console exibe apenas estado cached.

---

### 1.4 Governed Mandates

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/admin/mandates/proposals` | Listar proposals de mandatos | X-Admin-Key |
| GET | `/admin/mandates/governed` | Mandatos governados ativos | X-Admin-Key |
| GET | `/admin/mandates/effective` | Mandatos efetivos (merge) | X-Admin-Key |

**Arquivo:** [admin_mandates.py](../../../src/engine/api/admin_mandates.py)

**Uso no console:**
- Página Status: exibir mandatos ativos
- Página Bundles: exibir se há governed mandates overriding bundle

---

### 1.5 Admin Keys

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/admin/institutions/{id}/admin-keys` | Listar keys da institution | X-Admin-Key |

**Arquivo:** [admin_keys.py](../../../src/engine/api/admin_keys.py)

**Uso no console:** Página de administração (opcional, fora de scope MVP).

---

### 1.6 Pipeline (Dev Runs)

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/pipeline/build/runs` | Listar dev runs | X-Admin-Token |
| GET | `/pipeline/build/runs/{run_id}` | Detalhe de run | X-Admin-Token |
| GET | `/pipeline/build/diff?run_a=&run_b=` | Diff entre runs | X-Admin-Token |
| GET | `/pipeline/build/download?run_id=` | Download bundle zip | X-Admin-Token |

**Arquivo:** [pipeline.py](../../../src/engine/api/pipeline.py)

**Uso no console:**
- Página Bundles: listar releases disponíveis
- Página Bundles: mostrar trace.json (hashes)

---

### 1.7 Health

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/health` | Status do runtime | Nenhum |

**Arquivo:** [server.py](../../../src/engine/api/server.py)

**Uso no console:**
- Página Status: mode (ACTIVE/SAFE_MODE), reason_code, details

---

## 2. Endpoints Write-Only (Não usar no Console)

O console **NÃO DEVE** chamar estes endpoints, pois são operações de escrita:

| Endpoint | Motivo |
|----------|--------|
| POST `/admin/institutions` | Cria institution |
| PUT `/admin/institutions/{id}/config` | Atualiza config |
| POST `/admin/ege/drift/check` | Recalcula drift (mutation) |
| POST `/admin/ege/proposals` | Cria proposal |
| POST `/admin/ege/proposals/{id}/decide` | Decide proposal |
| POST `/admin/ege/pins/propose` | Cria pin proposal |
| POST `/admin/ege/pins/proposals/{id}/accept` | Aceita pin |
| POST `/admin/ege/pins/proposals/{id}/block` | Bloqueia pin |
| POST `/admin/mandates/proposals` | Cria mandate proposal |
| POST `/admin/mandates/proposals/{id}/decide` | Decide mandate |
| POST `/admin/institutions/{id}/admin-keys` | Cria key |
| POST `/admin/institutions/{id}/admin-keys/{id}/revoke` | Revoga key |
| POST `/pipeline/*` | Build/deploy operations |

---

## 3. Dados Necessários por Página

### 3.1 Página Home

```
GET /admin/institutions
→ Lista institutions: [{id, slug, name, created_at}]
```

### 3.2 Página Status

```
GET /health
→ {status, mode, reason_code?, details?}

GET /admin/institutions/{id}/config
→ {emergency_freeze, safe_mode_enabled, pinned_*, ...}

GET /admin/ege/pins/status (X-Institution-Id: {id})
→ {pinned: {...}, observed: {...}, drift_status: "CLEAR"|"ACTIVE"|"UNPINNED"}

GET /admin/mandates/effective?dept_id=X (X-Institution-Id: {id})
→ {mandates: [...], source: "governed"|"bundle"|"merged"}
```

### 3.3 Página Bundles

```
GET /pipeline/build/runs
→ {runs: [{run_id, bundle_name, created_at, ...}], total}

GET /pipeline/build/runs/{run_id}
→ {run_id, trace: {sir_sha256, bundle_manifest_sha256, ...}}

GET /admin/ege/pins/status
→ {pinned: {...}, observed: {...}}
```

### 3.4 Página Legacy

```
// TBD - Etapa 2.7 Legacy Bridge endpoints
// Não existem ainda endpoints read-only para legacy assets
// Ver gaps.md para detalhes
```

---

## 4. Autenticação

### Fluxo Proposto

1. Console solicita X-Admin-Key via form login
2. Key armazenada em sessionStorage (não persiste)
3. HTMX envia header em todas as requests:
   ```html
   <body hx-headers='{"X-Admin-Key": "..."}'>
   ```

### Alternativa: Cookie Session

1. POST `/console/login` com X-Admin-Key
2. API valida e retorna Set-Cookie com session token
3. Requests subsequentes autenticam via cookie
4. Mais seguro (key não exposta em JS)

**Recomendação:** Implementar cookie session para MVP.

---

## 5. Conclusão

**Todos os endpoints necessários já existem.** O console pode ser implementado 100% com chamadas aos endpoints admin existentes. Nenhuma nova API precisa ser criada para as páginas Home, Status e Bundles.

A única lacuna é a página Legacy, que depende de endpoints do Etapa 2.7 que podem ainda não estar expostos via API REST.
