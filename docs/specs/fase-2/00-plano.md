# Fase 2 — Plano Linear (AXIOM / ISE / EGE / Legacy Bridge / IDL)

**Data:** 2026-01-18  
**Base:** Engine v8.1.1 + Fase 1 concluída

Este documento tem dois objetivos:
1) Mostrar o estado atual do projeto por componente (com % aproximado).
2) Definir um cronograma linear e priorizado para a Fase 2.

## 0) Decision Point (Fonte de Verdade)

**Decisão oficial (Fase 2):** a **fonte de verdade da IDL** é a documentação em `/home/bazari/Downloads/spec-libervia/arquivos`, especialmente:
- IDL v1.1 (EBNF completa): `incremento-038.pdf`
- IDL v1.2.2 (history() + congelamento): `incremento-061.pdf`, `incremento-063.pdf`
- IR canônico (IRCS): `incremento-056.pdf`

Consequência prática:
- A “IDL” atual do engine (JSON parseado por `src/engine/ise/idl_parser.py`) **não é** a IDL institucional canônica. Ela deve ser tratada como **formato legado de input** ou como um **IR provisório**.
- O caminho canônico passa a ser: **IDL (DSL textual v1.2.2) → IR canônico (IRCS v1) → Contracts/Bundle → Runtime**.

## 0.1) Mapa de etapas → pastas (sem ambiguidade)

As etapas abaixo são numeradas como **2.1–2.8**. As pastas no repo podem ter nomes “históricos” e serão mantidas/ajustadas conforme evoluímos.

- **Etapa 2.1** (DSL v1.2.2 → IRCS v1): `docs/specs/fase-2/02-1-idl-mandates-autonomy/` *(nome histórico; escopo pivotado)*
- **Etapa 2.2** (ISE: IRCS v1 → contracts/bundle): `docs/specs/fase-2/02-2-ise-ircs-to-bundle/`
- **Etapa 2.3** (prova offline a partir DSL/IR): `docs/specs/fase-2/02-3-offline-proof-dsl-ir/`
- **Etapa 2.4** (rollback automatizado): `docs/specs/fase-2/02-4-rollback-governed/`
- **Etapa 2.5** (multi-dept parity): `docs/specs/fase-2/02-5-multi-dept-parity/`
- **Etapa 2.6** (multi-tenant hardening): `docs/specs/fase-2/02-6-multi-tenant-hardening/`
- **Etapa 2.7** (legacy bridge read-only): `docs/specs/fase-2/02-7-legacy-bridge-readonly/`
- **Etapa 2.8** (axiom mandates governed): `docs/specs/fase-2/02-8-axiom-mandates-governed/`


## 0.2) Status atual (Fase 2)

Status oficial por etapa:

| Etapa | Tema | Status | Pasta |
|------:|------|:------:|-------|
| 2.1 | DSL v1.2.2 → IRCS v1 | ✅ | `docs/specs/fase-2/02-1-idl-mandates-autonomy/` |
| 2.2 | ISE: IRCS v1 → bundle | ✅ | `docs/specs/fase-2/02-2-ise-ircs-to-bundle/` |
| 2.3 | Prova offline (DSL/IR → bundle) | ✅ | `docs/specs/fase-2/02-3-offline-proof-dsl-ir/` |
| 2.4 | Rollback governado | ✅ | `docs/specs/fase-2/02-4-rollback-governed/` |
| 2.5 | Multi-dept parity | ✅ | `docs/specs/fase-2/02-5-multi-dept-parity/` |
| 2.6 | Hardening multi-tenant (misconfig) | ✅ | `docs/specs/fase-2/02-6-multi-tenant-hardening/` |
| 2.7 | Legacy Bridge (read-only) | ✅ | `docs/specs/fase-2/02-7-legacy-bridge-readonly/` |
| 2.8 | AXIOM: mandatos governados | ✅ | `docs/specs/fase-2/02-8-axiom-mandates-governed/` |

## 1) Levantamento por componente (estado atual)

As porcentagens abaixo são **aproximações operacionais**: medem “o quanto existe e está amarrado end-to-end”, não quantidade de código.

### 1.1 AXIOM (Institutional Brain)
**Status estimado:** **55%**

O que já existe
- Mandatos governados (proposal → decide → apply) com override institucional: `src/engine/core/governed_mandates.py`, `src/engine/api/admin_mandates.py`
- Gates de mandates/autonomy no runtime (semântica canônica)

O que falta para “AXIOM de verdade”
- Expansão para governar policies/autonomy e review graduada
- Conselhos e meta-governança (councils/norms), se entrar no escopo

### 1.2 ISE (Compiler IDL → Bundle)
**Status estimado:** **85%**

O que já existe
- Compilação a partir de IRCS v1 (canônico): `src/engine/ise/ircs_adapter.py`, `src/engine/ise/compiler.py`, `src/engine/ise/__main__.py`
- Emissão de contracts + manifest ABI compatível com loader (Fase 1): `src/engine/ise/emit/`, `src/engine/ise/manifest.py`

Principais lacunas
- Expandir cobertura de geração de contracts a partir do IR (conforme DSL crescer)
- Fortalecer determinismo de build em ambientes CI/CD (timestamps/controlos)

### 1.3 EGE (Evolution Governance Engine)
**Status estimado:** **80%**

O que já existe
- Drift detection + enforcement, proposals e pins
- Rollback governado para última pinned release: `docs/specs/fase-2/02-4-rollback-governed/`

Principais lacunas
- Evoluir a prova de mudança (diff institucional) como produto/console

### 1.4 Legacy Bridge
**Status estimado:** **30%**

