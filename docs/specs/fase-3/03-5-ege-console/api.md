# API — Etapa 3.5: Console de Evolução (EGE)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO (PROMPT 3.5.2)
**Prompt inicial:** 3.5.1 (Diagnóstico)

## Resumo

Este documento especifica as rotas HTML (console) para a UI de governança de evolução (EGE).

---

## Rotas Console (HTML)

### GET /console/ege

**Overview da governança de evolução.**

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `dept_id` | string | Não | ID do departamento |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,
    "dept_id": Optional[str],

    # Drift status
    "drift_status": str,           # "CLEAR" | "ACTIVE" | "UNPINNED"
    "drift_checked_at": Optional[str],

    # Pin status
    "pin_status": {
        "pinned": {
            "bundle_manifest_sha256": Optional[str],
            "contract_ledger_sha256": Optional[str],
        },
        "observed": {
            "bundle_manifest_sha256": Optional[str],
            "contract_ledger_sha256": Optional[str],
        },
    },
    "pinned_release_id": Optional[str],

    # Proposals summary
    "open_proposals_count": int,
    "total_proposals_count": int,

    # Current release
    "current_release_id": Optional[str],

    # Rollback info
    "can_rollback": bool,          # True se pinned != current
    "rollback_blocked": bool,      # True se freeze/emergency
    "rollback_block_reason": Optional[str],
}
```

---

### GET /console/ege/proposals

**Lista de proposals EGE.**

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `dept_id` | string | Não | ID do departamento |
| `status_filter` | string | Não | "OPEN" ou "DECIDED" |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,
    "dept_id": Optional[str],

    "proposals": [
        {
            "proposal_id": str,
            "status": str,           # "OPEN" | "DECIDED"
            "created_at": str,
            "decision": Optional[str],  # "accept" | "block"
            "expected_bundle_manifest_sha256": Optional[str],
            "observed_bundle_manifest_sha256": Optional[str],
        },
        ...
    ],
    "status_filter": Optional[str],
    "total_proposals": int,
}
```

---

### GET /console/ege/proposals/{proposal_id}

**Detalhes de uma proposal.**

#### Path Parameters
| Param | Tipo | Descrição |
|-------|------|-----------|
| `proposal_id` | string | UUID da proposal |

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `dept_id` | string | Não | ID do departamento |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,
    "dept_id": Optional[str],

    "proposal": {
        "proposal_id": str,
        "status": str,
        "created_at": str,
        "expected_bundle_manifest_sha256": Optional[str],
        "expected_contract_ledger_sha256": Optional[str],
        "observed_bundle_manifest_sha256": Optional[str],
        "observed_contract_ledger_sha256": Optional[str],
        "decision": Optional[str],
        "reason": Optional[str],
        "decided_at": Optional[str],
        "decider_actor_id": Optional[str],
    },

    # PIN_UPDATE metadata (se aplicável)
    "is_pin_proposal": bool,
    "pin_metadata": Optional[{
        "release_id": str,
        "bundle_name": str,
    }],
}
```

---

### GET /console/ege/releases

**Lista de releases disponíveis.**

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,

    "releases": [
        {
            "release_id": str,        # e.g., "20260119-143025"
            "bundle_name": str,
            "is_current": bool,
            "is_pinned": bool,
            "has_trace": bool,
        },
        ...
    ],
    "total_releases": int,
    "current_release_id": Optional[str],
    "pinned_release_id": Optional[str],
}
```

---

### GET /console/ege/traces/{release_id}

**Visualização do trace de um release.**

