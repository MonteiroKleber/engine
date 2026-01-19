# Admin Authentication and Authorization

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 06 — Multi-instituicao e Admin Security

---

## 1. Visao Geral

Este documento descreve o sistema de autenticacao e autorizacao administrativa do Libervia Engine, incluindo chaves admin, rotacao, revogacao e auditoria.

---

## 2. Institution Registry

### 2.1 Estrutura Append-Only

**Arquivo:** [institutions.py:153-442](../../../../src/engine/core/institutions.py)

```
Registry Path: $ENGINE_INSTITUTIONS_REGISTRY_PATH
Default: var/institutions_registry.jsonl
Format: JSONL append-only
```

### 2.2 Campos de Registro

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `institution_id` | UUID | ID unico gerado pelo sistema |
| `slug` | string | Nome curto (unico, imutavel) |
| `name` | string | Nome de exibicao |
| `created_at` | datetime | Timestamp de criacao |
| `created_by` | string | Actor que criou |

### 2.3 Operacoes

| Operacao | Metodo | Auditoria |
|----------|--------|-----------|
| Criar | `create(slug, name, created_by)` | INSTITUTION_CREATED |
| Buscar por slug | `get_by_slug(slug)` | - |
| Buscar por ID | `get_by_id(id)` | - |
| Listar | `list_institutions()` | - |

### 2.4 API Endpoints

**Arquivo:** [admin_institutions.py](../../../../src/engine/api/admin_institutions.py)

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/admin/institutions` | POST | Criar instituicao |
| `/admin/institutions` | GET | Listar instituicoes |
| `/admin/institutions/{id}` | GET | Buscar por ID |

---

## 3. Admin Keys

### 3.1 Estrutura

**Arquivo:** [admin_keys.py:115-300+](../../../../src/engine/core/admin_keys.py)

```
Keys Path: $INSTITUTION_ROOT/admin_keys.jsonl
Format: JSONL append-only
```

### 3.2 Registro de Chave

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `key_id` | UUID | ID unico da chave |
| `key_hash` | string | Hash SHA256 do secret |
| `institution_id` | UUID | Instituicao dona |
| `operation` | enum | create, revoke, use |
| `created_at` | datetime | Timestamp da operacao |
| `expires_at` | datetime | Expiracao (opcional) |
| `status` | enum | active, revoked |

### 3.3 Geracao de Chave

**Arquivo:** [admin_keys.py:261-292](../../../../src/engine/core/admin_keys.py)

```python
def create_key(self, institution_id: str, ...) -> Tuple[str, str]:
    # 1. Gera secret: secrets.token_urlsafe(32) -> 43 chars
    # 2. Computa hash: SHA256:<hex>
    # 3. Append registro com operation="create"
    # 4. Retorna (key_id, plaintext_secret)
```

### 3.4 Verificacao de Chave

**Arquivo:** [admin_keys.py](../../../../src/engine/core/admin_keys.py)

```python
def verify_key(self, institution_id: str, plaintext: str) -> Tuple[bool, str, str]:
    # 1. Computa hash do plaintext
    # 2. Busca chave com hash correspondente
    # 3. Verifica institution_id matches
    # 4. Verifica status != revoked
    # 5. Verifica nao expirada
    # 6. Retorna (valid, key_id, error)
```

### 3.5 Rotacao de Chave

```
1. Criar nova chave (POST /admin/institutions/{id}/admin-keys)
2. Atualizar sistemas para usar nova chave
3. Revogar chave antiga (POST /admin/institutions/{id}/admin-keys/{key_id}/revoke)
```

### 3.6 Revogacao de Chave

**Arquivo:** [admin_keys.py](../../../../src/engine/core/admin_keys.py)

```python
def revoke_key(self, institution_id: str, key_id: str) -> Tuple[bool, str]:
    # 1. Busca chave
    # 2. Verifica nao ja revogada
    # 3. Append registro com operation="revoke"
    # 4. Retorna (success, error)
