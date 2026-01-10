# Diagnostic Report

---

## Status

```
STATUS FINAL: SMOKE_FAILED
PROJECT: petclinic
ENGINE VERSION: 1.0.0
DURATION: 171566ms
```

---

## Causa Provável

Os containers subiram mas os smoke tests falharam. Isso indica que os serviços não estão respondendo corretamente nos endpoints esperados, provavelmente devido a tempo de inicialização insuficiente ou erro de configuração.

---

## Evidências Objetivas

- Build frontend: OK
- Build backend: OK
- Docker compose up: OK
- docker compose ps: 2 container(s) listado(s)
- Logs backend: disponíveis
- Logs frontend: disponíveis
- Smoke tests: FAILED ou não executados

---

## Possíveis Causas

1. Serviço iniciou mas endpoint não respondeu a tempo
2. Configuração incorreta de rota ou porta
3. Tempo de inicialização maior que o permitido
4. Erro de conexão com banco de dados

---

## Ações Sugeridas

1. `docker compose ps`
2. `curl -v http://localhost:8080/actuator/health`
3. `curl -v http://localhost:3000/`
4. `cd /home/bazari/generated/_failed/SMOKE_FAILED/petclinic_20260105_102837 && docker compose logs --tail=100`

---

## Evidência Preservada

```
REPO PRESERVADO EM:
  /home/bazari/generated/_failed/SMOKE_FAILED/petclinic_20260105_102837
```

---

## Erros Registrados

- Services not ready after 120196ms

---

*Gerado por Bazari Engine v1.0.0*
*Timestamp: 2026-01-05T10:28:37.155923*