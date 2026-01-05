# Prompt — Dia 3: Domain Modeler Agent (SRS → IR)

Implemente a Tarefa 4.3 (Dia 3) da Semana 4.

Criar `agents/domain_modeler.py` com `DomainModeler.generate_ir(srs: dict) -> dict`.

Regras fixas (determinístico v1, sem LLM):
- meta.project_name = srs.meta.project_name
- meta.version: NÃO definir aqui (engine define no final via `next_version` do IR)

- domain.entities:
  - para cada item de `srs.data_requirements`:
    - name = entity
    - primary_key = "id" se não houver
    - fields: required conforme SRS; unique/indexed default false

- domain.relations: vazio
- domain.workflows: vazio

- domain.rules:
  - converter `srs.business_rules` em rules com severity `ERROR` por padrão

- api_intent.resources:
  - nomes das entidades (sem duplicar)

- ui.pages:
  - páginas CRUD mínimas por entidade:
    - /app/<entidade>/list
    - /app/<entidade>/new
    - /app/<entidade>/:id
  - components/actions mínimos (strings)

- nfr:
  - refletir `srs.non_functional_requirements.security.auth_required`
  - refletir `audit_log_required`

Regras de bloqueio:
- Nada de inferir entidades não citadas.
- Se o SRS vier sem `data_requirements` (ou sem entidades), gerar IR propositalmente inválido para bloquear (deve falhar no `ir_validator`).

Critério de aceite:
- Com SRS contendo entidades: IR passa no schema.
- Sem entidades: IR falha validação.
