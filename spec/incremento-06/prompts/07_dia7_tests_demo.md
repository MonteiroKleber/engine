# Prompt — Dia 7: Testes + Demo funcional (o “uau”)

Implemente o Dia 7 da Semana 8.

Criar testes obrigatórios:
- `tests/test_error_classifier.py`
- `tests/test_fix_loop_agent.py`
- `tests/test_fix_patch_generator.py`
- `tests/test_pipeline_autonomous_build.py`

Cobrir:
- erro → classificação
- classificação → patch
- patch → build ok
- limite de tentativas

Demo CLI FINAL:
```bash
python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"
```

Resultado esperado:
- Backend sobe
- Frontend sobe
- CRUD funcional
- Nenhum erro manual
- Fix Loop acionado se necessário

Critério:
- Testes verdes.
- Nenhuma violação de contrato ou path.