O que já existe
- Bridge read-only com registry + drift (arquivo local): `src/engine/legacy_bridge/`

O que falta (núcleo do Legacy Bridge)
- Conectores adicionais (HTTP, DB export, etc.)
- Caminho write-mode governado (após validação de risco)

### 1.5 IDL (Institutional Definition Language)
**Status estimado:** **75%**

O que já existe
- Parser DSL v1.2.2 (subset) → IRCS v1: `src/engine/idl_dsl/` + `examples/finance.idl`
- IRCS v1 como artefato canônico (schema + emitter) e pipeline DSL→IR→bundle: `docs/specs/fase-2/02-1-idl-mandates-autonomy/`

Principais lacunas
- Expandir a cobertura do subset da DSL (sem inflar escopo)
- Evoluir a camada de produto/console para operar isso com segurança


## 2) Princípios de execução da Fase 2 (como vamos trabalhar)

Modo de trabalho (padrão)
- Manter um cronograma linear (este documento).
- Para cada etapa:
  - criar/atualizar **uma spec curta** e **um prompt** correspondente (não antecipar tudo)
  - implementar, testar, atualizar docs/checklist, só então avançar
- Sempre que houver decisão arquitetural (decision point), registrar no topo da spec da etapa.

## 3) Cronograma linear (prioridade)

O foco da Fase 2 é evoluir de “MVP funcional” para “plataforma institucional escalável”, sem quebrar governança.

### Etapa 2.1 — IDL DSL v1.2.2 → IRCS v1 (prioridade máxima)
Objetivo
- Adotar formalmente a IDL **textual** (DSL) v1.2.2 como entrada institucional.
- Definir e implementar o **IR canônico** (IRCS v1) como ponte estável para o ISE.

Entrega mínima
- Spec curta: “IDL DSL v1.2.2 subset suportado no piloto” + “IRCS v1 schema canônico”.
- Parser/conversor mínimo: **IDL DSL (Finance exemplo canônico)** → **IRCS v1 JSON**.
- Validador determinístico (erro codes estáveis) para:
  - gramática do subset
  - tipos básicos do kernel (predicate_expr)
  - referência de campos (`entity.*`, `actor.*`, `context.*`, `request.*`, `history()`).

### Etapa 2.2 — ISE: IRCS v1 → Contracts/Bundle (paridade com runtime)
Objetivo
- Fazer o ISE compilar a partir do **IRCS v1** (não do JSON-IDL ad-hoc), emitindo contracts/bundle compatíveis com o runtime.

Entrega mínima
- Compilar IRCS v1 do Finance para:
  - `rbac.json`, `workflows.json`, `approvals.json`, `sod.json`, `invariants.json`, `policies.json`
  - `bundle.manifest.json` (ABI do loader)
  - `contract_ledger.json` com hashes e `idl_hash`/`source_hash` verificável.

### Etapa 2.3 — Prova offline “clean”: idl_hash real a partir da DSL/IR
Objetivo
- Provar offline (sem runtime) que:
  - DSL → IRCS v1 → contracts/bundle
  - hashes e fingerprints batem
  - o que está “decidido” (IDL) é o que está em produção (bundle pinado).

Entrega mínima
- Validar/verificar offline: manifest ↔ contratos ↔ contract_ledger ↔ idl_hash.
- Opcional: CLI simples de “proof verify”.

### Etapa 2.4 — Rollback automatizado e governado (EGE + release)
Objetivo
- Transformar rollback de “manual” para “procedimento governado e automatizável”.

Entrega mínima
- Definir contrato de release (CURRENT/pins) por instituição.
- Implementar auto-revert em falha de deploy (sem deixar estado “meio aplicado”).
- Testes cobrindo falha em deploy → rollback → runtime consistente.

### Etapa 2.5 — Multi-department parity end-to-end
Objetivo
- Fazer multi-dept ser “primeira classe” (não apenas caminhos auxiliares).

Entrega mínima
- Dept-aware approvals/mandates/autonomy/policies e state store por dept/institution.
- Testes E2E em `/d/{dept}/...` para pelo menos 2 departamentos.

### Etapa 2.6 — Harden multi-tenant: bloqueio de env override perigoso
Objetivo
- Garantir que overrides absolutos não quebrem isolamento em produção multi-tenant.

Entrega mínima
- Regra explícita (bloquear ou forçar namespacing) quando `require_institution_header_for_runtime=true`.
- Preflight/health evidenciando misconfig.

### Etapa 2.7 — Legacy Bridge MVP (read-only)
Objetivo
- Iniciar o Bridge com valor imediato: “provar o legado”, não reescrever.

Entrega mínima
- Modelo de “legacy asset” + hashing + ledger.
- 1 conector read-only (ex.: arquivo, tabela exportada, endpoint) gerando contratos e drift.

### Etapa 2.8 — AXIOM MVP: mandatos governados (criar/revogar via proposals)
Objetivo
- Subir 1 degrau acima dos gates: mandatos como objetos institucionais governados.

Entrega mínima
- CRUD governado de mandates (criação/revogação) via EGE proposal + audit ledger.
- Políticas de review (quando exige humano).

## 4) Ordem recomendada

1) 2.1 (IDL DSL v1.2.2 → IRCS v1)
2) 2.2 (ISE: IRCS v1 → contracts/bundle)
3) 2.3 (prova offline clean a partir da DSL/IR)
4) 2.4 (rollback automatizado)
5) 2.5 (multi-dept)
6) 2.6 (hardening multi-tenant)
7) 2.7 (Legacy Bridge read-only)
8) 2.8 (AXIOM mandatos governados)
