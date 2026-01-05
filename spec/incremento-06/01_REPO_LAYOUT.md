# Estrutura e paths (Semana 8)

## Diretórios fixos
- Engine: `/home/bazari/engine/`
- Templates: `/home/bazari/templates/`
- Output: `/home/bazari/generated/<project>/`

## Novos arquivos/pastas (no engine)
- `/home/bazari/engine/fix_loop/error_classifier.py`
- `/home/bazari/engine/fix_loop/fix_loop_agent.py`
- `/home/bazari/engine/fix_loop/fix_patch_generator.py`

## Arquivos atualizados
- `/home/bazari/engine/compilers/backend_compiler.py`
- `/home/bazari/engine/compilers/frontend_compiler.py`
- `/home/bazari/engine/orchestrator/engine.py`

## Segurança
- Qualquer patch aplicado deve ter alvo sob `/home/bazari/generated/<project>/`.
- Fix loop não pode criar novas entidades nem mudar contrato (OAS/RBAC).
