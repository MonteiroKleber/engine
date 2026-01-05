# Prompt — Dia 7: Testes + Demo

Implemente o Dia 7 da Semana 7.

Testes em `/home/bazari/engine/tests/`:
- `test_patch_rules.py`
- `test_patch_apply_rollback.py`
- `test_pipeline_to_repo_build.py`

Demo CLI:
```bash
cd /home/bazari/engine
python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"
```

Resultado obrigatório:
- `/home/bazari/generated/demo/`
- backend compila
- frontend compila
- `docker-compose.yml` existe

Regra final (fixada):
- O motor nunca se auto-modifica.
- Templates nunca são alterados.
- Tudo que é gerado vai para `/home/bazari/generated/`.
