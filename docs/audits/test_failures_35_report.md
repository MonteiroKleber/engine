# Relatório: Correção dos 35 Testes Falhando

**Data**: 2026-01-11
**Antes**: 35 failed, 2495 passed
**Depois**: 0 failed, 2558 passed, 1 skipped

---

## Resumo Executivo

Todos os 35 testes falhando foram corrigidos sem adicionar skips ou xfails.
As correções foram feitas no código fonte (não nos testes), exceto quando o teste
estava usando APIs antigas.

---

## Causas Raiz Identificadas

### 1. Property sem setter (21 falhas)
**Erro**: `AttributeError: can't set attribute 'GENERATED_ROOT'`

**Causa**: `Engine.GENERATED_ROOT` e `Engine.TEMPLATES_ROOT` eram properties read-only,
mas testes tentavam atribuir valores via `engine.GENERATED_ROOT = ...`

**Correção**: Adicionar setters para as properties em `orchestrator/engine.py`

### 2. PatchEngine.BLOCKED_PATHS ausente (3 falhas)
**Erro**: `AttributeError: type object 'PatchEngine' has no attribute 'BLOCKED_PATHS'`

**Causa**: O atributo de classe `BLOCKED_PATHS` foi removido em favor de uma property `blocked_paths`

**Correção**: Adicionar atributo de classe `BLOCKED_PATHS` para retrocompatibilidade em `patch_engine/patch_engine.py`

### 3. DEFAULT_* ausentes em classes (várias falhas)
**Erro**: `AttributeError: ... does not have the attribute 'DEFAULT_GENERATED_ROOT'`

**Causa**: Classes como `DockerComposeValidator`, `SmokeRunner`, `ReleaseChecklist`, `QAReleaseAgent`
não tinham os atributos de classe `DEFAULT_*` que os testes esperavam

**Correção**: Adicionar atributos de classe `DEFAULT_STORE_ROOT` e `DEFAULT_GENERATED_ROOT` nas classes afetadas

### 4. KeyError em verify_integrity (2 falhas)
**Erro**: `KeyError: 0` em `episode_store.py:907`

**Causa**: Código assumia que `current_files` era lista de tuplas `(path, hash)`, mas agora é lista de dicts `{"path": ..., "hash": ...}`

**Correção**: Atualizar código para usar acesso por chave de dicionário

### 5. TEMPLATE_ROOT não exportado (1 erro de collection)
**Erro**: `ImportError: cannot import name 'TEMPLATE_ROOT'`

**Causa**: `TEMPLATE_ROOT` foi substituído por `get_template_root()` no módulo `patch_generator_v1`

**Correção**: Atualizar import no teste para usar `get_template_root()`

---

## Arquivos Alterados

| Arquivo | Mudança |
|---------|---------|
| `orchestrator/engine.py` | Adicionar setters para GENERATED_ROOT e TEMPLATES_ROOT |
| `patch_engine/patch_engine.py` | Adicionar atributo de classe BLOCKED_PATHS |
| `release/docker_compose_validator.py` | Adicionar DEFAULT_GENERATED_ROOT |
| `release/smoke_runner.py` | Adicionar DEFAULT_GENERATED_ROOT |
| `release/release_checklist.py` | Adicionar DEFAULT_STORE_ROOT e DEFAULT_GENERATED_ROOT |
| `release/qa_release_agent.py` | Adicionar DEFAULT_STORE_ROOT e DEFAULT_GENERATED_ROOT |
| `episodes/episode_store.py` | Corrigir acesso a file_hashes (dict vs tuple) |
| `tests/test_engine_build_loop.py` | Usar instância de Engine para acessar properties |
| `tests/test_frontend_slots.py` | Atualizar import TEMPLATE_ROOT → get_template_root() |

---

## Comando Final

```bash
cd /home/bazari/engine && python -m pytest tests/ -v
```

## Resultado Final

```
================= 2558 passed, 1 skipped in 210.72s (0:03:30) ==================
```

---

## Detalhes das Correções

### orchestrator/engine.py (linhas 340-355)
```python
@GENERATED_ROOT.setter
def GENERATED_ROOT(self, value: str) -> None:
    """Set root for generated projects."""
    self._generated_root = value

@TEMPLATES_ROOT.setter
def TEMPLATES_ROOT(self, value: str) -> None:
    """Set root for templates."""
    self._templates_root = value
```

### patch_engine/patch_engine.py (linha 99)
```python
# Class-level blocked paths for backwards compatibility with tests
BLOCKED_PATHS: List[str] = ["/home/bazari/engine", "/home/bazari/templates"]
```

### episodes/episode_store.py (linha 907-921)
```python
# Antes: current_paths = {f[0] for f in current_files}
# Depois: current_paths = {f["path"] for f in current_files}
```

---

**Status**: CONCLUÍDO
**Skips adicionados**: 0
**Xfails adicionados**: 0
