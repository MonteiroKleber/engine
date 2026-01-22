# GAP 4 — Agentes IA como atores governados (cadeia de delegação + auto-solicitação)

## A) Resumo de correção (rastreabilidade)

- **Intenção original (spec anterior):** adicionar `on_behalf_of` e gerar “auto-request” quando negado, começando por legacy write.
- **Intenção corrigida (produção no cliente):** transformar o “agente” em um ator que **nunca executa fora de mandato/approval**, e que quando bloqueado **gera solicitação institucional rastreável** (approval/proposal request) ao invés de tentar executar. Isso precisa ser operável (admin consegue ver e agir) e auditável (ledger).
- **Impacto:** o produto suporta “agente governado” em produção, sem narrativa.

### O que foi mantido
- Escopo mínimo: começar por `POST /bridge/write/{action}`.
- Sem IA como autoridade: agent não altera contratos nem executa fora do que foi declarado.

### O que foi alterado
- Em produção, `on_behalf_of` precisa estar acoplado à identidade não-spoofável (GAP 2), não a headers livres.
- “Auto-request” deve ser um artefato institucional persistido e visível no console/admin, não apenas log.

### O que foi descartado por viés de “piloto”
- Criar “requests” sem persistência e sem rotas para o operador agir.

## B) Spec técnica corrigida (contrato)

### Objetivo
Agente como solicitante institucional governado:

- Implementar cadeia mínima de delegação (`on_behalf_of`)
- Quando bloqueado, gerar solicitação governada (não executar)
- Ledger registra tentativa, bloqueio e solicitação

### Estado atual (com arquivos/linhas reais)
- ActorContext existe, mas hoje pode ser spoofado (GAP 2):
  - `src/engine/core/actor_context.py:39-85`
- Mandates são o mecanismo de delegação por endpoint/phase:
  - `src/engine/core/mandates.py:1-8`
- Agent Ops (observabilidade) já existe:
  - `src/engine/agent_ops/read_model.py`
  - `src/engine/console/routes.py` (agents/denied)
- Não existe `on_behalf_of` estruturado nem storage de “agent requests”.

### Mudanças necessárias (mínimas)
1) **Delegation chain: `on_behalf_of`**
   - Introduzir `X-On-Behalf-Of` (header) ou campo equivalente no request.
   - Enforce:
     - apenas atores registrados como “agent” podem enviar `on_behalf_of`
     - `on_behalf_of` deve ser um `actor_id` válido (mesmo formato do sistema)
   - Persistir `on_behalf_of` no ledger payload para eventos relevantes de gates (pelo menos nas rotas de write crítico).

2) **Auto-solicitação (deny → request)**
   - Quando um agente for negado em endpoint mutável (escopo mínimo: legacy write):
     - criar um registro append-only de solicitação:
       - `institutions/<id>/agent_requests/requests.jsonl`
       - `institutions/<id>/agent_requests/state.json` (lookup)
     - payload mínimo:
       - `request_id`, `created_at`
       - `institution_id`, `dept_id`
       - `agent_actor_id`, `on_behalf_of`
       - `endpoint_sig`, `action_type`
       - `deny_code` (ex.: `MANDATE_DENIED`, `AUTONOMY_INSUFFICIENT`, `POLICY_DENIED`)
       - `deny_details` (campos estruturados, sem texto livre inferido)
   - Emitir evento no ledger:
     - `AGENT_REQUEST_CREATED` (case_id = request_id)

3) **Integração com o operador**
   - Sem criar UI nova grande: expor endpoints admin read-only mínimos para listar/consultar requests.
   - Console pode linkar (futuro), mas para esta fase o importante é persistir + ledger.

### Restrições explícitas (o que NÃO mudar)
- Agente não vira autoridade.
- Não criar um “auto-fix” de mandates/policies.
- Não criar execução probabilística.

### Eventos de ledger afetados
- Adicionar:
  - `AGENT_REQUEST_CREATED`
- Atualizar payloads de eventos de gate (apenas onde necessário) para incluir `on_behalf_of` quando presente.

### Riscos técnicos
- A validação de “agent” depende de um registry confiável (GAP 2/GAP 4).
- Evitar que `on_behalf_of` vire canal de spoof.

### Impacto esperado
- Agente passa a operar como solicitante institucional e deixa rastros formais quando bloqueado.

## C) Critérios de aceite (produção)

- `on_behalf_of` só é aceito para atores marcados como agent; caso contrário, deny determinístico.
- `on_behalf_of` válido aparece no ledger (payload) em eventos relevantes do legacy write.
- Um deny de legacy write por agente gera:
  - registro append-only em `agent_requests/requests.jsonl`
  - evento `AGENT_REQUEST_CREATED`
  - e **não** enfileira outbox
- Testes automatizados cobrem os cenários acima.

## D) Prompt para Claude Code (ver `prompts.md`)
