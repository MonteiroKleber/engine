# Prompt — Dia 4: Engine conectar IR na pipeline + Store IR

Implemente a Tarefa 4.4 (Dia 4) da Semana 4.

1) Atualizar `orchestrator/engine.py`
Pipeline agora:
- normalize
- classify blueprint
- req_analyst → SRS
- validate SRS
- save SRS (vN)
- domain_modeler → IR
- validate IR
- policy validator (IR)
- save IR (vN)
- write run log

Gates:
- Se SRS inválido: não seguir para IR.
- Se IR inválido (schema) ou policy falhar: não salvar IR.

2) Atualizar `store/artifacts_store.py`
Adicionar suporte ao kind `IR`:
- `store_data/{project}/IR/v{n}.json`

Critério de aceite:
- Rodar CLI gera `SRS/v1.json`, `IR/v1.json` e um log de run.
