# Diagnostic Report

---

## Status

```
STATUS FINAL: DOCKER_UP_FAILED
PROJECT: petclinic
ENGINE VERSION: 1.0.0
DURATION: 176251ms
```

---

## Causa Provável

Timeout ao aguardar docker compose subir os containers. Nenhum container ativo foi detectado dentro do tempo limite configurado. Isso é indicativo de que o comando docker compose up não conseguiu iniciar os serviços, provavelmente devido a imagens não buildadas ou Docker daemon não disponível.

---

## Evidências Objetivas

- Build frontend: OK
- Build backend: OK
- Docker compose up: FAILED
- docker compose ps: vazio (nenhum container rodando)
- Logs backend: vazios ou não disponíveis
- Logs frontend: vazios ou não disponíveis
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
2. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_162924 && docker compose build`
3. `lsof -i :5432 -i :8080 -i :3000`
4. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_162924 && docker compose logs --tail=100`
5. `docker compose ps`

---

## Evidência Preservada

```
REPO PRESERVADO EM:
  /home/bazari/generated/_failed/DOCKER_UP_FAILED/petclinic_20260104_162924
```

---

## Erros Registrados

- docker compose up failed:  petclinic-backend  Built
 petclinic-frontend  Built
 Network petclinic_default  Creating
 Network petclinic_default  Created
 Volume "petclinic_postgres_data"  Creating
 Volume "petclinic_postgres_da

---

*Gerado por Bazari Engine v1.0.0*
*Timestamp: 2026-01-04T16:29:24.086506*