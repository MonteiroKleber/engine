# Gaps — Etapa 3.5: Console de Evolução (EGE)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO (PROMPT 3.5.2)
**Prompt inicial:** 3.5.1 (Diagnóstico)

## Resumo

| Gap | Severidade | Status |
|-----|------------|--------|
| GAP-01: Rotas console EGE não existem | Alto | RESOLVIDO |
| GAP-02: Templates EGE não existem | Alto | RESOLVIDO |
| GAP-03: Nav link EGE no base.html | Baixo | RESOLVIDO |
| GAP-04: Função list_releases não existe | Médio | RESOLVIDO |
| GAP-05: Deploy traces não persistem em produção | Médio | PREEXISTENTE |
| GAP-06: Rollback via console | Alto | RESOLVIDO |

---

## Mapeamento: admin_ege.py (API existente)

### Localização
`src/engine/api/admin_ege.py`

### Rotas disponíveis (prefixo `/admin/ege`)

| Rota | Método | Descrição | Auth |
|------|--------|-----------|------|
| `/drift/check` | POST | Verifica drift status | X-Admin-Key ou X-Admin-Token |
| `/proposals` | POST | Cria drift resolution proposal | X-Admin-Key ou X-Admin-Token |
| `/proposals` | GET | Lista proposals | X-Admin-Key ou X-Admin-Token |
| `/proposals/{id}/decide` | POST | Decide proposal (accept/block) | X-Admin-Key ou X-Admin-Token |
| `/pins/status` | GET | Status dos pins | X-Admin-Key ou X-Admin-Token |
| `/pins/propose` | POST | Cria PIN_UPDATE proposal | X-Admin-Key ou X-Admin-Token |
| `/pins/proposals/{id}/accept` | POST | Aceita pin proposal | X-Admin-Key ou X-Admin-Token |
| `/pins/proposals/{id}/block` | POST | Bloqueia pin proposal | X-Admin-Key ou X-Admin-Token |

### Auth requerida
- `X-Institution-Id` header obrigatório
- `require_admin_auth(request, institution_id)` via `admin_auth.py`

---

## Mapeamento: Core EGE modules

### ege.py
`src/engine/core/ege.py`

| Função | Descrição |
|--------|-----------|
| `check_drift()` | Verifica drift (CLEAR/ACTIVE/UNPINNED) |
| `load_drift_state()` | Carrega estado do arquivo |
| `save_drift_state()` | Persiste estado |
| `emit_ege_drift_checked()` | Emite evento no ledger |
| `compute_file_sha256()` | Calcula hash de arquivo |

### ege_proposals.py
`src/engine/core/ege_proposals.py`

| Função | Descrição |
|--------|-----------|
| `create_drift_resolution_proposal()` | Cria proposal quando drift ACTIVE |
| `decide_proposal()` | Aceita/bloqueia proposal |
| `list_proposals()` | Lista proposals (most recent first) |
| `load_current_state()` | Fold JSONL para estado atual |

### Dataclass: ProposalState

```python
@dataclass
class ProposalState:
    proposal_id: str
    status: str              # "OPEN" ou "DECIDED"
    created_at: str
    expected_bundle_manifest_sha256: Optional[str]
    expected_contract_ledger_sha256: Optional[str]
    observed_bundle_manifest_sha256: Optional[str]
    observed_contract_ledger_sha256: Optional[str]
    decision: Optional[str]  # "accept" ou "block"
    reason: Optional[str]
    decided_at: Optional[str]
    decider_actor_id: Optional[str]
```

### ege_pins.py
`src/engine/core/ege_pins.py`

| Função | Descrição |
|--------|-----------|
| `get_pin_status()` | Retorna PinStatus (pinned, observed, drift) |
| `create_pin_update_proposal()` | Cria PIN_UPDATE proposal |
| `accept_pin_update_proposal()` | Aceita e atualiza config |
| `block_pin_update_proposal()` | Bloqueia proposal |
| `is_pin_update_proposal()` | Verifica tipo de proposal |
| `get_observed_hashes()` | Lê hashes do CURRENT bundle |

### ege_rollback.py (Etapa 2.4)
`src/engine/core/ege_rollback.py`

| Função | Descrição |
|--------|-----------|
| `execute_governed_rollback()` | Executa rollback governado |
| `get_pinned_release_path()` | Encontra release pinned |
| `check_rollback_blocked()` | Verifica freeze/emergency |
| `get_current_release_id()` | Retorna release ID do CURRENT |

### Dataclass: RollbackResult