#### Path Parameters
| Param | Tipo | Descrição |
|-------|------|-----------|
| `release_id` | string | ID do release (YYYYMMDD-HHMMSS) |

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,

    "release_id": str,
    "bundle_name": str,

    # Se trace disponível
    "has_trace": bool,
    "trace": Optional[{
        "run_id": str,
        "bundle_name": str,
        "mode": str,
        "sir_sha256": str,
        "draft_sha256": str,
        "final_idl_sha256": str,
        "bundle_manifest_sha256": str,
        "contract_ledger_sha256": str,
        "policy_count": Optional[int],
        "policy_gap_count": Optional[int],
    }],

    # Se trace não disponível
    "trace_unavailable_reason": Optional[str],
}
```

---

### GET /console/ege/rollback/confirm

**Página de confirmação de rollback.**

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Dados para Template

```python
{
    "request": request,
    "active_page": "ege",
    "admin_token": str,
    "institution_id": str,
    "institution_name": str,

    # Current state
    "current_release_id": Optional[str],
    "current_bundle_name": Optional[str],

    # Target state
    "pinned_release_id": Optional[str],
    "target_bundle_path": Optional[str],

    # Warnings
    "will_activate_safe_mode": bool,   # True se não há pinned release
    "rollback_blocked": bool,
    "block_reason": Optional[str],
}
```

---

### POST /console/ege/rollback

**Executa rollback governado.**

#### Query Parameters
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

#### Headers
| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `X-Admin-Token` | Sim | Token de admin |

#### Form Data
| Field | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `confirm` | string | Sim | Deve ser "yes" |
| `reason` | string | Não | Motivo do rollback |

#### Response
Redirect para `/console/ege?institution_id=...&success=...` ou `&error=...`

#### Success Query Params
- `success=rollback_executed&rolled_back_to={release_id}`

#### Error Query Params
- `error=rollback_blocked&reason={reason}`
- `error=rollback_failed&message={message}`
- `error=safe_mode_activated`

---

## Funções Helper Necessárias

### _get_ege_overview_info(institution_id)

```python
def _get_ege_overview_info(institution_id: str) -> Dict[str, Any]:
    """Coleta informações para overview EGE.

    Returns:
        Dict com drift_status, pin_status, proposals count, etc.
    """
    # Drift status
    drift_state = load_drift_state(institution_id)
    if not drift_state:
        drift_state = check_drift(institution_id)

    # Pin status
    pin_status, _, _ = get_pin_status(institution_id)

    # Proposals
    proposals = list_proposals(institution_id, limit=100)
    open_count = sum(1 for p in proposals if p.status == "OPEN")

    # Current release
    current_release = get_current_release_id(institution_id)

    # Config
    config = get_effective_config(institution_id)

    # Rollback check
    blocked, block_code, block_msg = check_rollback_blocked(institution_id)
    can_rollback = config.pinned_release_id and config.pinned_release_id != current_release

    return {
        "drift_status": drift_state.status,
        "drift_checked_at": drift_state.checked_at,
        "pin_status": pin_status.to_dict() if pin_status else {},
        "pinned_release_id": config.pinned_release_id,
        "open_proposals_count": open_count,
        "total_proposals_count": len(proposals),
        "current_release_id": current_release,
        "can_rollback": can_rollback,
        "rollback_blocked": blocked,
        "rollback_block_reason": block_msg,
    }
```

### list_releases(institution_id)

```python
def list_releases(institution_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Lista releases para uma instituição.

    Args:
        institution_id: UUID da instituição.
        limit: Máximo de releases a retornar.

    Returns:
        Lista de dicts com release_id, bundle_name, is_current, is_pinned, has_trace.
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    releases_dir = bundles_root / "releases"

    if not releases_dir.exists():
        return []

    config = get_effective_config(institution_id)
    current_release = get_current_release_id(institution_id)
    pinned_release = config.pinned_release_id

    releases = []
    for release_dir in sorted(releases_dir.iterdir(), reverse=True)[:limit]:
        if not release_dir.is_dir():
            continue

        # Find bundle inside
        for bundle_dir in release_dir.iterdir():
            if bundle_dir.is_dir():
                # Check for trace
                trace_path = bundle_dir / "trace.json"
                has_trace = trace_path.exists()

                releases.append({
                    "release_id": release_dir.name,
                    "bundle_name": bundle_dir.name,
                    "is_current": release_dir.name == current_release,
                    "is_pinned": release_dir.name == pinned_release,
                    "has_trace": has_trace,
                })
                break

    return releases
```

### _get_release_trace(institution_id, release_id)

```python
def _get_release_trace(
    institution_id: str,
    release_id: str,
) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    """Carrega trace de um release.

    Returns:
        Tuple of (trace_dict, bundle_name, error_message).
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    release_dir = bundles_root / "releases" / release_id

    if not release_dir.exists():
        return None, None, "Release not found"

    # Find bundle
    for bundle_dir in release_dir.iterdir():
        if bundle_dir.is_dir():
            trace_path = bundle_dir / "trace.json"
            if trace_path.exists():
                try:
                    with open(trace_path) as f:
                        trace = json.load(f)
                    return trace, bundle_dir.name, None
                except Exception as e:
                    return None, bundle_dir.name, f"Failed to read trace: {e}"
            else:
                return None, bundle_dir.name, "Trace not available for this release"

    return None, None, "No bundle found in release"
```

---

## Badges de Status

| Status | Classe CSS | Cor |
|--------|------------|-----|
| CLEAR | badge-active | verde |
| ACTIVE | badge-error | vermelho |
| UNPINNED | badge-unpinned | cinza |
| OPEN | badge-unpinned | cinza |
| DECIDED (accept) | badge-active | verde |
| DECIDED (block) | badge-error | vermelho |
| is_current | badge-active | verde |
| is_pinned | badge-unpinned | cinza/azul |

---

## Mensagens de Feedback

### Success Messages
- "Rollback executed successfully. Now at release {release_id}."

### Error Messages
- "Rollback blocked: {reason}"
- "Rollback failed: {message}"
- "SAFE_MODE activated: no pinned release available"

---

## Referências

- [spec.md](spec.md) — Especificação da etapa
- [gaps.md](gaps.md) — Gaps identificados
- [admin_ege.py](../../../../src/engine/api/admin_ege.py) — API admin existente
- [ege_rollback.py](../../../../src/engine/core/ege_rollback.py) — Rollback governado
- [ege_proposals.py](../../../../src/engine/core/ege_proposals.py) — Proposals EGE
- [ege_pins.py](../../../../src/engine/core/ege_pins.py) — Pin management
