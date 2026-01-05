# release/release_checklist.py — Checklist de Release (gates finais)

## Objetivo
Aplicar gates finais e bloquear release quando qualquer item obrigatório faltar.

## Itens obrigatórios
- Artefatos presentes: SRS/IR/OAS/RBAC/PLAN.
- Hashes completos no run log.
- Build ok.
- Smoke ok.
- Blueprint registrado.
- Regras absolutas respeitadas (paths, não auto-modificar engine, não alterar templates).

## Aceite (Dia 5)
- Qualquer item faltando → FAIL.
