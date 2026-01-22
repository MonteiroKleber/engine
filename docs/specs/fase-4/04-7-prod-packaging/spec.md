# Fase 4 — Etapa 4.7: Packaging / Prod hardening

**Data:** 2026-01-20  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.7)

## Objetivo

Permitir rodar o engine (runtime + console) em ambiente real com previsibilidade.

## Escopo

Inclui
- Checklist de produção (envs obrigatórias, paths, permissões, isolamento)
- Artefato de execução (docker compose mínimo OU systemd unit + exemplo)
- Procedimento de backup/restore do data root

Não inclui
- Kubernetes completo
- Observability stack completa (Prometheus/Grafana) como requisito

## Regras não negociáveis

- Determinismo e auditabilidade não podem ser “opcionais” em produção.
- Falhas de configuração críticas devem falhar no startup (já existe preflight).

## Entregas mínimas

- `docs/specs/fase-4/04-7-prod-packaging/runbook.md`
- `docs/specs/fase-4/04-7-prod-packaging/checklist.md`
- `docs/specs/fase-4/04-7-prod-packaging/gaps.md`
- Artefato mínimo de execução (a decidir no diagnóstico)

## Definition of Done

- Um operador consegue subir o serviço e acessar `/console/` no browser com login.
- Existem instruções claras de backup/restore e checklist de pré-produção.

