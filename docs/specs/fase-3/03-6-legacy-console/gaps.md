# 03-6 Legacy Console - Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Resumo

Análise de gaps entre a spec.md e a implementação atual do console para Legacy Bridge.

## Estado Atual

### Módulo `legacy_bridge` (Backend)

O módulo `engine.legacy_bridge` já implementa:

| Componente | Status | Descrição |
|------------|--------|-----------|
| `LegacyBridgeRegistry` | ✅ Existe | Classe com `register()`, `list_assets()`, `get_asset()`, `get_last_snapshot()` |
| `verify_asset()` | ✅ Existe | Função que verifica integridade de um asset |
| `verify_all_assets()` | ✅ Existe | Função que verifica todos os assets |
| `LegacyAsset` | ✅ Existe | Modelo dataclass com metadata do asset |
| `LegacyAssetSnapshot` | ✅ Existe | Modelo dataclass para snapshots verificados |
| `VerifyResult` | ✅ Existe | Dataclass com resultado de verificação |

### Console (`/console/legacy`)

| Componente | Status | Descrição |
|------------|--------|-----------|
| Rota `GET /console/legacy` | ✅ Implementado | Lista assets via `LegacyBridgeRegistry.list_assets()` |
| Rota `GET /console/legacy/{asset_id}` | ✅ Implementado | Detalhe do asset com snapshot |
| Rota `POST /console/legacy/{asset_id}/verify` | ✅ Implementado | Executa verify e redireciona |
| Template `legacy.html` | ✅ Implementado | Lista com badges e links para detalhe |
| Template `legacy_detail.html` | ✅ Implementado | Detalhe com verify button |
| `_get_legacy_assets_info()` | ✅ Implementado | Integrado com `LegacyBridgeRegistry` |

## Gaps Resolvidos

### GAP-1: Helper não integrado com legacy_bridge

**Status:** ✅ RESOLVIDO

**Implementação:** `routes.py:231-256`

```python
def _get_legacy_assets_info(institution_id: str, dept_id: Optional[str]) -> Dict[str, Any]:
    try:
        registry = LegacyBridgeRegistry(institution_id, dept_id)
        assets = registry.list_assets()
        return {
            "assets": assets,
            "bridge_available": True,
            "total_assets": len(assets),
        }
    except Exception:
        return {"assets": [], "bridge_available": False, "total_assets": 0}
```

---

### GAP-2: Falta rota de detalhe de asset

**Status:** ✅ RESOLVIDO

**Implementação:** `routes.py:728-787`
- Rota `GET /console/legacy/{asset_id}`
- Renderiza `legacy_detail.html`
- Retorna 404 se asset não existe

---

### GAP-3: Falta rota de verificação (POST)

**Status:** ✅ RESOLVIDO

**Implementação:** `routes.py:790-829`
- Rota `POST /console/legacy/{asset_id}/verify`
- Chama `legacy_verify_asset()`
- Redireciona com `verify_result` (303 See Other)

---

### GAP-4: Falta template de detalhe

**Status:** ✅ RESOLVIDO

**Implementação:** `templates/legacy_detail.html`
- Metadata do asset (asset_id, name, source_location, etc.)
- Último snapshot (sha256, verified_at)
- Resultado de verificação (MATCH/DRIFT_DETECTED/MISSING)
- Botão "Verify Now" com POST form

---

### GAP-5: Falta mapeamento de status para badges

**Status:** ✅ RESOLVIDO

**Implementação:** `templates/legacy.html`

| AssetStatus | Badge Class | Label |
|-------------|-------------|-------|
| `active` | `badge-active` | Active |
| `drift_detected` | `badge-error` | Drift |
| `missing` | `badge-safe-mode` | Missing |
| outros | `badge-unpinned` | (valor) |

## Testes Implementados

| Test Class | Count | Description |
|------------|-------|-------------|
| `TestConsoleLegacyAuth` | 3 | Auth tests (list, detail, verify) |
| `TestConsoleLegacyList` | 3 | List page tests |
| `TestConsoleLegacyDetail` | 2 | Detail page tests |
| `TestConsoleLegacyVerify` | 2 | Verify redirect tests |
| `TestConsoleLegacyWithAsset` | 7 | Tests with registered asset (MATCH, DRIFT, MISSING) |
| `TestConsoleLegacyPostRouteAllowed` | 1 | Route accessibility test |
| **Total** | **18** | Novos testes para Etapa 3.6 |

## Definition of Done

- [x] Operador consegue ver assets via `/console/legacy`
- [x] Operador consegue ver detalhe via `/console/legacy/{asset_id}`
- [x] Operador consegue rodar verify via POST
- [x] Verify detecta drift e missing
- [x] Testes cobrem auth e drift
- [x] Documentação atualizada
