# Relatório: Remover Hardcode de BLOCKED_PATHS

**Data**: 2026-01-11
**Problema**: `PatchEngine.BLOCKED_PATHS` continha paths absolutos hardcoded (`/home/bazari/engine`, `/home/bazari/templates`)

---

## Diagnóstico

O atributo de classe `BLOCKED_PATHS` em `patch_engine/patch_engine.py` tinha valores hardcoded:

```python
# ANTES (inaceitável)
BLOCKED_PATHS: List[str] = ["/home/bazari/engine", "/home/bazari/templates"]
```

**Problemas**:
1. **Não portável** - Quebra em qualquer ambiente fora de `/home/bazari/`
2. **Incompatível com CI** - Pipelines usam paths diferentes
3. **Incompatível com SaaS** - ISE-SaaS usa workspaces dinâmicos

---

## Solução Implementada

### 1. Derivação Portável via `Path(__file__).resolve()`

Módulo-level constants derivam os paths a partir da localização do arquivo:

```python
# patch_engine/patch_engine.py

# Derive engine root from this file's location: patch_engine/patch_engine.py -> engine/
_ENGINE_ROOT = Path(__file__).resolve().parent.parent

# Templates root is a sibling to engine root (engine/../templates)
_TEMPLATES_ROOT = _ENGINE_ROOT.parent / "templates"

# Build blocked paths list: always include engine, include templates only if exists
_BLOCKED_PATHS_LIST: List[str] = [str(_ENGINE_ROOT)]
if _TEMPLATES_ROOT.exists():
    _BLOCKED_PATHS_LIST.append(str(_TEMPLATES_ROOT))
```

### 2. BLOCKED_PATHS Usa Lista Condicional

```python
class PatchEngine:
    # Class-level blocked paths for backwards compatibility with tests
    # Derived portably from module location (no hardcoded absolutes)
    # Templates included only if directory exists
    BLOCKED_PATHS: List[str] = _BLOCKED_PATHS_LIST
```

### 3. Testes Usam Valores Derivados Diretamente

Os testes foram atualizados para usar os valores derivados sem heurísticas por substring:

```python
def test_blocked_paths_are_canonical(self):
    """Verificar que os paths bloqueados estão definidos e são canônicos."""
    from patch_engine.patch_engine import _ENGINE_ROOT, _TEMPLATES_ROOT

    # BLOCKED_PATHS deve conter pelo menos engine root
    assert len(PatchEngine.BLOCKED_PATHS) >= 1

    # Deve incluir engine root (usando valor derivado, não heurística)
    assert str(_ENGINE_ROOT) in PatchEngine.BLOCKED_PATHS

    # Deve incluir templates root SOMENTE se existir
    if _TEMPLATES_ROOT.exists():
        assert str(_TEMPLATES_ROOT) in PatchEngine.BLOCKED_PATHS
```

---

## Arquivos Alterados

| Arquivo | Mudança |
|---------|---------|
| `patch_engine/patch_engine.py` | Linhas 36-48: `_ENGINE_ROOT`, `_TEMPLATES_ROOT`, `_BLOCKED_PATHS_LIST` |
| `patch_engine/patch_engine.py` | Linha 116: `BLOCKED_PATHS = _BLOCKED_PATHS_LIST` |
| `tests/test_patch_engine.py` | Teste usa `_ENGINE_ROOT` e `_TEMPLATES_ROOT` diretamente |
| `tests/test_patch_rules.py` | Testes usam valores derivados sem heurística por substring |

---

## Propriedades Mantidas

| Propriedade | Status |
|-------------|--------|
| Retrocompatibilidade (`PatchEngine.BLOCKED_PATHS`) | ✅ Mantida |
| Tipo (`List[str]`) | ✅ Mantido |
| Paths absolutos | ✅ Mantidos (via `.resolve()`) |
| Segurança (bloqueio de engine) | ✅ Sempre ativo |
| Segurança (bloqueio de templates) | ✅ Condicional (só se existir) |
| Instância usa config (`self.blocked_paths`) | ✅ Mantida |

---

## Resultados dos Testes

```bash
cd /home/bazari/engine && python -m pytest tests/ -v
# 2558 passed, 1 skipped in 105.44s
```

Todos os testes passam, incluindo:
- 77 testes de patch engine/rules
- 2481 outros testes (sem regressão)

---

## Exemplo de Valores

### Ambiente de Desenvolvimento (com /templates existente)
```python
PatchEngine.BLOCKED_PATHS == [
    "/home/bazari/engine",
    "/home/bazari/templates"
]
```

### Ambiente CI (sem /templates)
```python
PatchEngine.BLOCKED_PATHS == [
    "/github/workspace/engine"
]
# templates não incluído porque não existe
```

### Container Docker (com /app/templates existente)
```python
PatchEngine.BLOCKED_PATHS == [
    "/app/engine",
    "/app/templates"
]
```

---

## Interação com Config System

A property `blocked_paths` da instância continua usando o config system:

```python
@property
def blocked_paths(self) -> List[str]:
    """Get list of blocked paths from config."""
    return get_config().get_blocked_paths()
```

O atributo de classe `BLOCKED_PATHS` é para retrocompatibilidade com testes que acessam `PatchEngine.BLOCKED_PATHS` diretamente. Para uso em produção, instâncias devem usar `self.blocked_paths` que consulta a configuração.

---

**Status**: IMPLEMENTADO E TESTADO (Hardening Final)