```

---

## 4. Autenticacao Admin

### 4.1 Headers Suportados

**Arquivo:** [admin_auth.py:37-70](../../../../src/engine/core/admin_auth.py)

| Header | Prioridade | Escopo |
|--------|------------|--------|
| `X-Admin-Key` | 1 (preferido) | Per-institution |
| `X-Admin-Token` | 2 (legacy) | Apenas DEFAULT_INSTITUTION |

### 4.2 Fluxo de Verificacao

```
verify_admin_auth(institution_id, headers):
  1. Se X-Admin-Key presente:
     -> _verify_admin_key(institution_id, key)
     -> Se valido: return (true, key_id, "admin_key")
     -> Se invalido: return (false, error_code, "admin_key")

  2. Se X-Admin-Token presente:
     -> _verify_legacy_admin_token(institution_id, token)
     -> Apenas funciona se institution_id == DEFAULT
     -> Se valido: return (true, None, "legacy_token")
     -> Se invalido: return (false, error_code, "legacy_token")

  3. Nenhum header:
     -> return (false, "ADMIN_KEY_REQUIRED", None)
```

### 4.3 Restricao de Legacy Token

**Arquivo:** [admin_auth.py:123-165](../../../../src/engine/core/admin_auth.py)

```python
def _verify_legacy_admin_token(institution_id: str, token: str):
    # Legacy token ONLY works for DEFAULT_INSTITUTION_ID
    if institution_id != DEFAULT_INSTITUTION_ID:
        return AdminAuthResult(
            valid=False,
            error_code="ADMIN_KEY_REQUIRED",  # Not LEGACY_TOKEN_NOT_ALLOWED
        )
```

---

## 5. API de Admin Keys

### 5.1 Endpoints

**Arquivo:** [admin_keys.py (API)](../../../../src/engine/api/admin_keys.py)

| Endpoint | Metodo | Descricao | Auth |
|----------|--------|-----------|------|
| `/admin/institutions/{id}/admin-keys` | POST | Criar chave | Required |
| `/admin/institutions/{id}/admin-keys` | GET | Listar chaves | Required |
| `/admin/institutions/{id}/admin-keys/{key_id}/revoke` | POST | Revogar chave | Required |

### 5.2 Criar Chave

```
POST /admin/institutions/{institution_id}/admin-keys
Headers: X-Admin-Key: <existing_key> OR X-Admin-Token: <legacy>
Body: {
  "expires_at": "2030-12-31T23:59:59Z"  // opcional
}

Response 201:
{
  "key_id": "uuid",
  "plaintext_secret": "base64url...",  // 43 chars, MOSTRADO UMA VEZ
  "created_at": "...",
  "expires_at": "..."  // se fornecido
}
```

### 5.3 Listar Chaves

```
GET /admin/institutions/{institution_id}/admin-keys
Headers: X-Admin-Key: <key>

Response 200:
{
  "items": [
    {
      "key_id": "uuid",
      "status": "active|revoked",
      "created_at": "...",
      "expires_at": "...",
      "last_used_at": "..."
    }
  ]
}
```

**Nota:** `plaintext_secret` e `key_hash` NUNCA sao expostos na listagem.

### 5.4 Revogar Chave

```
POST /admin/institutions/{institution_id}/admin-keys/{key_id}/revoke
Headers: X-Admin-Key: <key>

Response 200:
{
  "key_id": "uuid",
  "status": "revoked",
  "revoked_at": "..."
}
```

---

## 6. Auditoria

### 6.1 Eventos de Admin Key

| Evento | Quando | Payload |
|--------|--------|---------|
| `ADMIN_KEY_CREATED` | Chave criada | key_id, institution_id |
| `ADMIN_KEY_USED` | Chave usada para auth | key_id, institution_id, endpoint |
| `ADMIN_KEY_REVOKED` | Chave revogada | key_id, institution_id, revoked_by |
| `ADMIN_KEY_EXPIRED` | Chave expirou | key_id, institution_id |
| `ADMIN_KEY_DENIED` | Tentativa rejeitada | reason, institution_id |

### 6.2 Eventos de Institution

| Evento | Quando | Payload |
|--------|--------|---------|
| `INSTITUTION_CREATED` | Instituicao criada | institution_id, slug, created_by |
| `INSTITUTION_CONFIG_UPDATED` | Config alterada | institution_id, changes, updated_by |

### 6.3 Localizacao no Ledger

**Arquivo:** [admin_auth.py:73-120](../../../../src/engine/core/admin_auth.py)

```python
def _verify_admin_key(...):
    # On success:
    registry.mark_used(institution_id, key_id)
    ledger.append(
        event_type="ADMIN_KEY_USED",
        tenant_id=institution_id,
        actor_id=key_id,
        ...
    )
