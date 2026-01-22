# Fase 4 — Plano Linear (Produto / Onboarding / Conectores / Expansão)

**Data:** 2026-01-19  
**Base:** Fase 3 concluída (console operável + governança + proof + intake assistido)

## Objetivo da Fase 4

Transformar o console/engine em um produto pronto para pilotos reais em empresas, com:

- acesso no browser (sessão) sem depender de extensão de header
- onboarding guiado (instituição, dept, bundles, templates)
- conectores com legado evoluindo de read-only para write governado
- expansão controlada da DSL/IR (sem inflar escopo)

## Não objetivos (nesta fase)

- ERP completo
- “IA autônoma” tomando decisões
- dezenas de conectores enterprise de uma vez

## 0.1) Mapa de etapas → pastas

- **Etapa 4.1** (auth no browser): `docs/specs/fase-4/04-1-console-browser-auth/`
- **Etapa 4.2** (onboarding + templates): `docs/specs/fase-4/04-2-onboarding-templates/`
- **Etapa 4.3** (legacy write governado): `docs/specs/fase-4/04-3-legacy-write-governed/`
- **Etapa 4.4** (governança UI: policies/autonomy): `docs/specs/fase-4/04-4-policies-autonomy-ui/`
- **Etapa 4.5** (expansão DSL/IR controlada): `docs/specs/fase-4/04-5-dsl-ir-expansion/`
- **Etapa 4.6** (agent ops/observability mínima): `docs/specs/fase-4/04-6-agent-ops/`
- **Etapa 4.7** (packaging/prod hardening): `docs/specs/fase-4/04-7-prod-packaging/`

## 0.2) Status atual (Fase 4)

| Etapa | Tema | Status | Pasta |
|------:|------|:------:|-------|
| 4.1 | Auth no browser (sessão/cookie) | ✅ | `docs/specs/fase-4/04-1-console-browser-auth/` |
| 4.2 | Onboarding + templates | ✅ | `docs/specs/fase-4/04-2-onboarding-templates/` |
| 4.3 | Legacy write governado | ✅ | `docs/specs/fase-4/04-3-legacy-write-governed/` |
| 4.4 | Governança UI (policies/autonomy) | ✅ | `docs/specs/fase-4/04-4-policies-autonomy-ui/` |
| 4.5 | Expansão DSL/IR (controlada) | ✅ | `docs/specs/fase-4/04-5-dsl-ir-expansion/` |
| 4.6 | Agent Ops / Observability mínima | ✅ | `docs/specs/fase-4/04-6-agent-ops/` |
| 4.7 | Packaging / Prod hardening | ✅ | `docs/specs/fase-4/04-7-prod-packaging/` |

## Cronograma linear (prioridade)

### Etapa 4.1 — Auth no browser (sessão/cookie)

**Meta:** acessar `/console/*` no browser sem extensão de header, mantendo segurança.

- Login simples (token → sessão) + logout
- Cookie com TTL + CSRF básico para rotas POST do console
- Mantém compatibilidade do `X-Admin-Token` para automação/API

### Etapa 4.2 — Onboarding + templates

**Meta:** reduzir custo de implantação do piloto.

- Wizard: criar instituição, escolher dept(s), selecionar template (finance/support)
- Botão “gerar bundle” e “ver proof” antes de qualquer deploy
- Templates versionados (mínimo: finance/support; opcionais: tech)

### Etapa 4.3 — Legacy write governado (Bridge)

**Meta:** sair do read-only com segurança.

- 1 conector write-mode governado (ex.: arquivo “outbox” + job de aplicação, ou HTTP controlado)
- Approvals/SoD/mandates para write
- Ledger registra: intent → decision → execution → result

### Etapa 4.4 — Governança UI para policies/autonomy

**Meta:** tornar governável o que hoje ainda é “contrato de bundle”.

- UI para proposals de policies/autonomy, no mesmo padrão de mandatos
- Diff e prova no console

### Etapa 4.5 — Expansão DSL/IR (controlada)

**Meta:** aumentar cobertura sem explodir complexidade.

- expandir subset DSL com foco em operações e expressões tipadas
- migração/versionamento (v1.2.2 patch-level) sem quebrar provas

### Etapa 4.6 — Agent Ops / Observability mínima

**Meta:** governar agentes em produção com visibilidade.

- registry/listagem de agents (actor_id + roles + escopo)
- trilha de ações (ledger query) por agente
- painel de “tentativas negadas” e razões (gates)

### Etapa 4.7 — Packaging / Prod hardening

**Meta:** rodar com previsibilidade em ambientes reais.

- Docker compose mínimo (ou systemd pack) + config por instituição
- backup/restore de data roots
- checklist de produção (paths, permissões, hardening)

## Saída esperada da Fase 4

- Um CTO consegue instalar, fazer onboarding do piloto, integrar um legado (RO + 1 write governado), operar via browser e provar compliance/auditoria com poucos cliques.
