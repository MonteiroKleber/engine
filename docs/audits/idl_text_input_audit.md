# Auditoria: Entrada IDL Textual no ISE/Engine

**Data:** 2026-01-10
**Versao:** Bazari Engine v1.0.0
**Tipo:** READ-ONLY Audit

---

## 1. Resumo Executivo

O Bazari Engine possui um **parser IDL v1 textual completo e funcional** (lexer + parser recursive descent) que implementa toda a gramatica EBNF definida. Porem, o fluxo IDL textual **NAO esta conectado ao pipeline canonico** (SRS → IR → OAS → build). O modo `--input-mode idl` funciona apenas com `--idl-only`, que processa e salva o IDL sem executar o pipeline. Quando usado sem `--idl-only`, o parametro e **ignorado** e o input e tratado como texto livre.

---

## 2. Evidencias por Item

### A) Entrypoint e Dispatcher

**Entrypoint:** `/home/bazari/engine/main.py`

**Dispatcher de input-mode:** `/home/bazari/engine/orchestrator/input_dispatcher.py`

**Tratamento do modo IDL no dispatcher:**
```python
# input_dispatcher.py:160-161
if resolved_mode == InputMode.IDL:
    return self._dispatch_idl(project, input_payload, input_path, input_source, detection_reason)
```

**PROBLEMA CRITICO - main.py ignora input-mode no pipeline principal:**
```python
# main.py:489-494 - args.input_mode NAO e passado para engine
result = engine.run_with_build(
    project=args.project,
    raw_input=args.input,  # <-- Passa input como texto bruto
    title=args.title,
    skip_build=False,
)
```

O `--input-mode` e usado apenas quando `--idl-only` esta ativo:
```python
# main.py:439-441
if args.idl_only:
    return run_idl_only(args)  # <-- UNICO caminho que usa dispatcher
```

---

### B) Parser/Gramatica/Lexer

**Gramatica EBNF:** `/home/bazari/engine/idl/idl_v1.ebnf` (289 linhas)

**Lexer:** `/home/bazari/engine/idl/idl_v1.py` (classe `IDLLexer`, linha 765)

**Parser:** `/home/bazari/engine/idl/idl_v1.py` (classe `IDLParser`, linha 965)

**Funcao principal de parse:**
```python
# idl_v1.py:972-1001
def parse(self, source: str) -> IDLDocument:
    """Faz parsing do fonte IDL e retorna um IDLDocument."""
    lexer = IDLLexer(source)
    self.tokens = lexer.tokenize()
    self.pos = 0
    doc = IDLDocument()
    while not self._is_at_end():
        # Parse sections: system, actors, entities, usecases, integrations, nonfunctional
        ...
    return doc
```

**Estrutura gerada:** `IDLDocument` contendo:
- `system: SystemDefinition`
- `actors: List[ActorDefinition]`
- `entities: List[EntityDefinition]`
- `usecases: List[UseCaseDefinition]`
- `integrations: List[IntegrationDefinition]`
- `nonfunctional: List[NFRDefinition]`

**STATUS:** Parser COMPLETO e FUNCIONAL

---

### C) Integracao com Pipeline

**Call graph do fluxo `--input-mode idl` (SEM `--idl-only`):**
```
main.py::main()
  └── args.input_mode = "idl" (parseado mas IGNORADO)
  └── engine.run_with_build(raw_input=args.input)  # <-- input-mode NAO passado
        └── engine.run(raw_input)
              └── normalizer.normalize(raw_input)  # <-- Trata IDL como texto livre
              └── analyst.generate_srs(normalized) # <-- Gera SRS vazio/minimo
              └── domain_modeler.generate_ir(srs)  # <-- IR vazio
              └── FALHA: "IR validation failed, [] should be non-empty"
```

**Call graph do fluxo `--input-mode idl --idl-only`:**
```
main.py::main()
  └── run_idl_only(args)
        └── InputDispatcher.dispatch(input_mode=IDL)
              └── _dispatch_idl()
                    └── IDLParser.parse(source)  # <-- Parse IDL textual
                    └── IDLStore.save(document)  # <-- Salva IDL JSON + MD
        └── SUCESSO: IDL processado e salvo
        └── PIPELINE NAO EXECUTADO
```

