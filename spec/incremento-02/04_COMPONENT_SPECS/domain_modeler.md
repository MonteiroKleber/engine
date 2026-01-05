# agents/domain_modeler.py — Especificação

## Objetivo
Transformar SRS → IR de forma determinística v1 (sem LLM).

## API
- `class DomainModeler:`
  - `generate_ir(srs: dict) -> dict`

## Regras fixas (determinístico v1)
### meta
- `meta.project_name = srs.meta.project_name`
- `meta.version` **não** é definido aqui (engine define no final usando `next_version` do IR)

### domain.entities
Para cada item em `srs.data_requirements`:
- criar entidade com `name = entity`
- `primary_key = "id"` se não houver
- mapear `fields` com:
  - `required` conforme SRS
  - `unique=false` e `indexed=false` por padrão

### domain.relations
- vazio por padrão nesta versão

### domain.workflows
- vazio por padrão nesta versão

### domain.rules
- converter `srs.business_rules` em `rules` com `severity="ERROR"` por padrão

### api_intent.resources
- lista com nomes de entidades (sem duplicar)

### ui.pages
Gerar páginas CRUD mínimas por entidade:
- `/app/<entidade>/list`
- `/app/<entidade>/new`
- `/app/<entidade>/:id`

Incluir `components/actions` mínimos (strings) consistentes (ex.: `create`, `update`, `delete`, `view`, `list`).

### nfr
Refletir:
- `srs.non_functional_requirements.security.auth_required`
- `srs.non_functional_requirements.security.audit_log_required`

## Regras de bloqueio (importante)
- Nada de inferir entidades não citadas.
- Se o SRS não tem `data_requirements` (ou vier sem entidades), o DomainModeler deve produzir um IR que **falha validação por schema** (para bloquear o pipeline).

## Critério de aceite (Dia 3)
- Quando SRS tem entidades: IR passa no schema.
- Quando SRS não tem entidades: IR falha validação.
