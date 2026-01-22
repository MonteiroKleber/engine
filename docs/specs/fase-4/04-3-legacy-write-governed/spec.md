# Fase 4 — Etapa 4.3: Legacy Bridge Write-Mode (Governado)

**Data:** 2026-01-19  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.3)

## Objetivo

Evoluir o Legacy Bridge de read-only para **1 ação de escrita governada**, com risco controlado:

- ação write encapsulada (um “ato”) com parâmetros explícitos
- approvals/SoD/mandates/policies para permitir ou bloquear
- trilha completa no ledger: intent → decisão → execução → resultado

## Escopo

Inclui
- Um conector write-mode mínimo (escolha canônica para MVP): **Outbox File Connector**
  - EDAP escreve um arquivo de “comando” (outbox) em formato determinístico
  - um aplicador externo (fora do engine) consome e aplica no legado
  - o engine registra ack/resultado quando receber confirmação (opcional nesta etapa)
- Endpoints governados do bridge:
  - `POST /bridge/write/{action}` (ex.: `increase_limit`)
- Governança aplicada:
  - mandates/autonomy/policies + approvals + SoD

Não inclui
- escrever direto no DB do legado
- RPA
- múltiplas ações write

## Regras não negociáveis

- A ação write deve ser um “ato único” com input canônico (JSON ordenado) e hash.
- Não existe execução write sem:
  - mandate válido
  - approvals quando configurado
  - ledger event
- Outbox deve ser per-institution/per-dept (isolamento).

## Deliverables

1) Modelo de ação write (contract)
- `LegacyWriteAction` com:
  - `action_id`, `action_type`
  - `params` (schema mínimo)
  - `intent_sha256`
  - `requested_by` (actor)
  - `created_at`

2) Implementação
- `engine.legacy_bridge` ganha write connector outbox
- endpoint governado para enfileirar write
- ledger events:
  - `LEGACY_WRITE_INTENT_CREATED`
  - `LEGACY_WRITE_ALLOWED` / `LEGACY_WRITE_DENIED`
  - `LEGACY_WRITE_ENQUEUED`
  - (opcional) `LEGACY_WRITE_ACKED`

3) Testes
- write permitido cria arquivo no outbox e eventos
- write negado não cria arquivo e registra deny
- isolamento por institution/dept

## Definition of Done

- Existe 1 ação write governada end-to-end até outbox.
- Auditor consegue provar offline o que foi pedido e por quê foi permitido.
