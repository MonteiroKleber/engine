# Smoke Tests (backend + frontend)

## Objetivo
Validar rapidamente que o sistema gerado está operacional.

## Backend
- Healthcheck: `GET /actuator/health` deve retornar 200.
- CRUD básico: `GET /api/<entityPlural>` deve retornar 200 ou 401 conforme RBAC.

## Frontend
- `npm run build` ok.
- Rota principal renderiza (definir check mínimo: ex. build artifact existe / resposta HTTP 200).

## Artefatos
- Salvar logs e relatórios em:
  - `/home/bazari/generated/<project>/smoke/`

## Critério de aceite (Dia 2)
- Smoke executa localmente e retorna PASS/FAIL.
