# O que é Libervia/EDAP (e o que não é)

## O que é

Libervia/EDAP é um **runtime institucional governado** que separa explicitamente:

- **decisão institucional** (contratos versionados)
- **execução determinística** (runtime aplica o contrato)
- **enforcement fora do modelo** (gates determinísticos, não inferência)
- **prova auditável offline** (artefatos verificáveis sem “confiar no runtime”)

O objetivo é tornar ações de alto risco (incluindo ações executadas por agentes IA) **governadas, rastreáveis, revogáveis e auditáveis**.

## Dor que resolve

Em ambientes reais, regras de negócio e controles de risco costumam ficar:

- espalhados em código e processos manuais
- difíceis de auditar (quem decidiu, por qual regra?)
- frágeis frente a automação e agentes (expansão implícita de poder)

O EDAP resolve isso fornecendo um núcleo onde:

- **toda execução mutável** passa por gates explícitos (RBAC/SoD/Policies/Mandates/Autonomy/Approvals/Invariants)
- **toda decisão** gera trilha em ledger append-only com hash-chain
- **qualquer drift** e inconsistência pode levar a bloqueio (SAFE_MODE) ou rollback governado

## O que não é

- Não é “chatbot” nem “orquestrador de prompt”.
- Não é um sistema que “decide por conta própria”.
- Não é um no-code/low-code genérico.
- Não é um BPM tradicional com execução implícita sem prova.

## Como o produto é consumido

- O Engine expõe uma API governada (IDL-driven).
- Um “Target” (web/mobile/CLI/chatbot) é um cliente separado que **consome a API**; ele não implementa a governança.

