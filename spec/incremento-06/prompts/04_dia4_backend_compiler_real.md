# Prompt — Dia 4: Compilers Reais (Backend)

Implemente o Dia 4 da Semana 8.

Atualizar:
- `/home/bazari/engine/compilers/backend_compiler.py`

Agora o backend compiler deve gerar:
- JPA Entity completa
- Repository funcional
- Service com CRUD real
- Controller com:
  - validação
  - mapeamento DTO ↔ Entity
  - annotations de segurança (`@PreAuthorize`)

Tudo derivado do IR + OAS + RBAC.

Regra:
- Ainda sem business rules complexas.

Critério de aceite:
- Backend sobe.
- Endpoints respondem.
- Security ativa.
