"""Admin Institution Config API endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from engine.ise.release import verify_admin_token
from engine.ise import errors as ise_errors
from engine.core.institution_context import DEFAULT_INSTITUTION_ID
from engine.core.institution_config import (
    get_effective_config,
    save_active_config,
    get_config_history,
    invalidate_config_cache,
    InstitutionConfig,
    CONFIG_SCHEMA_VERSION,
)
from engine.core.errors import (
    INSTITUTION_CONFIG_INVALID,
    INSTITUTION_CONFIG_UNAVAILABLE,
    INSTITUTION_CONFIG_HISTORY_UNAVAILABLE,
    INSTITUTION_NOT_FOUND,
)
from engine.core.institutions import get_registry
from engine.core.ledger import get_ledger


router = APIRouter(prefix="/admin", tags=["admin"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    INSTITUTION_CONFIG_INVALID: 400,
    INSTITUTION_CONFIG_UNAVAILABLE: 500,
    INSTITUTION_CONFIG_HISTORY_UNAVAILABLE: 500,
    INSTITUTION_NOT_FOUND: 404,
}


class ConfigFlagsModel(BaseModel):
    """Configuration flags."""

    model_config = ConfigDict(strict=True, extra="forbid")

    require_institution_header_for_runtime: bool = False
    allow_legacy_routes: bool = True
    enable_contracts_stub: bool = True


class ConfigLimitsModel(BaseModel):
    """Configuration limits."""

    model_config = ConfigDict(strict=True, extra="forbid")

    rate_limit_per_minute: int = Field(ge=1, le=100000, default=100)
    max_body_bytes: int = Field(ge=1024, default=262144)


class ConfigDefaultsModel(BaseModel):
    """Configuration defaults."""

    model_config = ConfigDict(strict=True, extra="forbid")

    default_dept: str = Field(default="finance", pattern=r"^[a-zA-Z0-9_-]+$")
    default_bundle_name: str = Field(default="finance-pilot", min_length=1, max_length=64)


class EmergencyStopModel(BaseModel):
    """Emergency stop configuration."""

    model_config = ConfigDict(strict=True, extra="forbid")

    enabled: bool = False
    blocked_endpoints: List[str] = Field(default_factory=list)


class InstitutionConfigResponse(BaseModel):
    """Response body for institution config."""

    schema_version: str
    updated_at: Optional[str]
    updated_by: Optional[str]
    flags: ConfigFlagsModel
    limits: ConfigLimitsModel
    defaults: ConfigDefaultsModel
    freeze_mode: bool = False
    emergency_stop: EmergencyStopModel = Field(default_factory=EmergencyStopModel)


class PutInstitutionConfigRequest(BaseModel):
    """Request body for updating institution config.

    Full config required - no partial updates.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    flags: ConfigFlagsModel
    limits: ConfigLimitsModel
    defaults: ConfigDefaultsModel
    freeze_mode: bool = False
    emergency_stop: EmergencyStopModel = Field(default_factory=EmergencyStopModel)


class ConfigHistoryItemResponse(BaseModel):
    """Response body for a single history item."""

    schema_version: str
    updated_at: Optional[str]
    updated_by: Optional[str]
    flags: ConfigFlagsModel
    limits: ConfigLimitsModel
    defaults: ConfigDefaultsModel
    freeze_mode: bool = False
    emergency_stop: EmergencyStopModel = Field(default_factory=EmergencyStopModel)
    seq: Optional[int] = None


class ConfigHistoryResponse(BaseModel):
    """Response body for config history."""

    items: List[ConfigHistoryItemResponse]


def _require_admin_token(token: Optional[str]) -> None:
    """Verify admin token, raise HTTPException if invalid."""
    if not verify_admin_token(token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )


def _validate_institution_id(institution_id: str) -> None:
    """Validate institution exists or is default.

    Args:
        institution_id: Institution UUID.

    Raises:
        HTTPException: 404 if not found.
    """
    # Default institution is always valid
    if institution_id == DEFAULT_INSTITUTION_ID:
        return

    registry = get_registry()
    institution, error_code, error_message = registry.get_by_id(institution_id)

    if error_code == INSTITUTION_NOT_FOUND:
        raise HTTPException(
            status_code=404,
            detail={
                "code": INSTITUTION_NOT_FOUND,
                "message": f"Institution '{institution_id}' not found",
            },
        )
    elif error_code is not None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": INSTITUTION_CONFIG_UNAVAILABLE,
                "message": error_message,
            },
        )


