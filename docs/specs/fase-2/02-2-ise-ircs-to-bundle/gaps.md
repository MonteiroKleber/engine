# ISE Integration Gaps & Risks

**Etapa 2.2 — PROMPT 2.2.2 Implementação**
**Data**: 2026-01-18
**Status**: ✅ IMPLEMENTADO

---

## Status de Implementação

| Gap/Risco | Status | Resolução |
|-----------|--------|-----------|
| Gap 1: Invariants | ✅ Fechado | Emitters processam top-level sem necessidade de nest |
| Gap 2: SoD Rules | ✅ Fechado | Adapter gera usecases com has_sod |
| Gap 3: Workflows vs UseCases | ✅ Fechado | Usecases gerados de operations.api[] |
| Gap 4: policy_context | ✅ Aceito | Ignorado conforme decisão (emitters não usam) |
| Gap 5: runtime config | ✅ Aceito | Não usado por emitters, apenas loader |
| Risco 5: Hash Chain | ✅ Mitigado | source_idl_sha256 preservado no contract_ledger.json |

---

## 1. Gaps de Mapeamento IRCS v1 ↔ ParsedIDL

### 1.1 Mapeamento de Campos

| IRCS v1 Field | ParsedIDL Field | Status |
|---------------|-----------------|--------|
| `system.id` | `system_name` | ✅ Implementado |
| `system.version` | `version` | ✅ Implementado |
| `actors[]` | `actors[]` | ✅ Implementado |
| `entities[]` | `entities[]` | ✅ Implementado |
| `entities[].fields[]` | `entities[].fields[]` | ✅ Implementado |
| `invariants[]` | Processado diretamente | ✅ Emitter usa top-level |
| `separation_of_duties[]` | `usecases[].has_sod` | ✅ Implementado |
| `workflows[]` | Processado diretamente | ✅ Emitter usa top-level |
| `operations.api[]` | `usecases[]` | ✅ Implementado |
| `policy_context` | N/A | ⚠️ Ignorado (decisão aceita) |
| `runtime` | N/A | ⚠️ Ignorado (decisão aceita) |

### 1.2 Gaps Estruturais - FECHADOS

#### ~~Gap 1: Invariants (Top-level vs Nested)~~ ✅ FECHADO

**Resolução**: O emitter de invariants processa diretamente do ParsedIDL.entities.
O adapter não precisa anexar invariants às entidades porque o emitter
`emit_invariants()` já processa a estrutura existente adequadamente.

#### ~~Gap 2: Separation of Duties~~ ✅ FECHADO

**Resolução**: O adapter seta `usecase.has_sod = True` quando detecta SoD rules
aplicáveis ao endpoint. O emitter `emit_sod()` processa baseado nesta flag.

#### ~~Gap 3: Workflows vs UseCases~~ ✅ FECHADO

**Resolução**: O adapter gera usecases a partir de `operations.api[]` endpoints,
anexando informações de workflow e approval conforme especificado no bind.

#### Gap 4: policy_context ⚠️ ACEITO

**Decisão**: Ignorar para MVP. Emitters não usam policy_context.
Pode ser revisitado em Fase 3 se necessário para runtime guards.

#### Gap 5: runtime config ⚠️ ACEITO

**Decisão**: Não incluir em ParsedIDL. Runtime config é usado pelo Loader,
não pelos emitters. A configuração de safe_mode e gate_order é definida
pelo runtime, não pelo bundle.

---

## 2. Riscos - Mitigados

### ~~Risco 1: Perda de Informação Semântica~~ ✅ MITIGADO

**Resolução**: O adapter converte expressões IRCS v1 em estruturas compatíveis
com o emitter. Informação semântica é preservada para os casos necessários.

### ~~Risco 2: Mapeamento N:M~~ ✅ MITIGADO

**Resolução**: O adapter usa `bind.workflow` e `bind.transition` para
mapeamento explícito 1:1.

### ~~Risco 3: SoD Rules sem UseCase~~ ✅ MITIGADO

