# Offline Proof Verification: Gaps & Decisions

**Etapa 2.3 — PROMPT 2.3.2 Implementação**
**Data**: 2026-01-18
**Status**: ✅ IMPLEMENTADO

---

## 1. Status de Implementação

| Gap | Status | Resolução |
|-----|--------|-----------|
| Gap 1: Módulo `engine.proof` | ✅ Fechado | Criado `src/engine/proof/` |
| Gap 2: CLI para prova offline | ✅ Fechado | `python -m engine.proof verify` |
| Gap 3: Verificação manifest_hash | ✅ Fechado | Implementado + corrigido ISE compiler |
| Gap 4: Cross-check manifest ↔ ledger | ✅ Fechado | Verificação bidirecional |
| Gap 5: Validação source_idl_sha256 | ✅ Fechado | Validação 64-char hex |
| Gap 6: Testes de prova offline | ✅ Fechado | 32 testes em `test_offline_proof.py` |
| Gap 7: Segurança path traversal | ✅ Fechado | Proteção anti-traversal |

---

## 2. Correção Importante: manifest_hash

Durante a implementação, foi identificado que o ISE compiler usava `bundle_hash` (hash of contract hashes) como `manifest_hash` no ledger, divergindo da spec que define:

> `manifest_hash` (SHA256 do manifest)

**Correção aplicada**: `src/engine/ise/compiler.py` foi modificado em 4 locais para usar `SHA256(manifest_json)` como `manifest_hash`, conforme a spec.

---

## 3. Código Existente Reutilizado

| Módulo | Função | Uso |
|--------|--------|-----|
| `engine.loader.verify_hashes` | `compute_sha256()` | ✅ Hash de arquivos |
| `engine.loader.verify_hashes` | `normalize_hash()` | ✅ Remove `SHA256:` prefix |

---

## 4. Arquivos Criados

```
src/engine/proof/
├── __init__.py        # ~40 LOC - Exports públicos
├── errors.py          # ~30 LOC - Códigos PROOF_*
├── verify.py          # ~280 LOC - verify_bundle_offline()
└── __main__.py        # ~70 LOC - CLI

tests/test_offline_proof.py  # ~350 LOC - 32 testes
```

---

## 5. Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/engine/ise/compiler.py` | Corrigido `manifest_hash` em 4 funções de compilação |

---

## 6. Códigos de Erro Implementados

| Código | Descrição |
|--------|-----------|
| `PROOF_MANIFEST_MISSING` | bundle.manifest.json não encontrado |
| `PROOF_MANIFEST_INVALID_JSON` | JSON inválido no manifest |
| `PROOF_MANIFEST_INVALID_SCHEMA` | Schema inválido (falta contracts[]) |
| `PROOF_CONTRACT_MISSING` | Contrato required ausente |
| `PROOF_CONTRACT_HASH_MISMATCH` | Hash do contrato não bate |
| `PROOF_CONTRACT_HASH_INVALID_FORMAT` | Hash não é SHA256 válido |
| `PROOF_PATH_TRAVERSAL` | Tentativa de path traversal |
| `PROOF_LEDGER_MISSING` | contract_ledger.json não encontrado |
| `PROOF_LEDGER_INVALID_JSON` | JSON inválido no ledger |
| `PROOF_LEDGER_INVALID_SCHEMA` | Schema inválido |
| `PROOF_LEDGER_MANIFEST_HASH_MISMATCH` | manifest_hash não bate |
| `PROOF_LEDGER_MANIFEST_HASH_INVALID` | manifest_hash formato inválido |
| `PROOF_LEDGER_CONTRACT_MISSING` | Contrato do manifest ausente no ledger |
| `PROOF_LEDGER_CONTRACT_EXTRA` | Contrato extra no ledger |
| `PROOF_LEDGER_CONTRACT_HASH_MISMATCH` | Hash diverge entre manifest e ledger |
| `PROOF_SOURCE_IDL_MISSING` | source_idl_sha256 ausente |
| `PROOF_SOURCE_IDL_INVALID_FORMAT` | source_idl_sha256 formato inválido |

---

## 7. Testes

### 7.1 Cobertura

