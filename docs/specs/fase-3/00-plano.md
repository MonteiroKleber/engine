# Fase 3 — Plano Linear (Produto / Console / UX)

**Data:** 2026-01-18  
**Base:** Engine v8.1.1 + Fase 2 concluída (DSL→IR→bundle, prova offline, rollback, multi-dept/tenant, legacy bridge RO, mandatos governados)
## 0.1) Mapa de etapas → pastas

- **Etapa 3.1** (console mínimo read-only): `docs/specs/fase-3/03-1-console-readonly/`
- **Etapa 3.2** (institutional explorer): `docs/specs/fase-3/03-2-institutional-explorer/`
- **Etapa 3.3** (proof no console): `docs/specs/fase-3/03-3-proof-console/`
- **Etapa 3.4** (mandates governance UI): `docs/specs/fase-3/03-4-mandates-governance-ui/`
- **Etapa 3.5** (EGE console): `docs/specs/fase-3/03-5-ege-console/`
- **Etapa 3.6** (legacy console): `docs/specs/fase-3/03-6-legacy-console/`
- **Etapa 3.7** (intake assistido): `docs/specs/fase-3/03-7-intake-assisted/`

## 0.2) Status atual (Fase 3)

| Etapa | Tema | Status | Pasta |
|------:|------|:------:|-------|
| 3.1 | Console mínimo (read-only) | ✅ | `docs/specs/fase-3/03-1-console-readonly/` |
| 3.2 | Institutional Explorer (contracts) | ✅ | `docs/specs/fase-3/03-2-institutional-explorer/` |
| 3.3 | Prova offline no console (UX + export) | ✅ | `docs/specs/fase-3/03-3-proof-console/` |
| 3.4 | Governança de mandatos (UI) | ✅ | `docs/specs/fase-3/03-4-mandates-governance-ui/` |
| 3.5 | EGE no console (proposals/releases/rollback) | ✅ | `docs/specs/fase-3/03-5-ege-console/` |
| 3.6 | Legacy Bridge no console | ✅ | `docs/specs/fase-3/03-6-legacy-console/` |
| 3.7 | Intake assistido (NL/DSL → draft/gaps/export) | ✅ | `docs/specs/fase-3/03-7-intake-assisted/` |
## Objetivo da Fase 3

Transformar o engine em **produto operável** para CTO/COO/Arquitetura e para operação diária, sem quebrar os princípios:

- decisão (instituição) é versionável
- execução é commodity
- governança antes de automação
- prova e auditabilidade offline

## Não objetivos (nesta fase)

- UI bonita e completa para todos os usuários finais do negócio
- substituir ERP
- “chat faz tudo sozinho” sem fluxo governado

## Público alvo

- CTO/Arquitetos: visão institucional, contratos, riscos, deploy/pin/rollback
- Segurança/Compliance: prova offline, trilha auditável, SoD/approvals
- Operação/Plataforma: gestão de tenants, bundles, drift, legacy assets

## Princípios de UX (canônicos)

- UI nunca edita “execução” direto. Mudanças entram como **proposal**.
- Toda ação de alto impacto exige confirmação explícita e mostra consequência (diff/prova).
- Tudo tem link para evidência (manifest, contract_ledger, proof verify, ledger events).

## Cronograma linear (prioridade)

### Etapa 3.1 — Console mínimo (leitura)
- Login/admin (se já existir auth, integrar; se não, modo dev com token)
- Seleção: instituição + dept
- Status: ACTIVE/SAFE_MODE, pinned_release, drift, emergency/freeze

### Etapa 3.2 — Explorer institucional (contratos)
- Visualizar `bundle.manifest.json` + `contract_ledger.json`
- Navegar contracts por dept (rbac, policies, mandates, autonomy, workflows, invariants, sod)
- Mostrar “fonte da decisão”: `source_idl_sha256` e versões

### Etapa 3.3 — Prova offline no console
- Rodar/ver resultados do `engine.proof verify` para um bundle selecionado
- Exportar report JSON

### Etapa 3.4 — Governança operacional (mandatos)
- UI para:
  - listar mandates efetivos (bundle vs governado)
  - criar proposal, aprovar/rejeitar, aplicar/revogar
- Mostrar diff do efeito (antes/depois) e eventos no ledger

### Etapa 3.5 — Evolução e deploy (EGE)
- Lista de proposals/pins
- Botão de rollback governado (quando aplicável)
- Timeline de releases + deploy traces

### Etapa 3.6 — Legacy Bridge (read-only) no console
- Registrar assets (ou pelo menos listar)
- Rodar verify e mostrar drift/tamper

### Etapa 3.7 — UX de “intake” (assistido, não autônomo)
- Entrada de texto (rascunho) → gerar DSL/IR draft → gaps
- UI de perguntas/respostas (NEEDS_ANSWERS) e geração de artefatos
- Exportar DSL/IR para revisão humana

## Saída esperada da Fase 3

- Um CTO consegue navegar, provar e governar um fluxo piloto (finance/support), e integrar um legado read-only, tudo com evidência.

## Encerramento (Fase 3)

A Fase 3 está concluída quando o console permite, de ponta a ponta:

- observar estado (ACTIVE/SAFE_MODE, drift, freeze/emergency)
- inspecionar contratos e provas (manifest/ledger/contracts + proof report)
- governar mandatos (proposal/decide/apply)
- operar EGE (proposals/pins/releases) e executar rollback governado
- operar Legacy Bridge read-only (list + verify)
- fazer intake assistido e exportar DSL/IR

Próximos candidatos naturais (Fase 4)

- Auth de browser (sessão/cookie) para console
- Onboarding e templates por indústria/departamento
- Write-mode governado para Legacy Bridge (após avaliação de risco)
- Expansão do subset DSL (com controle de escopo)

