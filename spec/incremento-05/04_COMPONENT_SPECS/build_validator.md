# validators/build_validator.py — Build Validator (repo gerado)

## Objetivo
Validar que o repo gerado compila/builda após aplicação de patches.

## Local
- `/home/bazari/engine/validators/build_validator.py`

## Execução
Comandos executados dentro de:
- `/home/bazari/generated/<project>/`

Comandos mínimos:
- Backend:
  - `mvn test` (rodar em `/home/bazari/generated/<project>/backend`)
- Frontend:
  - `npm ci` e `npm run build` (rodar em `/home/bazari/generated/<project>/frontend`)

## Regras
- Não executar comandos fora do diretório do projeto.
- Capturar stdout/stderr para log.

## Critério de aceite (Dia 4)
- Repo vazio (templates puros) passa no build.
