# Etapa 06 — Multi-instituição e Admin Security

Objetivo
- Garantir multi-tenant real, isolamento físico e administração governada por instituição.

Escopo
- Criação e registry append-only de instituições (admin API).
- Header obrigatório `X-Institution-Id` no runtime.
- Isolamento total por institution_id de:
  - ledger
  - state_store
  - bundles
  - dev-runs
  - admin keys
- `institution_config` v1.3 com freeze/emergency/rate limit/allow-deny governado.

Saídas (artefatos)
- `docs/specs/fase-1/06-multi-institution-admin/isolation.md`
  - modelo de isolamento, paths e garantias.
- `docs/specs/fase-1/06-multi-institution-admin/admin-auth.md`
  - chaves, rotação, revogação, auditoria.

Definition of Done (Etapa 06)
- Evidência de que um tenant não consegue ver/interferir/inferir outro.
- Admin de uma instituição não administra outra, com eventos auditáveis.

