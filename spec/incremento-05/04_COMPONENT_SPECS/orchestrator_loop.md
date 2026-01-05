# orchestrator/engine.py — Loop real (Semana 7)

## Objetivo
Executar o loop real: gerar repo → gerar patches → aplicar → build → rollback/sucesso.

## Ordem fixa
1) Criar repo em `/home/bazari/generated/<project>` (Repo Generator)
2) Gerar patches (Patch Generator v1)
3) Aplicar patches (Patch Engine)
4) Rodar Build Validator
5) Falhou → rollback
6) Passou → SUCCESS

## Run log (obrigatório)
- `repo_path: /home/bazari/generated/<project>`
- `patch_count`
- `build_ok`