```python
@dataclass
class RollbackResult:
    success: bool
    error_code: Optional[str]
    error_message: Optional[str]
    rolled_back_to: Optional[str]      # release_id
    previous_release: Optional[str]    # release que falhou
    safe_mode_activated: bool
```

---

## Mapeamento: Console Auth (routes.py)

### Auth atual
O console usa `_require_admin_token()` que valida via `verify_admin_token()`:
```python
def _require_admin_token(token: Optional[str]) -> None:
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, ...)
```

### Padrão de POST redirect
Para rotas POST (mutáveis), o padrão usado em Etapa 3.4:
```python
return RedirectResponse(
    url=f"/console/mandates/proposals?institution_id={institution_id}&success=...",
    status_code=303,  # See Other - para POST-Redirect-GET
)
```

---

## GAP-01: Rotas console EGE não existem

### Spec requer
- `GET /console/ege` (overview)
- `GET /console/ege/proposals` (lista)
- `GET /console/ege/proposals/{id}` (detalhe)
- `GET /console/ege/releases` (lista)
- `GET /console/ege/traces/{release_id}` (trace view)
- `POST /console/ege/rollback` (rollback governado)

### Estado atual
Nenhuma rota `/console/ege` existe.

### Solução proposta
Criar 6 handlers em `routes.py`:
1. `console_ege` — overview com drift, pins, proposals count
2. `console_ege_proposals` — lista proposals EGE
3. `console_ege_proposal_detail` — detalhe + diff
4. `console_ege_releases` — lista releases
5. `console_ege_trace` — trace de um release específico
6. `console_ege_rollback` — POST executa rollback governado

---

## GAP-02: Templates EGE não existem

### Spec requer
- listas e detalhes com badges
- confirmação de rollback

### Solução proposta
Criar templates:
- `ege.html` — overview (drift status, pins, proposals count)
- `ege_proposals.html` — lista proposals com status
- `ege_proposal_detail.html` — detalhe com diff hashes
- `ege_releases.html` — lista releases com status
- `ege_trace.html` — trace view de um release

---

## GAP-03: Nav link EGE no base.html

### Estado atual
Nav tem: Home, Status, Bundles, Contracts, Proof, Mandates, Legacy

### Solução proposta
Adicionar após Mandates:
```html
<a href="/console/ege?institution_id={{ institution_id }}..."
   class="{% if active_page == 'ege' %}active{% endif %}">EGE</a>
```

---

## GAP-04: Função list_releases não existe

### Spec requer
- `GET /console/ege/releases` deve listar releases

### Estado atual
- Releases são armazenados em `<bundles_root>/releases/<YYYYMMDD-HHMMSS>/<bundle-name>/`
- Não existe função para listar releases
- `get_current_release_id()` existe mas só retorna o CURRENT

### Solução proposta
Criar função `list_releases(institution_id)` em `ege_rollback.py` ou novo módulo:
```python
def list_releases(institution_id: str, limit: int = 20) -> List[Dict]:
    """Lista releases disponíveis para uma instituição.

    Returns:
        List de dicts com: release_id, bundle_name, is_current, is_pinned
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    releases_dir = bundles_root / "releases"

    # List directories, sort by name (date-based)
    releases = []
    for release_dir in sorted(releases_dir.iterdir(), reverse=True)[:limit]:
        if release_dir.is_dir():
            # Find bundle inside
            for bundle_dir in release_dir.iterdir():
                if bundle_dir.is_dir():
                    releases.append({
                        "release_id": release_dir.name,
                        "bundle_name": bundle_dir.name,
                        "is_current": ...,
                        "is_pinned": ...,
                    })
                    break
    return releases
```

---

## GAP-05: Deploy traces não persistem em produção

### Estado atual (GAP preexistente)
- Conforme `trace-contract.md` (GAP 9.1):
  - `build_pipeline` → persiste `trace.json` e `idl_final.idl` ✓
  - `run_pipeline` (deploy) → **não** persiste trace ✗

### Impacto para Etapa 3.5
- `GET /console/ege/traces/{release_id}` não terá dados para mostrar em deploys de produção

### Decisão para esta etapa
**Opção A (Recomendada):** Mostrar "trace unavailable" para releases sem trace.json
**Opção B:** Implementar persistência de trace em deploy (escopo maior)

Recomendação: Usar Opção A nesta etapa. Deixar persistência de traces para etapa futura.

---

## GAP-06: Rollback via console

### Spec requer
- `POST /console/ege/rollback` com confirmação explícita

### Mecanismo existente (Etapa 2.4)
`execute_governed_rollback()` em `ege_rollback.py`:
- Verifica se rollback está bloqueado (freeze/emergency)
- Encontra release pinned
- Atualiza symlink CURRENT atomicamente
- Emite eventos no ledger
- Se não há release pinned → ativa SAFE_MODE

