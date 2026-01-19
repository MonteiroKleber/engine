# AXIOM Console - Gaps Analysis

**Data:** 2026-01-18
**Tipo:** Análise de gaps para PROMPT 3.1.1
**Status:** IMPLEMENTADO (PROMPT 3.1.2)

---

## Resumo Executivo

| Área | Status | Gaps |
|------|--------|------|
| APIs Read-Only | ✅ 100% | Todas APIs utilizadas |
| Templates/UI | ✅ 100% | 4 páginas + base template |
| Autenticação Console | ✅ OK | X-Admin-Token header |
| Legacy Bridge | ⚠️ Placeholder | Assets não exibidos (future) |

### Implementação Completa

- **4 páginas HTML** (Home, Status, Bundles, Legacy)
- **20 testes** passando
- **0 endpoints JSON novos** (reutiliza APIs existentes)
- **Freeze bypass** para visibilidade durante emergências

---

## 1. APIs - Gaps Identificados

### 1.1 ✅ DISPONÍVEL: Institutions

- `GET /admin/institutions` - Lista
- `GET /admin/institutions/{id}` - Detalhe
- `GET /admin/institutions/by-slug/{slug}` - Por slug

**Status:** 100% pronto

---

### 1.2 ✅ DISPONÍVEL: Institution Config

- `GET /admin/institutions/{id}/config` - Config atual
- `GET /admin/institutions/{id}/config/history` - Histórico

**Status:** 100% pronto

---

### 1.3 ✅ DISPONÍVEL: EGE Drift & Pins

- `GET /admin/ege/proposals` - Lista proposals
- `GET /admin/ege/pins/status` - Status pins

**Status:** 100% pronto

---

### 1.4 ✅ DISPONÍVEL: Governed Mandates

- `GET /admin/mandates/proposals` - Lista proposals
- `GET /admin/mandates/governed` - Mandatos governados
- `GET /admin/mandates/effective` - Mandatos efetivos

**Status:** 100% pronto

---

### 1.5 ✅ DISPONÍVEL: Pipeline/Bundles

- `GET /pipeline/build/runs` - Lista runs
- `GET /pipeline/build/runs/{run_id}` - Detalhe + trace
- `GET /pipeline/build/diff` - Diff entre runs

**Status:** 100% pronto

---

### 1.6 ✅ DISPONÍVEL: Health

- `GET /health` - Status runtime

**Status:** 100% pronto

---

### 1.7 ⚠️ GAP: Departments List

**Problema:** Não existe endpoint para listar departments disponíveis para uma institution/bundle.

**Impacto:** Página Home precisa mostrar dropdown de departments.

**Solução proposta:**
```python
GET /admin/institutions/{id}/departments
→ ["finance", "support", "hr", ...]
```

**Complexidade:** Baixa - leitura do bundle manifest já carregado.

**Workaround MVP:** Hardcode departments conhecidos ou ler do bundle_manifest.json diretamente.

---

### 1.8 ⚠️ GAP: Legacy Assets Read-Only

**Problema:** Etapa 2.7 (Legacy Bridge) implementou a ponte read-only para sistemas legados, mas não há endpoints REST documentados para listar/visualizar legacy assets.

**Impacto:** Página Legacy do console não pode ser implementada sem estes endpoints.

**Solução proposta:**
```python
GET /admin/legacy/assets
→ [{asset_id, type, name, last_sync, status}]

GET /admin/legacy/assets/{asset_id}
→ {asset_id, data: {...}, metadata: {...}}
```

**Complexidade:** Média - depende de como legacy bridge foi implementado.

**Workaround MVP:** Omitir página Legacy até Etapa 3.2 ou posterior.

---

## 2. Templates/UI - Gaps

### 2.1 ❌ GAP: Estrutura de Templates

**Status:** Não existe nenhum template Jinja2 no projeto.

**Necessário criar:**
```
src/engine/console/
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── status.html
│   ├── bundles.html
│   └── legacy.html
└── static/
    ├── style.css
    └── htmx.min.js
```

