# Specs — Fechar Gaps (produção single-instance)

Este diretório contém **specs executáveis** (e prompts para implementação) para fechar gaps críticos **antes de instalar o Libervia/EDAP em produção no cliente** (single-instance).

Regras gerais:
- Cada gap tem sua própria pasta.
- Cada pasta tem:
  - `spec.md` (contrato)
  - `prompts.md` (prompts prontos para Claude Code)

Critério de sucesso desta fase:

“O Libervia/EDAP pode ser instalado no cliente em produção (single-instance), e o cliente consegue criar instituições, definir departamentos e criar sistemas do zero (DSL/IDL → IR → bundle → runtime), com governança real, auditabilidade e agentes como atores governados.”