### Solução proposta
1. GET `/console/ege/rollback/confirm` — tela de confirmação mostrando:
   - Current release
   - Target release (pinned)
   - Warning se vai ativar SAFE_MODE
2. POST `/console/ege/rollback` — executa `execute_governed_rollback()`
3. Redirect para `/console/ege?success=rollback_executed` ou error

### Considerações de segurança
- Requer `X-Admin-Token`
- Mostrar confirmação com detalhes antes de executar
- Emitir evento no ledger (já implementado em `ege_rollback.py`)

---

## Funções Core a Reutilizar

| Função | Import |
|--------|--------|
| `check_drift()` | `engine.core.ege` |
| `load_drift_state()` | `engine.core.ege` |
| `list_proposals()` | `engine.core.ege_proposals` |
| `get_pin_status()` | `engine.core.ege_pins` |
| `execute_governed_rollback()` | `engine.core.ege_rollback` |
| `get_pinned_release_path()` | `engine.core.ege_rollback` |
| `get_current_release_id()` | `engine.core.ege_rollback` |
| `get_bundles_root_for_institution()` | `engine.ise.release` |

**Nota**: Chamar funções core diretamente (Python), não via HTTP.

---

## Checklist de Implementação (PROMPT 3.5.2)

- [x] GAP-01: Criar rotas GET para EGE
- [x] GAP-01: Criar rota POST rollback
- [x] GAP-02: Criar templates ege*.html
- [x] GAP-03: Nav link no base.html
- [x] GAP-04: Função list_releases
- [x] GAP-06: Confirmação + execução rollback
- [x] Testes: auth, GET pages, POST rollback

## Implementação (PROMPT 3.5.2) — Concluído 2026-01-19

### Rotas implementadas (`routes.py`)

| Rota | Método | Handler | Descrição |
|------|--------|---------|-----------|
| `/console/ege` | GET | `console_ege` | Overview: drift, pins, proposals |
| `/console/ege/proposals` | GET | `console_ege_proposals` | Lista proposals EGE |
| `/console/ege/proposals/{id}` | GET | `console_ege_proposal_detail` | Detalhe de proposal |
| `/console/ege/releases` | GET | `console_ege_releases` | Lista releases |
| `/console/ege/traces/{release_id}` | GET | `console_ege_trace` | Trace view |
| `/console/ege/rollback/confirm` | GET | `console_ege_rollback_confirm` | Confirmação |
| `/console/ege/rollback` | POST | `console_ege_rollback` | Executa rollback governado |

### Templates implementados

| Template | Descrição |
|----------|-----------|
| `ege.html` | Overview com drift, pins, proposals summary |
| `ege_proposals.html` | Lista proposals com status badges |
| `ege_proposal_detail.html` | Detalhe com diff de hashes |
| `ege_releases.html` | Lista releases com status current/pinned |
| `ege_trace.html` | Trace view (ou mensagem se indisponível) |
| `ege_rollback_confirm.html` | Página de confirmação de rollback |

### Funções adicionadas

| Função | Arquivo | Descrição |
|--------|---------|-----------|
| `list_releases()` | `ege_rollback.py` | Lista releases disponíveis |
| `_get_ege_overview_info()` | `routes.py` | Coleta info para overview |
| `_get_release_trace()` | `routes.py` | Carrega trace de um release |

### Testes adicionados (`test_console.py`)

| Classe | Testes |
|--------|--------|
| `TestConsoleEGEAuth` | 5 testes (401 para GET/POST sem token) |
| `TestConsoleEGEPage` | 4 testes (HTML, links) |
| `TestConsoleEGEProposalsPage` | 2 testes |
| `TestConsoleEGEReleasesPage` | 2 testes |
| `TestConsoleEGETracePage` | 2 testes (trace unavailable) |
| `TestConsoleEGERollbackConfirm` | 2 testes (warning) |
| `TestConsoleEGERollbackPost` | 2 testes (confirm, redirect) |
| `TestConsoleEGENavLink` | 1 teste |
| `TestConsolePostEndpointsAllowed` | 2 testes (mandates + EGE) |

**Total: 98 testes passando (22 novos para Etapa 3.5)**

---

## Decisões de Design

1. **Auth para POST rollback**: Usar `verify_admin_token()` (padrão console)

2. **Redirect após rollback**: Usar redirect HTTP tradicional com query param de status

3. **Traces indisponíveis**: Mostrar mensagem informativa, não erro

4. **Confirmação de rollback**: Página separada GET antes do POST (não usar JS confirm)
