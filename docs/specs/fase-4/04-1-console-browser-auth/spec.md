# Fase 4 — Etapa 4.1: Auth no Browser (Sessão/Cookie)

**Data:** 2026-01-19  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.1)

## Objetivo

Permitir uso do console no browser sem depender de extensão para injetar header `X-Admin-Token`, mantendo segurança e compatibilidade.

## Escopo

Inclui
- Login simples: token → sessão (cookie)
- Logout
- CSRF básico para rotas POST do console (as mutáveis: mandates, ege rollback, legacy verify, intake)
- Compatibilidade preservada:
  - requests com `X-Admin-Token` continuam funcionando
  - API/admin endpoints continuam como estão

Não inclui
- IAM completo, usuários, RBAC de console por usuário
- OAuth2 externo

## Regras não negociáveis

- Sessão deve ter TTL e ser revogável (logout).
- CSRF deve proteger POSTs feitos via browser.
- Não permitir que a sessão “vaze” para APIs de runtime; é só para `/console/*`.

## UX mínima

- `GET /console/login` mostra formulário para colar token.
- `POST /console/login` valida token e seta cookie.
- `GET /console/logout` limpa cookie.
- Se acessar `/console/*` sem token/cookie válido:
  - se Accept HTML → redirecionar para `/console/login`
  - se Accept JSON → manter erro JSON atual

## Implementação (proposta)

- Cookie assinado (HMAC) com:
  - token hash (ou token id)
  - expires_at
  - nonce
- CSRF:
  - token CSRF por sessão em cookie separado ou campo hidden
  - verificar em POST

## Definition of Done

- Usuário acessa `/console/` no browser, faz login com token, navega sem header.
- POSTs do console exigem CSRF e continuam exigindo auth.
- `X-Admin-Token` continua funcionando para automação/curl.

