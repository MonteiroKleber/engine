# Fase 3 — Etapa 3.1: Console mínimo (leitura)

**Data:** 2026-01-18
**Status:** IMPLEMENTADO (PROMPT 3.1.2)
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.1)

## Objetivo

Disponibilizar um **console mínimo**, focado em **leitura**, para operar e inspecionar a plataforma sem tocar em execução diretamente.

O console deve permitir:
- escolher `institution_id` e `dept_id`
- ver estado do runtime (ACTIVE/SAFE_MODE, drift, freeze/emergency)
- ver release atual/pin (quando aplicável)
- navegar contratos e provas (links para manifest/contract_ledger/proof)

## Escopo

Inclui
- UI simples (web) para leitura.
- Autenticação mínima (modo dev com token ou reutilizar admin token atual, sem inventar um IAM completo).
- Chamadas a APIs existentes do engine (ou endpoints mínimos novos) apenas para leitura.

Não inclui
- Editar IDL/IR no console.
- Criar proposals (isso entra na Etapa 3.4/3.5).

## Regras não negociáveis

- Console não pode oferecer operações mutáveis do runtime como ações diretas.
- Dados exibidos devem apontar para evidências (arquivos/ledger/events) e não “estado implícito”.

## Entregas mínimas

1) Páginas
- Home/Select: escolher instituição e dept (lista)
- Status: modo do runtime, drift, freeze/emergency, pinned_release_id
- Bundles: mostrar bundle atual, manifest, contract_ledger, links para proof verify
- Legacy (read-only): listar legacy assets registrados (mínimo)

2) Endpoints necessários
- Se não existirem, criar endpoints read-only mínimos:
  - listar instituições
  - listar departamentos carregados
  - status runtime por instituição/dept
  - listar legacy assets (por instituição/dept)

3) Testes
- Testes mínimos de API (se criar endpoints)
- Smoke test do console (opcional)

## Definition of Done

- Um operador consegue entrar, selecionar instituição+dept e ver:
  - status (ACTIVE/SAFE_MODE)
  - drift/freeze/emergency
  - pinned_release_id
  - contratos do bundle (manifest + contract_ledger)
  - legacy assets read-only

