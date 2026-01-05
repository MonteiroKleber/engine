# Estrutura do repositório e convenções (Semana 6)

## Delta de estrutura (em relação à Semana 5)
Adicionar/atualizar no repo `/home/bazari/engine`:
- Adicionar/confirmar `schemas/plan.schema.json`.
- Criar `agents/planner_agent.py`.
- Criar `validators/plan_validator.py`.
- Atualizar `store/fs_layout.md` e `store/artifacts_store.py` para suportar `PLAN`.
- Atualizar `validators/policy_validator.py` com policies do PLAN.
- Atualizar `orchestrator/engine.py` para gerar/validar/salvar PLAN e registrar `plan_hash`.
- Criar testes unitários e integração até PLAN.

## Store layout (obrigatório)
- `store_data/{project}/PLAN/v{n}.json`

## Run log: hash (obrigatório)
Arquivo: `{store_root}/{project}/runs/{execution_id}.json`

Campo mínimo:
- `plan_hash`: sha256 hex do conteúdo do arquivo `PLAN/vN.json` salvo.

Recomendação para estabilidade:
- Para `plan_hash`: hash do JSON canonicalizado (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`).
