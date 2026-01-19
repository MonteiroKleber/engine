# Fase 2 — Etapa 2.6: Harden Multi-Tenant (Misconfig Guardrails)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.6)

## Objetivo

Eliminar classes de misconfiguração que podem quebrar isolamento multi-tenant/multi-dept em produção.

Foco: variáveis de ambiente e configurações que permitem “escape” acidental para paths globais.

## Escopo

Inclui
- Identificar quais ENV/configs podem quebrar isolamento (ex.: paths absolutos de ledger/state store).
- Definir regra canônica em produção institucional:
  - quando multi-tenant está ativo, overrides perigosos devem ser bloqueados ou namespaced automaticamente.
- Implementar um preflight/health que detecta e **falha** (ou ativa SAFE_MODE) em misconfig.
- Testes cobrindo misconfigs comuns.

Não inclui
- Mudança de storage backend
- Cloud specifics

## Contexto (problema real)

Em testes anteriores já apareceu que variáveis como `ENGINE_STATE_STORE_DIR` e `ENGINE_LEDGER_PATH` podem quebrar namespacing se usadas como path absoluto.

Multi-tenant “real” requer:
- storage e ledger sempre namespaced por `institution_id` (e agora também por `dept_id`).

## Regras não negociáveis

- Se `require_institution_header_for_runtime=true` (ou equivalente) estiver ativo:
  - nenhum tenant pode compartilhar ledger/state_store por acidente.
- Misconfig detectada deve resultar em:
  - erro determinístico no startup/preflight, ou
  - SAFE_MODE (decisão a ser tomada na etapa)

## Deliverables

1) `docs/specs/fase-2/02-6-multi-tenant-hardening/matrix.md`
- tabela de ENV/configs: permitido/proibido/em quais modos.

2) Implementação
- Guardrails para ENV overrides perigosos.
- Preflight/health check com diagnóstico explícito.

3) Testes
- Quando multi-tenant está ativo:
  - setar override perigoso → falha determinística
- Quando single-tenant/dev:
  - override permitido (se for política)

## Definition of Done

- Não é possível iniciar runtime multi-tenant em configuração que quebra isolamento.
- Erros são determinísticos e auditáveis.
- Testes automatizados cobrem os cenários.
