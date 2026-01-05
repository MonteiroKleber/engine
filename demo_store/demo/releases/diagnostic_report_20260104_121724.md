# Diagnostic Report

---

## Status

```
STATUS FINAL: DOCKER_UP_FAILED
PROJECT: demo
ENGINE VERSION: 1.0.0
DURATION: 229519ms
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
2. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/demo_20260104_121724 && docker compose build`
3. `lsof -i :5432 -i :8080 -i :3000`
4. `cd /home/bazari/generated/_failed/DOCKER_UP_FAILED/demo_20260104_121724 && docker compose logs --tail=100`
5. `docker compose ps`

---

## Evidência Preservada

```
REPO PRESERVADO EM:
  /home/bazari/generated/_failed/DOCKER_UP_FAILED/demo_20260104_121724
```

---

## Erros Registrados

- docker compose up failed: Dockerfile:10

--------------------

   8 |     

   9 |     # Download de dependências (cached se pom.xml não mudar)

  10 | >>> RUN mvn dependency:go-offline -B

  11 |     

  12 |     # Copiar cód

---

*Gerado por Bazari Engine v1.0.0*
*Timestamp: 2026-01-04T12:17:24.065932*