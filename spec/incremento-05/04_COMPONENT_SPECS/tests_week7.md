# Tests — Semana 7

## tests/test_patch_rules.py
- path traversal bloqueado
- escrita fora de generated bloqueada
- escrita em engine/templates bloqueada
- rewrite >80% bloqueado

## tests/test_patch_apply_rollback.py
- patch inválido → rollback imediato
- patch válido aplica e mantém alterações

## tests/test_pipeline_to_repo_build.py
- pipeline cria repo gerado
- aplica patches
- build validator roda
- falha → rollback; sucesso → build_ok
