# 03-6 Legacy Console - API Mapping

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Backend APIs Disponíveis

### `engine.legacy_bridge.registry.LegacyBridgeRegistry`

```python
class LegacyBridgeRegistry:
    def __init__(self, institution_id: str, dept_id: Optional[str] = None):
        """Inicializa registry para uma institution."""

    def register(
        self,
        asset_id: str,
        name: str,
        source_location: str,
        source_format: str = "raw",
        source_type: str = "file",
        description: Optional[str] = None,
        actor_id: str = "system",
    ) -> LegacyAsset:
        """Registra novo asset. Retorna LegacyAsset criado."""

    def list_assets(self) -> List[Dict[str, Any]]:
        """Lista assets com status atual. Retorna lista de summaries."""

    def get_asset(self, asset_id: str) -> Optional[LegacyAsset]:
        """Busca asset por ID. Retorna LegacyAsset ou None."""

    def get_last_snapshot(self, asset_id: str) -> Optional[LegacyAssetSnapshot]:
        """Busca último snapshot verificado. Retorna LegacyAssetSnapshot ou None."""

    def record_verification(...) -> LegacyAssetSnapshot:
        """Registra resultado de verificação."""

    def record_missing(self, asset_id: str, error: str, actor_id: str = "system") -> None:
        """Marca asset como MISSING (source não encontrado)."""
```

### `engine.legacy_bridge.verify`

```python
@dataclass
class VerifyResult:
    asset_id: str
    name: str
    status: str              # "MATCH" | "DRIFT_DETECTED" | "MISSING" | "ERROR"
    expected_sha256: str
    observed_sha256: str
    drift_detected: bool
    drift_type: Optional[str] = None
    error: Optional[str] = None

def verify_asset(
    institution_id: str,
    asset_id: str,
    dept_id: Optional[str] = None,
    actor_id: str = "system",
) -> VerifyResult:
    """
    Verifica integridade de um asset (read-only no source).

    Retorna:
        VerifyResult com status:
        - MATCH: sha256 confere com último snapshot
        - DRIFT_DETECTED: sha256 diferente do esperado
        - MISSING: source não encontrado
        - ERROR: asset não existe
    """

def verify_all_assets(...) -> VerifyAllResult:
    """Verifica todos os assets de uma institution/dept."""
```

## Console Routes Implementadas

### `GET /console/legacy`

**Status:** ✅ IMPLEMENTADO

**Localização:** `routes.py:683-725`

**Parâmetros:**
- `institution_id` (query, required): UUID da instituição
- `dept_id` (query, optional): ID do departamento
- `X-Admin-Token` (header, required): Token de admin

**Resposta:** HTML com lista de assets

**Helper:**
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

### `GET /console/legacy/{asset_id}`

**Status:** ✅ IMPLEMENTADO

**Localização:** `routes.py:728-787`

**Parâmetros:**
- `asset_id` (path, required): ID do asset
- `institution_id` (query, required): UUID da instituição
- `dept_id` (query, optional): ID do departamento
- `verify_result` (query, optional): Resultado de verify anterior
- `X-Admin-Token` (header, required): Token de admin

**Resposta:** HTML com detalhes do asset ou 404

**Template context:**
```python
{
    "asset": LegacyAsset,
    "last_snapshot": LegacyAssetSnapshot | None,
    "verify_result": str | None,  # "MATCH" | "DRIFT_DETECTED" | "MISSING" | ...
}
```

### `POST /console/legacy/{asset_id}/verify`

**Status:** ✅ IMPLEMENTADO

**Localização:** `routes.py:790-829`

**Parâmetros:**
- `asset_id` (path, required): ID do asset
- `institution_id` (form, required): UUID da instituição
- `dept_id` (form, optional): ID do departamento
- `X-Admin-Token` (header, required): Token de admin

**Comportamento:**
1. Chama `legacy_verify_asset(institution_id, asset_id, dept_id, actor_id="console")`
2. Redireciona para `GET /console/legacy/{asset_id}` com `verify_result`

**Redirect:**
```python
RedirectResponse(
    url=f"/console/legacy/{asset_id}?institution_id={institution_id}&verify_result={status}",
    status_code=303,
)
```

## Templates Implementados

### `legacy.html`

Lista de assets com:
- Tabela: Asset ID, Name, Status (badge), Last Verified, Action (View link)
- Badges: active (green), drift_detected (red), missing (yellow)
- Bridge status card
- Empty state quando sem assets

### `legacy_detail.html`

Detalhe do asset com:
- Verify result banner (success/drift/missing)
- Asset metadata (id, name, source_location, source_type, source_format)
- Last snapshot info (sha256, size, lines, verified_at)
- "Verify Now" button (POST form)
- Back link para lista

## Mapeamento de Status para Badges

| Status Value | Badge Class | Label |
|-------------|-------------|-------|
| `active` | `badge-active` | Active |
| `drift_detected` | `badge-error` | Drift |
| `missing` | `badge-safe-mode` | Missing |
| outros | `badge-unpinned` | (valor) |

## Testes Implementados

| Test | Status | Description |
|------|--------|-------------|
| `test_legacy_list_requires_admin_token` | ✅ | Auth test |
| `test_legacy_detail_requires_admin_token` | ✅ | Auth test |
| `test_legacy_verify_requires_admin_token` | ✅ | Auth test |
| `test_legacy_list_returns_html` | ✅ | List page |
| `test_legacy_list_shows_bridge_available` | ✅ | List page |
| `test_legacy_list_shows_empty_state` | ✅ | List page |
| `test_legacy_detail_asset_not_found` | ✅ | Detail 404 |
| `test_legacy_detail_requires_institution_id` | ✅ | Detail 422 |
| `test_legacy_verify_redirects` | ✅ | Verify redirect |
| `test_legacy_verify_preserves_dept_id` | ✅ | Verify redirect |
| `test_legacy_list_shows_registered_asset` | ✅ | With asset |
| `test_legacy_detail_shows_asset` | ✅ | With asset |
| `test_legacy_verify_match` | ✅ | MATCH result |
| `test_legacy_verify_drift_detected` | ✅ | DRIFT result |
| `test_legacy_verify_missing` | ✅ | MISSING result |
| `test_legacy_detail_shows_verify_result_match` | ✅ | UI feedback |
| `test_legacy_detail_shows_verify_result_drift` | ✅ | UI feedback |
| `test_legacy_verify_post_route_allowed` | ✅ | Route accessibility |
