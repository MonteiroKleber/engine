# Contexto e Escopo

## Objetivo imutável da Semana 6
Implementar planejamento determinístico em cima do pipeline existente (até IR + contratos):
- `schemas/plan.schema.json` (congelado)
- `agents/planner_agent.py` (gera `plan.json`)
- `validators/plan_validator.py` (gate)
- policies do plan (ordem linear, arquivos, aceites testáveis)
- versionamento: `store_data/{project}/PLAN/v{n}.json`
- `plan_hash` no run log
- testes unitários + integração até PLAN
- demo CLI gerando PLAN sempre

## Entradas e saídas esperadas
- Entradas do Planner: `IR` + `OpenAPI` + `RBAC`.
- Saída: `PLAN` (dict compatível com `schemas/plan.schema.json`).

## Artefatos persistidos (layout)
- `store_data/{project}/PLAN/vN.json`

## Run log (obrigatório)
- incluir `plan_hash` (sha256 do arquivo `PLAN/vN.json` salvo).

## Definição de pronto (Semana 6 concluída)
- `PLAN` gerado a partir de IR + OAS + RBAC.
- Gate de schema + rules do validator + policies do PLAN.
- Versionamento + `plan_hash` no run log.
- `pytest` verde.
- Demo:
  - `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`
  - cria `store_data/demo/PLAN/v1.json`.
