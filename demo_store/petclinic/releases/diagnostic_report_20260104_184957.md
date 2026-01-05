# Diagnostic Report

---

## Status

```
STATUS FINAL: DOCKER_UP_FAILED
PROJECT: petclinic
ENGINE VERSION: 1.0.0
DURATION: 365986ms
```

---

## Causa Provável

O comando docker compose up falhou antes de todos os containers ficarem operacionais. Isso pode indicar erro de configuração, portas em conflito ou recursos insuficientes.

---

## Evidências Objetivas

- Build frontend: OK
- Build backend: OK
- Docker compose up: FAILED
- docker compose ps: 3 container(s) listado(s)
- Logs backend: disponíveis
- Logs frontend: disponíveis
- Smoke tests: FAILED ou não executados

---

## Possíveis Causas

1. Docker daemon não está rodando
2. Imagens não foram buildadas (docker compose build não executado)
3. Portas já em uso (5432, 8080, 3000)
4. Ambiente sem recursos suficientes (memória, disco)
5. Timeout ao aguardar containers subirem

---

## Ações Sugeridas

1. `docker info`
2. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_184957 && docker compose build`
3. `lsof -i :5432 -i :8080 -i :3000`
4. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_184957 && docker compose logs --tail=100`
5. `docker compose ps`

---

## Evidência Preservada

```
REPO PRESERVADO EM:
  /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_184957
```

---

## Erros Registrados

- docker compose up failed: Command timed out

---

*Gerado por Bazari Engine v1.0.0*
*Timestamp: 2026-01-04T18:49:57.496050*