**Complexidade:** Média

---

### 2.2 ❌ GAP: Rotas Console

**Status:** Não existe nenhuma rota /console/* no servidor.

**Necessário criar:**
```python
# src/engine/api/console.py
router = APIRouter(prefix="/console")

@router.get("/")
async def console_home(): ...

@router.get("/status")
async def console_status(): ...

@router.get("/bundles")
async def console_bundles(): ...
```

**Complexidade:** Baixa

---

### 2.3 ❌ GAP: Static Files

**Status:** Servidor não está configurado para servir arquivos estáticos.

**Necessário:**
```python
from fastapi.staticfiles import StaticFiles
app.mount("/console/static", StaticFiles(directory="console/static"))
```

**Complexidade:** Baixa

---

## 3. Autenticação - Gaps

### 3.1 ⚠️ GAP: Session Management para Console

**Problema:** APIs admin usam X-Admin-Key header. Console web precisa de session management para não expor key em JavaScript.

**Impacto:** Sem session, key fica visível no browser (inseguro).

**Solução proposta:**
```python
POST /console/login
Body: {admin_key: "..."}
Response: Set-Cookie: session=<jwt>; HttpOnly; Secure

# Middleware verifica cookie e extrai institution_id
```

**Complexidade:** Média

**Workaround MVP:** Aceitar X-Admin-Key em header (usuário digita manualmente) - menos seguro mas funcional.

---

## 4. Plano de Implementação Mínimo

### Fase 1: Estrutura Base (PROMPT 3.1.2)

1. Criar `src/engine/console/` com templates e static
2. Criar `src/engine/api/console.py` com rotas
3. Configurar static files no server.py
4. Template base.html com layout + HTMX

**Entregável:** Console renderiza páginas vazias com navegação.

---

### Fase 2: Página Home (PROMPT 3.1.3)

1. Listar institutions via `GET /admin/institutions`
2. Form de seleção de institution + dept
3. Persistir seleção em session/cookie

**Entregável:** Usuário pode selecionar institution.

---

### Fase 3: Página Status (PROMPT 3.1.4)

1. Exibir `/health` (ACTIVE/SAFE_MODE)
2. Exibir `/admin/ege/pins/status` (drift)
3. Exibir `/admin/institutions/{id}/config` (freeze, safe_mode)
4. Polling automático via HTMX (every 5s)

**Entregável:** Dashboard de status operacional.

---

### Fase 4: Página Bundles (PROMPT 3.1.5)

1. Listar `/pipeline/build/runs`
2. Mostrar trace.json com hashes
3. Exibir pinned vs observed

**Entregável:** Visualização de releases e pins.

---

### Fase 5: Página Legacy (PROMPT 3.2+)

**Dependência:** Endpoints legacy assets (ver gap 1.8)

1. Criar endpoints GET /admin/legacy/*
2. Template para listar/visualizar assets

**Entregável:** Visualização de assets legados.

---

## 5. Resumo de Gaps

| ID | Gap | Prioridade | Complexidade | Workaround |
|----|-----|------------|--------------|------------|
| G1 | Departments list endpoint | Baixa | Baixa | Hardcode |
| G2 | Legacy assets endpoints | Média | Média | Omitir página |
| G3 | Templates Jinja2 | Alta | Média | N/A |
| G4 | Rotas /console/* | Alta | Baixa | N/A |
| G5 | Static files config | Alta | Baixa | N/A |
| G6 | Session management | Média | Média | Header manual |

---

## 6. Conclusão

O console read-only pode ser implementado com **esforço mínimo**:

1. **APIs:** 95% prontas - apenas 2 gaps menores (departments, legacy)
2. **Templates:** 0% - precisa criar estrutura completa
3. **Autenticação:** Funcional com workaround (header manual)

**Recomendação:** Iniciar implementação em PROMPT 3.1.2 com:
- Templates base + rotas
- Página Home + Status como MVP
- Página Bundles em sequência
- Página Legacy adiada para Fase 3.2