```

---

## 7. Bootstrap de Primeira Chave

### 7.1 Problema

Para criar a primeira admin key de uma instituicao, nao ha chave existente para autenticar.

### 7.2 Solucao: Legacy Token para DEFAULT

```
# Instituicao DEFAULT pode usar X-Admin-Token (ENV)
POST /admin/institutions/00000000-0000-0000-0000-000000000000/admin-keys
Headers: X-Admin-Token: <ENGINE_ISE_ADMIN_TOKEN>
```

### 7.3 Solucao: Bootstrap via CLI (futuro)

```bash
# CLI privilegiado cria primeira chave
engine admin bootstrap-key --institution <id> --output-file key.txt
```

---

## 8. Seguranca

### 8.1 Protecoes Implementadas

| Protecao | Implementacao |
|----------|---------------|
| Hash de secrets | SHA256 (nunca armazenado plaintext) |
| Isolamento por institution | Chave de A nao funciona para B |
| Append-only storage | Imutabilidade de registros |
| Expiracao | Campo expires_at opcional |
| Revogacao | Marcacao permanente no registro |
| Auditoria | Eventos no ledger |

### 8.2 Praticas Recomendadas

1. **Rotacao regular** - Revogar chaves antigas periodicamente
2. **Expiracao** - Definir expires_at para chaves de curta duracao
3. **Minimo privilegio** - Usar chaves separadas para sistemas diferentes
4. **Monitoramento** - Auditar eventos ADMIN_KEY_USED
5. **Revogacao imediata** - Revogar chaves comprometidas

---

## 9. GAPs Identificados

| # | GAP | Severidade | Status |
|---|-----|------------|--------|
| 1 | Sem evento ADMIN_KEY_DENIED no ledger para tentativas rejeitadas | Alto | **RESOLVIDO** |
| 2 | Sem rate limiting para tentativas de auth admin | Medio | ABERTO |
| 3 | Sem mecanismo de bootstrap para instituicoes nao-DEFAULT | Medio | ABERTO |

### 9.1 Resolucao do GAP 1

O evento `ADMIN_KEY_DENIED` ja estava implementado em [admin_auth.py:113-119](../../../../src/engine/core/admin_auth.py):

```python
# Em _verify_admin_key():
_emit_auth_event(
    institution_id=institution_id,
    event_type="ADMIN_KEY_DENIED",
    key_id=key_id,
    decision="deny",
    reason=error_code,
)
```

Testes adicionados em `test_cross_tenant_isolation.py`:
- `test_invalid_admin_key_emits_denied_event`
- `test_legacy_token_for_non_default_emits_denied_event`

---

## 10. Testes

| Teste | Arquivo |
|-------|---------|
| Criar chave | test_admin_keys_api.py |
| Listar chaves | test_admin_keys_api.py |
| Revogar chave | test_admin_keys_api.py |
| Usar chave para auth | test_admin_keys_api.py |
| Chave de outra institution rejeitada | test_admin_keys_registry.py:246-254 |
| Chave revogada rejeitada | test_admin_keys_registry.py:287-296 |
| Legacy token apenas DEFAULT | test_admin_keys_api.py:107-116 |
| **ADMIN_KEY_DENIED event** | test_cross_tenant_isolation.py | **NOVO** |

---

## 11. Referencias

- [spec.md](spec.md) - Especificacao da Etapa 06
- [isolation.md](isolation.md) - Modelo de isolamento
- [admin_keys.py (core)](../../../../src/engine/core/admin_keys.py) - Registry de chaves
- [admin_auth.py](../../../../src/engine/core/admin_auth.py) - Verificacao de auth
- [admin_keys.py (api)](../../../../src/engine/api/admin_keys.py) - Endpoints

---

**Status:** ESPECIFICACAO ATIVA (GAP 1 RESOLVIDO, GAPs 2-3 ABERTOS - baixa severidade)
**Data:** 2026-01-18
**Atualizado:** 2026-01-18 - Verificado que ADMIN_KEY_DENIED ja estava implementado, adicionados testes
