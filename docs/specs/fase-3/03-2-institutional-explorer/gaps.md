# Gaps — Etapa 3.2: Institutional Explorer

**Data:** 2026-01-18
**Status:** TODOS OS GAPS RESOLVIDOS (PROMPT 3.2.2)
**Prompt inicial:** 3.2.1 (Diagnóstico)

## Resumo

| Gap | Severidade | Status |
|-----|------------|--------|
| GAP-01: Rota contracts não existe | Alto | RESOLVIDO |
| GAP-02: Rota proof não existe | Alto | RESOLVIDO |
| GAP-03: Bundle path por institution inconsistente | Médio | RESOLVIDO |
| GAP-04: Anti path-traversal não reutilizável | Baixo | RESOLVIDO |

---

## GAP-01: Rotas /console/contracts - RESOLVIDO

### Solução Implementada

Criadas em `engine/console/routes.py`:
- `GET /console/contracts` — lista contracts do bundle
- `GET /console/contracts/{file}` — conteúdo de um contract específico

Templates criados:
- `contracts.html` — lista manifest, ledger, contracts
- `contract_detail.html` — conteúdo + hash verification

---

## GAP-02: Rota /console/proof - RESOLVIDO

### Solução Implementada

Criada em `engine/console/routes.py`:
- `GET /console/proof` — executa verify offline

Template criado:
- `proof.html` — mostra PASS/FAIL + anchors + optional JSON

---

## GAP-03: Bundle path por institution - RESOLVIDO

### Solução Implementada

Helper `_get_bundle_path_for_institution()` em `routes.py`:
1. Tenta resolver CURRENT symlink em `var/institutions/<id>/bundles/`
2. Fallback para global `ENGINE_BUNDLE_PATH`
3. Retorna None se não encontrar

---

## GAP-04: is_safe_path export - RESOLVIDO

### Solução Implementada

Exportado em `engine/proof/__init__.py`:
```python
from .verify import verify_bundle_offline, is_safe_path, ProofResult
```

Adicionado a `__all__`:
```python
__all__ = [
    "is_safe_path",
    ...
]
```

---

## Checklist de Implementação

- [x] GAP-01: Criar `GET /console/contracts`
- [x] GAP-01: Criar `GET /console/contracts/{file}`
- [x] GAP-02: Criar `GET /console/proof`
- [x] GAP-03: Helper `_get_bundle_path_for_institution()`
- [x] GAP-04: Exportar `is_safe_path()` reutilizável
- [x] Templates: `contracts.html`, `contract_detail.html`, `proof.html`
- [x] Testes: auth, read-only, path traversal, hash verification

---

## Arquivos Criados/Modificados (PROMPT 3.2.2)

**Criados:**
- `src/engine/console/templates/contracts.html`
- `src/engine/console/templates/contract_detail.html`
- `src/engine/console/templates/proof.html`

**Modificados:**
- `src/engine/console/routes.py` — +280 linhas (helpers + 3 rotas)
- `src/engine/console/templates/base.html` — nav links para Contracts e Proof
- `src/engine/console/static/style.css` — +50 linhas (.code-block, .btn-link, details)
- `src/engine/proof/__init__.py` — export is_safe_path
- `tests/test_console.py` — +23 testes (43 total)

---

## Testes Adicionados

| Classe | Testes | Cobertura |
|--------|--------|-----------|
| TestConsoleContractsAuth | 3 | Auth para contracts/proof |
| TestConsoleContractsPage | 4 | Listing, manifest, contracts |
| TestConsoleContractDetail | 4 | Content, hash, match, 404 |
| TestConsolePathTraversal | 4 | .., encoded, absolute, valid |
| TestConsoleProofPage | 5 | HTML, PASS, count, JSON |
| TestConsoleProofFailure | 2 | Missing manifest, hash mismatch |
| TestConsoleExplorerReadOnly | 1 | GET only |

**Total:** 23 novos testes, 43 total passando.
