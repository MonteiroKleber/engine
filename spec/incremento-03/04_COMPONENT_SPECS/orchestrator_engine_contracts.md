# orchestrator/engine.py — Integração até contratos

## Objetivo
Conectar geração/validação/persistência de OpenAPI + RBAC ao pipeline existente (que já chega até IR).

## Etapas novas (após IR válido + policy ok do IR)
1) `contracts_agent.generate_contracts(ir)` → `openapi_yaml`, `rbac_dict`
2) `openapi_validator` (gate)
3) `rbac_validator` (gate)
4) `policy_validator` (contratos) (gate)
5) salvar OpenAPI em `OAS/vN.yaml`
6) salvar RBAC em `RBAC/vN.json`
7) atualizar run log com `oap_hash` e `rbac_hash`

## Gates
- Se qualquer gate falhar: não salvar OAS/RBAC.

## Critério de aceite (Dia 5)
- CLI gera `OAS/v1.yaml` e `RBAC/v1.json` quando IR é válido.