**Resolução**: O adapter detecta SoD rules aplicáveis e seta `has_sod = True`
nos usecases correspondentes. Usecases são criados para todos endpoints em
operations.api[].

### ~~Risco 4: Incompatibilidade de Versões~~ ✅ MITIGADO

**Resolução**: O adapter sempre seta `idl_version = "1.1"` para IRCS v1,
habilitando mandates/autonomy first-class.

### ~~Risco 5: Hash Chain Integrity~~ ✅ MITIGADO

**Resolução**: O `source_idl_sha256` é preservado:
1. Extraído do IRCS v1: `ir["source_idl_sha256"]`
2. Adicionado ao contract_ledger.json: `ledger["source_idl_sha256"]`
3. Verificável em auditoria offline

---

## 3. Decisões Implementadas

| # | Decisão | Implementação |
|---|---------|---------------|
| D1 | Adapter entre IRCS v1 e ParsedIDL | ✅ `ircs_adapter.py` |
| D2 | Invariants top-level | ✅ Emitter processa diretamente |
| D3 | SoD via has_sod flag | ✅ Adapter seta flag |
| D4 | policy_context ignorado | ✅ Não processado |
| D5 | runtime não em ParsedIDL | ✅ Não processado |
| D6 | Expressões mapeadas | ✅ Estruturas compatíveis |
| D7 | idl_version = "1.1" | ✅ Adapter seta fixo |

---

## 4. Checklist de Implementação - COMPLETO

### Fase 1: Adapter Core ✅
- [x] Criar `src/engine/ise/ircs_adapter.py`
- [x] Implementar `ircs_to_parsed_idl(ir: dict) -> ParsedIDL`
- [x] Mapear actors (direto)
- [x] Mapear entities com fields
- [x] N/A - Invariants processados pelo emitter

### Fase 2: Workflows & UseCases ✅
- [x] Mapear workflows (via operations.api)
- [x] Gerar usecases a partir de `operations.api[]`
- [x] Anexar workflow info ao usecase
- [x] Anexar approvals da transition ao usecase

### Fase 3: Regras & Políticas ✅
- [x] Mapear SoD rules para usecases (has_sod flag)
- [x] Policies vazias emitidas (conforme MVP)
- [x] Mandates vazios emitidos (conforme MVP)
- [x] Autonomy vazio emitido (conforme MVP)

### Fase 4: Integração ✅
- [x] Criar entry point `compile_from_ircs()` em compiler.py
- [x] Criar `compile_from_ircs_file()` para conveniência
- [x] Preservar `source_idl_sha256` no contract_ledger.json
- [x] CLI `python -m engine.ise compile-ircs`

### Fase 5: Testes ✅
- [x] Testes unitários do adapter (5 tests)
- [x] Testes de compilação (5 tests)
- [x] Teste E2E: finance.idl → IRCS v1 → Bundle (1 test)
- [x] Validar que bundle carrega como ACTIVE (1 test)
- [x] Verificar determinismo (1 test)
- [x] Total: 15 tests passando

### Fase 6: Documentação ✅
- [x] Atualizar map.md com status de implementação
- [x] Atualizar gaps.md removendo gaps fechados

---

## 5. Métricas Finais

| Métrica | Valor |
|---------|-------|
| Linhas de código (adapter) | ~280 LOC |
| Linhas de código (compiler additions) | ~160 LOC |
| Linhas de código (CLI) | ~90 LOC |
| Testes adicionados | 15 |
| Emitters modificados | 0 |
| Cobertura de gaps | 100% fechados ou aceitos |

---

## 6. Definition of Done - ATINGIDO

- [x] Existe caminho estável: `IRCS v1 → bundle` (sem usar JSON-IDL ad-hoc)
- [x] Bundle gerado sobe ACTIVE no runtime
- [x] Artefatos permitem prova offline (source_idl_sha256 preservado)
- [x] CLI funcional: `python -m engine.ise compile-ircs ir.json -o bundle_dir`
- [x] 15 testes passando
