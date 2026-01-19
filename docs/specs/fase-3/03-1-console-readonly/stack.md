# AXIOM Console - Stack Decision

**Data:** 2026-01-18
**Tipo:** Decisão de stack para PROMPT 3.1.1
**Status:** IMPLEMENTADO (PROMPT 3.1.2)

---

## Resumo Executivo

Opção recomendada: **Opção A - FastAPI + Jinja2 + HTMX**

---

## 1. Opções Avaliadas

### Opção A: UI Servida por FastAPI (Jinja2 + HTMX)

**Descrição:** Console HTML/CSS servido diretamente pela API FastAPI existente, usando templates Jinja2 e HTMX para interatividade.

**Prós:**
- Zero infraestrutura adicional (não requer Node.js, npm, build pipeline)
- Deploy único (API + Console no mesmo container)
- Mesma autenticação (X-Admin-Key headers reutilizados)
- Latência mínima (no API calls, templates renderizados server-side)
- HTMX provê interatividade sem SPA complexity
- Alinhado com filosofia "minimal console" do spec

**Contras:**
- UI limitada comparada a React/Vue
- Menos reusabilidade de componentes
- Curva de aprendizado HTMX para devs React

**Esforço estimado:** ~2-3 dias para MVP

### Opção B: React/Vite Separado

**Descrição:** SPA React com Vite, servido separadamente ou como static assets.

**Prós:**
- UI mais rica e interativa
- Ecossistema React maduro
- Componentes reutilizáveis
- TypeScript support nativo

**Contras:**
- Infraestrutura adicional (Node.js, npm, build pipeline)
- Dois processos/containers (API + UI)
- CORS configuration necessária
- Maior complexidade de deploy
- Maior bundle size
- Overkill para console read-only minimal

**Esforço estimado:** ~5-7 dias para MVP

---

## 2. Decisão

**Recomendação: Opção A (FastAPI + Jinja2 + HTMX)**

### Justificativas

1. **Alinhamento com spec.md:**
   > "Console cannot offer mutable operations"

   Um console read-only não precisa da interatividade complexa de um SPA.

2. **Escopo minimal:**
   - 4 páginas apenas (Home, Status, Bundles, Legacy)
   - Operações read-only
   - Sem formulários complexos

3. **Reuso de infraestrutura:**
   - FastAPI já serve /health, /docs
   - Autenticação admin já implementada
   - Deploy existente não precisa de alteração

4. **HTMX é suficiente:**
   - Polling automático para status updates
   - Tabs e navegação sem page reload
   - Partial updates para listas

5. **Coerência com projeto:**
   - Código Python (equipe já domina)
   - Sem dependências npm/Node.js
   - Menor superfície de manutenção

---

## 3. Arquitetura Proposta

```
src/engine/
├── api/
│   └── console.py           # Routes for console pages
└── console/
    ├── templates/           # Jinja2 templates
    │   ├── base.html        # Layout comum
    │   ├── home.html        # Seleção institution/dept
    │   ├── status.html      # Runtime status
    │   ├── bundles.html     # Releases/pins
    │   └── legacy.html      # Legacy assets (etapa 2.7)
    └── static/              # CSS, JS
        ├── style.css        # CSS custom + Tailwind CDN
        └── htmx.min.js      # HTMX (CDN backup)
```

### Dependências

```toml
# pyproject.toml
jinja2 = "^3.1"  # Já incluído via FastAPI
aiofiles = "^23.0"  # Para servir static files
```

### Rotas

| Rota | Descrição |
|------|-----------|
| `GET /console/` | Home - seleção de institution |
| `GET /console/status` | Status runtime (ACTIVE/SAFE_MODE, drift) |
| `GET /console/bundles` | Releases e pins |
| `GET /console/legacy` | Legacy assets (read-only) |

### Autenticação

- Usa mesmos headers: `X-Admin-Key` ou `X-Admin-Token`
- Alternativa: Cookie-based session para UX melhor (opcional)

---

## 4. Dependências HTMX

```html
<!-- CDN (primary) -->
<script src="https://unpkg.com/htmx.org@1.9.10"></script>

<!-- Fallback local -->
<script src="/console/static/htmx.min.js"></script>
```

**Features HTMX usados:**
- `hx-get`: Fetch e replace HTML
- `hx-trigger="every 5s"`: Polling automático para status
- `hx-target`: Update parcial de elementos
- `hx-swap`: innerHTML, outerHTML
- `hx-headers`: Enviar X-Admin-Key automaticamente

---

## 5. Implementação (PROMPT 3.1.2)

### Arquivos Criados

```
src/engine/console/
├── __init__.py              # Módulo
├── routes.py                # Rotas FastAPI (4 páginas + static + partials)
├── templates/
│   ├── base.html            # Layout comum com nav
│   ├── home.html            # Seleção institution/dept
│   ├── status.html          # Runtime status, drift, config, mandates
│   ├── bundles.html         # Pins, builds, proposals
│   └── legacy.html          # Legacy assets (placeholder)
└── static/
    └── style.css            # CSS dark theme

tests/
└── test_console.py          # 20 testes (auth, pages, read-only, freeze bypass)
```

### Rotas Implementadas

| Rota | Descrição | Auth |
|------|-----------|------|
| `GET /console/` | Home - seleção de institution | X-Admin-Token |
| `GET /console/status?institution_id=X` | Status runtime | X-Admin-Token |
| `GET /console/bundles?institution_id=X` | Releases e pins | X-Admin-Token |
| `GET /console/legacy?institution_id=X` | Legacy assets | X-Admin-Token |
| `GET /console/static/{path}` | Static files (CSS) | None |
| `GET /console/partials/status` | HTMX polling | X-Admin-Token |

### Modificações em server.py

- Import: `from engine.console.routes import router as console_router`
- Router: `app.include_router(console_router)`
- Bypass: Console paths bypass freeze/emergency checks (read-only visibility)

### Testes

- 20 testes passando
- Cobertura: auth, HTML rendering, runtime mode display, read-only enforcement, freeze bypass

---

## 6. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| HTMX não atende requisitos futuros | Migrar para React se necessário (APIs já existem) |
| Performance com muitos items | Paginação server-side (já implementada nas APIs) |
| UX limitada | Scope é read-only; para operações usar CLI ou curl |
