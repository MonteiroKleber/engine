# blueprints/generic_blueprint.py — GenericBlueprint

## Objetivo
Garantir um blueprint genérico seguro e determinístico para operar sem blueprint específico.

## Responsabilidade
O `GenericBlueprint`:
- NÃO cria entidades
- NÃO cria endpoints
- NÃO cria tarefas novas
- NÃO altera IR/OAS/PLAN
- Apenas organiza e ordena o que já existe

## Interface obrigatória
```py
class GenericBlueprint:
    def apply(ir, oas, rbac, plan) -> plan
```

## Semântica
- `apply` é um no-op estruturado.
- Retorna o PLAN original, possivelmente reordenado.
- Nunca expande tasks.

## Determinismo
- Mesmos inputs → mesmo PLAN (mesma ordem).

## Critério de aceite (Dia 1)
- `apply` não altera conteúdo, apenas ordem (se aplicável).
- Não cria elementos.
