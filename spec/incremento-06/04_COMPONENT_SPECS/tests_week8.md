# Tests — Semana 8

## tests/test_error_classifier.py
- cobre padrões de mensagens → enum correto

## tests/test_fix_patch_generator.py
- gera 1 patch
- patch não reescreve arquivo inteiro
- patch aponta para generated

## tests/test_fix_loop_agent.py
- max 3 tentativas
- 1 patch por tentativa

## tests/test_pipeline_autonomous_build.py
- build falha → fix loop tenta
- build passa em caso simples
- ou falha com status correto
