# Plano de testes (Semana 8)

## Unitários (novos)
- `tests/test_error_classifier.py`
- `tests/test_fix_loop_agent.py`
- `tests/test_fix_patch_generator.py`

Cobrir:
- erro → classificação fechada
- classificação → 1 patch mínimo
- limite de tentativas (max 3)

## Integração (novo)
- `tests/test_pipeline_autonomous_build.py`

Cobrir:
- pipeline gera repo
- build falha em caso controlado
- fix loop aplica patch e retry
- build passa (casos simples) ou falha com status correto
- sem violar paths

## Demo
`python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`
- backend sobe
- frontend sobe
- CRUD funcional
- fix loop acionado se necessário
