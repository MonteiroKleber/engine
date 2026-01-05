# Contexto e Escopo

## Objetivo da Semana 7
Gerar código real com:
- templates externos (fora do engine)
- patches seguros
- rollback automático
- build validado

## Componentes a implementar
- Templates estáticos em `/home/bazari/templates/`.
- Repo generator: `/home/bazari/engine/repo/repo_generator.py`.
- Patch engine blindado: `/home/bazari/engine/patch_engine/`.
- Build validator (repo gerado): `/home/bazari/engine/validators/build_validator.py`.
- Patch generator v1: `/home/bazari/engine/compilers/patch_generator_v1.py`.
- Loop real no engine: `/home/bazari/engine/orchestrator/engine.py`.
- Testes: `/home/bazari/engine/tests/`.

## Regras finais (fixadas)
- O motor nunca se auto‑modifica.
- Templates nunca são alterados.
- Tudo que é gerado vai para `/home/bazari/generated/`.

## Critério de pronto (Semana 7 concluída)
- `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`:
  - cria `/home/bazari/generated/demo/`
  - backend compila (`mvn test`)
  - frontend compila (`npm ci` + `npm run build`)
  - `docker-compose.yml` existe
- Testes:
  - `test_patch_rules.py`
  - `test_patch_apply_rollback.py`
  - `test_pipeline_to_repo_build.py`
  - `pytest` verde