| Categoria | Testes | Status |
|-----------|--------|--------|
| Helper `is_valid_sha256_hex` | 9 | ✅ |
| PASS cases | 3 | ✅ |
| Manifest failures | 3 | ✅ |
| Contract failures | 4 | ✅ |
| Ledger failures | 6 | ✅ |
| source_idl_sha256 failures | 3 | ✅ |
| E2E pipeline | 1 | ✅ |
| CLI | 3 | ✅ |
| **Total** | **32** | ✅ |

### 7.2 Execução

```bash
cd /home/bazari/engine
PYTHONPATH=src python -m pytest tests/test_offline_proof.py -v
# Resultado: 32 passed
```

---

## 8. Decisões Implementadas

| # | Decisão | Implementação |
|---|---------|---------------|
| D1 | Módulo `engine.proof` separado | ✅ Criado |
| D2 | Reutilizar `verify_hashes.py` | ✅ Importa `compute_sha256`, `normalize_hash` |
| D3 | CLI `python -m engine.proof verify` | ✅ Implementado |
| D4 | Retornar `ProofResult` dataclass | ✅ Implementado |
| D5 | Códigos de erro `PROOF_*` | ✅ 17 códigos |
| D6 | Verificar manifest_hash no ledger | ✅ Implementado |
| D7 | Cross-check contracts manifest ↔ ledger | ✅ Bidirecional |
| D8 | Validar formato source_idl_sha256 | ✅ 64-char hex |
| D9 | Proteção path traversal | ✅ Implementado |
| D10 | Exit code 0/1 para CI | ✅ Implementado |
| D11 | Output JSON (`--json`) | ✅ Implementado |

---

## 9. Checklist de Implementação - COMPLETO

### Fase 1: Módulo Core ✅
- [x] Criar `src/engine/proof/__init__.py`
- [x] Criar `src/engine/proof/errors.py`
- [x] Criar `src/engine/proof/verify.py`
- [x] Implementar `verify_bundle_offline()`
- [x] Implementar `is_safe_path()` (anti-traversal)

### Fase 2: CLI ✅
- [x] Criar `src/engine/proof/__main__.py`
- [x] Implementar comando `verify`
- [x] Formatar output (human-readable)
- [x] Adicionar flag `--json`
- [x] Exit code 0/1

### Fase 3: Correção ISE ✅
- [x] Corrigir `compile_idl()` - usar SHA256(manifest)
- [x] Corrigir `compile_bundle_multi()` - usar SHA256(manifest)
- [x] Corrigir `_compile_single_mode()` - usar SHA256(manifest)
- [x] Corrigir `compile_from_ircs()` - usar SHA256(manifest)

### Fase 4: Testes ✅
- [x] Criar `tests/test_offline_proof.py`
- [x] Testes helper `is_valid_sha256_hex`
- [x] Testes PASS (bundle válido)
- [x] Testes FAIL manifest
- [x] Testes FAIL contracts
- [x] Testes FAIL ledger
- [x] Testes FAIL source_idl_sha256
- [x] Testes path traversal
- [x] Teste E2E pipeline
- [x] Testes CLI

### Fase 5: Documentação ✅
- [x] Atualizar `proof.md` com status implementado
- [x] Atualizar `gaps.md` fechando gaps

---

## 10. Definition of Done - ATINGIDO

- [x] Existe `python -m engine.proof verify <bundle_path>`
- [x] Verifica todos os hashes (contracts, manifest_hash)
- [x] Cross-check completo manifest ↔ ledger (1:1, sem extras)
- [x] Verifica source_idl_sha256 presente e válido (64-char hex)
- [x] Proteção anti path-traversal
- [x] Exit code 0 para PASS, 1 para FAIL
- [x] Output JSON para CI (`--json`)
- [x] Testes cobrem PASS e todos os FAILs (32 testes)
- [x] Documentação atualizada

---

## 11. Métricas Finais

| Métrica | Valor |
|---------|-------|
| Linhas de código (proof module) | ~420 LOC |
| Linhas de código (testes) | ~350 LOC |
| Testes adicionados | 32 |
| Códigos de erro | 17 |
| Arquivos criados | 5 |
| Arquivos modificados | 1 |
