# GAP 3 — Eliminar “self-approved” e decisões implícitas em writes críticos

## A) Resumo de correção (rastreabilidade)

- **Intenção original (spec anterior):** remover `approved_by=self` no legacy write e exigir approval real ou role explícita.
- **Intenção corrigida (produção no cliente):** nenhum write crítico pode ser concluído sem ato formal (approval) **ou** autoridade explícita declarada (RBAC + mandate), e isso deve ser **enforçado por default em produção**, não opcional.
- **Impacto:** o Legacy Bridge write deixa de ser “ato auto-aprovado” e vira um fluxo institucional verificável.

### O que foi mantido
- “Outbox only”: o engine nunca aplica direto no legado.
- Ledger registra intent/decisão/outcome.

### O que foi alterado
- Em produção, o caminho “role explícita” não pode ser implícito. Se usado, deve ser verificável (RBAC/mandate) e registrado como tal.
- Para ações críticas, o default é **approval required** quando policy existir; se policy não existir, o default seguro é **deny** (não “self-approve”).

### O que foi descartado por viés de “piloto”
- “Self-approved in this MVP”.

## B) Spec técnica corrigida (contrato)

### Objetivo
Eliminar caminhos de write crítico com decisão implícita:

- write crítico deve resultar em **PENDING_APPROVAL** ou **ENQUEUED** com base em regras explícitas
- nunca “approved_by = requester” sem ato formal

### Estado atual (com arquivos/linhas reais)
- Finance já usa approvals antes de commit:
  - `src/engine/api/finance.py:230-270` (approval policy / emit)
- Legacy write:
  - marca “approved_by” como o próprio ator:
    - `src/engine/legacy_bridge/write_registry.py:302-314`
  - não integra approvals/SoD:
    - `src/engine/legacy_bridge/write_registry.py:245-296`

### Mudanças necessárias (mínimas)
1) **Remover auto-aprovação**
   - `approved_by` não pode ser setado automaticamente como requester.

2) **Definir comportamento canônico para write crítico**
   - Para `POST /bridge/write/{action}` (mínimo: `increase_limit`):
     - Se houver uma regra de approvals configurada para esse `endpoint_sig` (no dept corrente), então:
       - criar approval request (via approvals subsystem) e retornar `202 PENDING_APPROVAL` com `approval_id`
       - somente após `POST /approvals/{approval_id}/decide` (já existente) o engine enfileira outbox
     - Se não houver regra de approvals:
       - em produção (`ENGINE_INSTALL_MODE=prod`): negar deterministicamente (não “auto-approve”)
       - em dev: permitir apenas se houver role explícita `admin` + mandate válido (para não quebrar dev)

3) **Ledger events (prova)**
   - Para legacy write, registrar:
     - intent created
     - approval requested/decided (se aplicável)
     - allowed/denied (por gate)
     - enqueued (somente após approval, quando requerido)

### Restrições explícitas (o que NÃO mudar)
- Continua sendo outbox.
- Não criar “atalho” para escrever no legado diretamente.
- Não inventar heurística (“se parece crítico então…”). Criticidade é determinada pelo endpoint/action_type.

### Eventos de ledger afetados
- `LEGACY_WRITE_INTENT_CREATED`, `LEGACY_WRITE_DENIED`, `LEGACY_WRITE_ENQUEUED` já existem.
- Adicionar (se necessário) um evento explícito de “approval required” no contexto do write:
  - ex.: `LEGACY_WRITE_APPROVAL_REQUESTED` com `approval_id`

### Riscos técnicos
- Integrar approvals no legacy write precisa resolver:
  - onde armazenar approval request (já existe subsystem)
  - como correlacionar approval_id ↔ action_id
  - evitar que alguém “decida” approval sem mandato/role

### Impacto esperado
- Writes críticos deixam de ser “auto-aprovados” e ficam auditáveis como atos.

## C) Critérios de aceite (produção)

- `approved_by` não é mais auto-preenchido com o requester sem approval formal.
- Para `increase_limit`:
  - com approvals configurados: request retorna `202` + `approval_id` e **não** cria outbox até decidir.
  - após decide (approve): cria outbox determinístico.
  - após decide (reject): não cria outbox e registra evento.
- Em `ENGINE_INSTALL_MODE=prod`, sem approvals configurados: deny determinístico (não “self-approved”).
- Testes automatizados cobrem os 3 cenários.

## D) Prompt para Claude Code (ver `prompts.md`)
