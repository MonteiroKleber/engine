# Fase 3 — Etapa 3.3: Prova Offline no Console (UX + Export)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.3)

## Objetivo

Melhorar a experiência de **prova offline** dentro do console, mantendo read-only:

- mostrar o resultado do `engine.proof verify` com detalhes acionáveis
- permitir export do report (JSON)
- permitir comparar bundles (opcional, se já houver dados)

## Contexto

A Etapa 3.2 já adicionou `/console/proof` com PASS/FAIL. Agora a 3.3 foca em UX e evidências:
- lista de verificações (manifest, ledger, contracts)
- erros com códigos (`PROOF_*`) e explicação
- links diretos para contract_detail quando houver mismatch

## Escopo

Inclui
- Refinar página `/console/proof`:
  - detalhar checks e failures
  - exportar JSON report (download)
  - exibir âncoras (`source_idl_sha256`, `manifest_hash`, pinned_release_id)
- Tornar o report legível para auditor/CTO.

Não inclui
- executar ações de correção
- proposals

## Regras não negociáveis

- Read-only.
- Não executar runtime nem pipeline.
- Prova deve rodar somente sobre arquivos do bundle.

## Entregas mínimas

1) UI
- `/console/proof` com:
  - tabela de checks
  - lista de divergências
  - links para `/console/contracts/{file}`
- `/console/proof.json` (ou query `?format=json`) para export.

2) Testes
- PASS para bundle válido
- FAIL com contract tampered mostra o erro e aponta o arquivo
- Export JSON funciona e é estável

## Definition of Done

- Auditor consegue abrir o console, rodar prova e exportar report com detalhes e evidências.
