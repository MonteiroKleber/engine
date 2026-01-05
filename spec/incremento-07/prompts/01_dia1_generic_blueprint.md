# Prompt — Dia 1: Definição formal do Blueprint Genérico

Implemente o Dia 1 da Semana 9.

Criar:
- `/home/bazari/engine/blueprints/generic_blueprint.py`

Responsabilidade:
- NÃO cria entidades
- NÃO cria endpoints
- NÃO cria tarefas novas
- NÃO altera IR/OAS/PLAN
- Apenas organiza e ordena o que já existe

Interface obrigatória:
```py
class GenericBlueprint:
    def apply(ir, oas, rbac, plan) -> plan
```

Regra:
- `apply` = no-op estruturado (retorna o PLAN original, possivelmente reordenado, nunca expandido).
