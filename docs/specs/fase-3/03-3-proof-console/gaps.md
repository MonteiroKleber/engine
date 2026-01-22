# Gaps — Etapa 3.3: Proof Console (UX + Export)

**Data:** 2026-01-19
**Status:** TODOS OS GAPS RESOLVIDOS (PROMPT 3.3.2)
**Prompt inicial:** 3.3.1 (Diagnóstico)

## Resumo

| Gap | Severidade | Status |
|-----|------------|--------|
| GAP-01: Tabela de checks não existe | Alto | RESOLVIDO |
| GAP-02: Lista de divergências com links | Alto | RESOLVIDO |
| GAP-03: Export JSON como download | Médio | RESOLVIDO |
| GAP-04: pinned_release_id não exibido | Baixo | RESOLVIDO |

---

## GAP-01: Tabela de checks - RESOLVIDO

### Solução Implementada

Criada função `_generate_proof_checks()` em `routes.py:394-476`:
- Gera lista de 8 checks baseado no ProofResult
- Cada check: `{name, status, detail}` com status pass/fail/skip
- Checks: Manifest exists, Manifest valid JSON, Manifest schema valid, Contracts hashes, Ledger exists, Ledger manifest_hash, Ledger contracts 1:1, source_idl_sha256

Template `proof.html` atualizado com tabela de verificações:
- Badges coloridos: PASS (verde), FAIL (vermelho), SKIP (cinza)
- Coluna de detalhe para informações adicionais

---

## GAP-02: Lista de divergências com links - RESOLVIDO

### Solução Implementada

Template `proof.html` melhorado para mostrar:
- "Affected File" com link clicável para `/console/contracts/{file}`
- "Expected Hash" e "Actual Hash" lado a lado
- Links funcionam com parâmetros institution_id e dept_id

---

## GAP-03: Export JSON como download - RESOLVIDO

### Solução Implementada

Nova rota `GET /console/proof.json` em `routes.py:1031-1096`:
- Retorna `JSONResponse` com `Content-Disposition: attachment`
- Filename: `proof-{institution_id[:8]}.json`
- Inclui metadata adicional: institution_id, dept_id, bundle_path

Template `proof.html` atualizado:
- Botão "Download JSON Report" no card Export
- Link direto para `/console/proof.json`

---

## GAP-04: pinned_release_id não exibido - RESOLVIDO

### Solução Implementada

Handler `console_proof` busca config via `_get_institution_config_info()`:
```python
config = _get_institution_config_info(institution_id)
pinned_release_id = config.get("pinned_release_id")
```

Template `proof.html` exibe na seção "Cryptographic Anchors":
- Pinned Release ID (se disponível)
- Manifest SHA256
- source_idl_sha256
- Bundle Path

---

## Checklist de Implementação

- [x] GAP-01: Adicionar tabela de checks ao template
- [x] GAP-02: Renderizar divergências com links para contracts
- [x] GAP-03: Criar endpoint para export JSON download
- [x] GAP-04: Exibir pinned_release_id nas âncoras
- [x] Testes: PASS mostra checks, FAIL mostra links, export JSON funciona

---

## Arquivos Criados/Modificados (PROMPT 3.3.2)

**Modificados:**
- `src/engine/console/routes.py` — +160 linhas
  - Helper `_generate_proof_checks()` (linhas 394-476)
  - Handler `console_proof` atualizado (linhas 928-1028)
  - Nova rota `GET /console/proof.json` (linhas 1031-1096)
- `src/engine/console/templates/proof.html` — reescrito com UX melhorada
- `tests/test_console.py` — +12 testes (55 total)

---

## Testes Adicionados

| Classe | Testes | Cobertura |
|--------|--------|-----------|
| TestConsoleProofChecksTable | 3 | Tabela de checks, PASS badges, FAIL badges |
| TestConsoleProofFailureLinks | 2 | Link para arquivo, hashes expected/actual |
| TestConsoleProofJsonExport | 6 | Auth, required params, content type, download header, result fields, failure |
| TestConsoleProofExportLink | 1 | Link de download na página |

**Total:** 12 novos testes, 55 total passando.

---

## Definition of Done

- [x] Auditor consegue abrir o console, rodar prova e ver tabela de checks
- [x] Auditor consegue ver link para contract afetado em caso de falha
- [x] Auditor consegue exportar report JSON com download
- [x] Âncoras incluem pinned_release_id, manifest_hash, source_idl_sha256