def _config_to_response(config: InstitutionConfig) -> InstitutionConfigResponse:
    """Convert InstitutionConfig to response model."""
    return InstitutionConfigResponse(
        schema_version=config.schema_version,
        updated_at=config.updated_at,
        updated_by=config.updated_by,
        flags=ConfigFlagsModel(
            require_institution_header_for_runtime=config.flags.require_institution_header_for_runtime,
            allow_legacy_routes=config.flags.allow_legacy_routes,
            enable_contracts_stub=config.flags.enable_contracts_stub,
        ),
        limits=ConfigLimitsModel(
            rate_limit_per_minute=config.limits.rate_limit_per_minute,
            max_body_bytes=config.limits.max_body_bytes,
        ),
        defaults=ConfigDefaultsModel(
            default_dept=config.defaults.default_dept,
            default_bundle_name=config.defaults.default_bundle_name,
        ),
        freeze_mode=config.freeze_mode,
        emergency_stop=EmergencyStopModel(
            enabled=config.emergency_stop.enabled,
            blocked_endpoints=config.emergency_stop.blocked_endpoints,
        ),
    )


@router.get("/institutions/{institution_id}/config", response_model=InstitutionConfigResponse)
async def get_institution_config(
    institution_id: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> InstitutionConfigResponse:
    """Get institution config.

    Returns effective config - either saved config or deterministic defaults.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Institution config.

    Raises:
        HTTPException: 404 if institution not found, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)
    _validate_institution_id(institution_id)

    config = get_effective_config(institution_id)
    return _config_to_response(config)


@router.put("/institutions/{institution_id}/config", response_model=InstitutionConfigResponse)
async def put_institution_config(
    institution_id: str,
    request: PutInstitutionConfigRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> InstitutionConfigResponse:
    """Update institution config.

    Full replacement - requires complete config body.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        institution_id: Institution UUID.
        request: Full config to set.
        x_admin_token: Admin token from header.
        x_actor_id: Actor ID from header (for audit trail).

    Returns:
        Updated institution config.

    Raises:
        HTTPException: 404 if institution not found, 400 if config invalid, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)
    _validate_institution_id(institution_id)

    # Build config dict from request
    config_dict: Dict[str, Any] = {
        "flags": request.flags.model_dump(),
        "limits": request.limits.model_dump(),
        "defaults": request.defaults.model_dump(),
        "freeze_mode": request.freeze_mode,
        "emergency_stop": request.emergency_stop.model_dump(),
    }

    # Actor ID for audit trail
    updated_by = x_actor_id or "admin"

    # Save config
    saved_config, error_code, error_message, config_hash = save_active_config(
        institution_id=institution_id,
        config_dict=config_dict,
        updated_by=updated_by,
    )

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    # Emit ledger event with freeze/emergency_stop details
    ledger = get_ledger()
    if ledger:
        ledger.append(
            event_type="INSTITUTION_CONFIG_UPDATED",
            tenant_id=institution_id,
            actor_id=updated_by,
            actor_roles=["admin"],
            case_id=institution_id,
            step="ADMIN:institution.config.update",
            payload={
                "schema_version": CONFIG_SCHEMA_VERSION,
                "config_sha256": config_hash,
                "freeze_mode": saved_config.freeze_mode,
                "emergency_stop.enabled": saved_config.emergency_stop.enabled,
                "emergency_stop.blocked_endpoints_count": len(saved_config.emergency_stop.blocked_endpoints),
            },
        )

    # Invalidate cache so next request sees updated config
    invalidate_config_cache(institution_id)

    return _config_to_response(saved_config)


@router.get("/institutions/{institution_id}/config/history", response_model=ConfigHistoryResponse)
async def get_institution_config_history(
    institution_id: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> ConfigHistoryResponse:
    """Get institution config history.

    Returns all historical config versions from history.jsonl.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        List of historical configs.

    Raises:
        HTTPException: 404 if institution not found, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)
    _validate_institution_id(institution_id)

    history, error_code, error_message = get_config_history(institution_id)

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    # Convert history dicts to response models
    items = []
    for config_dict in history:
        config = InstitutionConfig.from_dict(config_dict)
        items.append(ConfigHistoryItemResponse(
            schema_version=config.schema_version,
            updated_at=config.updated_at,
            updated_by=config.updated_by,
            flags=ConfigFlagsModel(
                require_institution_header_for_runtime=config.flags.require_institution_header_for_runtime,
                allow_legacy_routes=config.flags.allow_legacy_routes,
                enable_contracts_stub=config.flags.enable_contracts_stub,
            ),
            limits=ConfigLimitsModel(
                rate_limit_per_minute=config.limits.rate_limit_per_minute,
                max_body_bytes=config.limits.max_body_bytes,
            ),
            defaults=ConfigDefaultsModel(
                default_dept=config.defaults.default_dept,
                default_bundle_name=config.defaults.default_bundle_name,
            ),
            freeze_mode=config.freeze_mode,
            emergency_stop=EmergencyStopModel(
                enabled=config.emergency_stop.enabled,
                blocked_endpoints=config.emergency_stop.blocked_endpoints,
            ),
            seq=config_dict.get("seq"),
        ))

    return ConfigHistoryResponse(items=items)