**Conversao IDL → SRS:** **NAO EXISTE**

Busca por funcoes de conversao:
```bash
grep -r "IDLDocument.*to.*srs\|idl.*srs\|convert.*idl" /home/bazari/engine
# Resultado: NENHUMA funcao de conversao encontrada
```

O pipeline espera `SRS` gerado pelo `RequirementsAnalyst.generate_srs()`, que processa texto normalizado, nao `IDLDocument`.

---

### D) Testes

**Testes do parser IDL textual:**
| Arquivo | Escopo | Passa |
|---------|--------|-------|
| `test_idl_v1_parser.py` | Parse de todas as secoes | SIM |
| `test_idl_v1_canonicalization.py` | Hash determinístico | SIM |
| `test_idl_v1_contract_gate.py` | Validacao de integridade | SIM |

**Testes do dispatcher com modo IDL:**
| Arquivo | Escopo | Passa |
|---------|--------|-------|
| `test_input_modes_dispatch.py` | Dispatch IDL → IDLDocument | SIM |

**Teste E2E IDL → IR → OAS → build:** **NAO EXISTE**

Todos os testes `engine.run()` usam texto livre:
```python
# test_pipeline_contracts.py:30
result = engine.run(project="...", raw_input="clientes (nome, email)")
```

Nenhum teste chama `engine.run()` ou `engine.run_with_build()` com IDL textual.

---

## 3. Diagnostico Final

**GAP DE IMPLEMENTACAO** - O parser IDL v1 foi implementado e testado isoladamente, mas a integracao com o pipeline canonico nunca foi completada. O gap especifico e:

1. `main.py` nao passa `input_mode` para `Engine.run_with_build()`
2. `Engine.run()` nao aceita `input_mode` como parametro
3. Nao existe funcao `IDLDocument → SRS` para alimentar o pipeline

---

## 4. Pontos de Corte (Onde a Execucao Para)

| # | Caminho | Ponto de Corte | Resultado |
|---|---------|----------------|-----------|
| 1 | `--input-mode idl` (sem --idl-only) | `main.py:489` - input-mode ignorado | IDL tratado como texto → SRS vazio → IR falha |
| 2 | `--input-mode idl --idl-only` | `run_idl_only():310` | IDL salvo, pipeline NAO executado |
| 3 | Pipeline interno | `engine.run():458` | `generate_srs(normalized)` - espera texto, nao IDLDocument |

---

## 5. Riscos

| Risco | Severidade | Descricao |
|-------|------------|-----------|
| **Interface Enganosa** | ALTA | CLI expoe `--input-mode idl` como se fosse suportado para geracao completa, mas so funciona com `--idl-only` |
| **Documentacao** | MEDIA | `main.py` docstring mostra `--input-mode idl` sem mencionar que requer `--idl-only` |
| **Pilotos** | ALTA | Usuarios tentando usar IDL textual para gerar projetos receberao "IR validation failed" sem explicacao clara |
| **Regressao Falsa** | MEDIA | Parece regressao mas nunca funcionou - o piloto-atendimento usou Draft JSON, nao IDL textual |

---

## 6. Recomendacoes (para referencia futura)

1. **Curto prazo:** Documentar que `--input-mode idl` requer `--idl-only` ou retornar erro explicito
2. **Medio prazo:** Implementar `IDLDocument → SRS` ou `IDLDocument → IR` direto
3. **Longo prazo:** Unificar fluxos para que IDL textual e Draft JSON convirjam antes do pipeline

---

## Anexo: Arquivos Chave

| Arquivo | Linhas | Funcao |
|---------|--------|--------|
| `main.py` | 489-494 | Ignora input-mode no pipeline |
| `main.py` | 227-310 | `run_idl_only()` - unico caminho funcional |
| `orchestrator/input_dispatcher.py` | 175-256 | `_dispatch_idl()` - parse e save |
| `orchestrator/engine.py` | 368-512 | `run()` - nao aceita input_mode |
| `idl/idl_v1.py` | 765-963 | `IDLLexer` |
| `idl/idl_v1.py` | 965-1701 | `IDLParser` |
| `idl/idl_v1.ebnf` | 1-289 | Gramatica formal |
