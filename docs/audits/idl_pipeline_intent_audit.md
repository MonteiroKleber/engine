# Auditoria: Intencao Original do --input-mode idl

**Data:** 2026-01-10
**Objetivo:** Confirmar se `--input-mode idl` foi planejado para E2E ou apenas idl-only

---

## 1. Onde a Documentacao Promete IDL no Pipeline

### 1.1 main.py docstring (linhas 14-18)
```python
# Input modes
python main.py --project demo --input "Sistema X" --input-mode natural
python main.py --project demo --input draft.json --input-mode draft
python main.py --project demo --input spec.idl --input-mode idl      # <-- Sem --idl-only
python main.py --project demo --input spec.idl --input-mode auto
```
**Implicacao:** Mostra `--input-mode idl` como equivalente aos outros modos, sugerindo que deveria funcionar igual.

### 1.2 docs/ops/04_running_engine.md (linhas 91-99)
```markdown
## Using IDL Input

python main.py \
  --project myproject \
  --input /path/to/spec.idl \
  --input-mode idl \
  --release                    # <-- PROMETE release mode com IDL!
```
**Implicacao:** Documentacao oficial promete `--input-mode idl --release` funcionando.

### 1.3 CLI help output
```
--input-mode {auto,natural,draft,idl}
    Modo de entrada: auto (detecta), natural (texto livre),
    draft (IDL Draft JSON), idl (IDL v1)
```
**Implicacao:** Apresenta todos os modos como equivalentes, sem mencionar `--idl-only`.

---

## 2. Onde o Codigo Contradiz

### 2.1 main.py:489-494 - input-mode ignorado
```python
# Modo build: gerar + compilar
result = engine.run_with_build(
    project=args.project,
    raw_input=args.input,      # <-- NAO passa input_mode
    title=args.title,
    skip_build=False,
)
```

### 2.2 orchestrator/engine.py - run() nao aceita input_mode
```python
def run(
    self,
    project: str,
    raw_input: str,            # <-- Apenas raw_input
    title: Optional[str] = None,
    legacy_bundle: Optional[Dict[str, str]] = None,
) -> RunResult:
```

### 2.3 input_dispatcher.py so usado com --idl-only
```python
# main.py:439-441
if args.idl_only:
    return run_idl_only(args)  # UNICO lugar que chama dispatcher
```

---

## 3. Indicios Mais Fortes de Intencao Original

### Evidencia 1: Arquitetura Documentada (input_mode.py:1-8)
```python
"""Input Mode - Modos de entrada do motor.

Define os 3 modos de entrada suportados:
- NATURAL: texto solto → Draft → GATE 1 → GATE 2 → IDL v1
- DRAFT: IDL Draft v1 JSON → GATE 1 → GATE 2 → IDL v1
- IDL: IDL v1 (texto .idl ou JSON) → Contract Gate

AUTO detecta o modo automaticamente via heurísticas determinísticas.
"""
```
**Interpretacao:** Os 3 modos sao apresentados como **fluxos paralelos de entrada para o mesmo pipeline**. O modo IDL pula os gates de Draft e vai direto para Contract Gate, mas deveria **continuar no pipeline apos isso**.

### Evidencia 2: Dispatcher Completo (input_dispatcher.py:1-9)
```python
"""Input Dispatcher - Coordena fluxos por modo de entrada.

Dispatcher para os 3 modos de entrada:
- NATURAL: texto → intake → Draft → GATE 1 → GATE 2 → IDL v1 → Contract Gate
- DRAFT: JSON Draft → GATE 1 → GATE 2 → IDL v1 → Contract Gate
- IDL: arquivo .idl ou JSON canônico → Contract Gate

Este módulo NÃO contém LLM. LLM só é chamado via intake (NATURAL mode).
"""
```
**Interpretacao:** O dispatcher foi projetado para **coordenar fluxos de entrada**, nao para ser um endpoint terminal. O fluxo IDL termina no Contract Gate, mas a intencao era que o IDLDocument resultante alimentasse o pipeline.

### Evidencia 3: Commit b14d854 - IDL v1 sem mencao de "idl-only"
```
Add IDL v1 (Institutional Definition Language) + DiagnosticReport Contract

IDL v1:
- EBNF grammar specification (idl_v1.ebnf)
- Full parser with lexer for system, actors, entities, usecases...
- Deterministic canonicalization with SHA256 hashing
- IDLStore with Contract Gate validation
- 87 tests (parser, canonicalization, contract gate)
```
**Interpretacao:** O commit adiciona IDL v1 como **formato de entrada completo** (actors, entities, usecases), nao apenas como storage. Se fosse apenas para guardar, nao precisaria de usecases/integrations/nonfunctional.

---

## 4. Conclusao

### Veredicto: **ERA PRA FUNCIONAR E2E**

**Justificativa:**

1. **Documentacao promete:** `--input-mode idl --release` funcionando (docs/ops/04_running_engine.md)

2. **Arquitetura planejada:** Os 3 modos (natural, draft, idl) sao fluxos paralelos para o **mesmo destino** (pipeline canonico), nao endpoints diferentes

3. **Parser completo demais para idl-only:** O parser IDL v1 implementa usecases, actors, integrations, nonfunctional - elementos que so fazem sentido se forem convertidos para SRS/IR

4. **Nao existe "idl-only" no design original:** O commit b14d854 adiciona IDL sem mencionar `--idl-only`. Esse flag foi adicionado depois (9a9daa4) como workaround, nao como design intencional

### Gap Especifico

O que falta para completar a intencao original:

| Item | Status | Descricao |
|------|--------|-----------|
| IDLParser | OK | Completo e testado |
| IDLStore + Contract Gate | OK | Completo e testado |
| InputDispatcher | OK | Retorna IDLDocument |
| main.py → Engine | **FALTA** | Passar input_mode para Engine |
| Engine.run() | **FALTA** | Aceitar input_mode como parametro |
| IDLDocument → SRS/IR | **FALTA** | Conversao para alimentar pipeline |

---

## 5. Recomendacao

O `--idl-only` deve ser tratado como **workaround temporario**, nao como design final. A intencao original era que `--input-mode idl` funcionasse como entrada E2E, e a implementacao esta incompleta.
