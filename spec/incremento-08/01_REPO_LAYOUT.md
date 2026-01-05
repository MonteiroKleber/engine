# Estrutura e integração (Semana 10)

## Paths fixos
- Engine: `/home/bazari/engine/`
- Templates: `/home/bazari/templates/`
- Output: `/home/bazari/generated/<project>/`
- Store: `/home/bazari/store_data/` (ou `store_root` do engine)

## Novos arquivos (no engine)
- `/home/bazari/engine/release/qa_release_agent.py`
- `/home/bazari/engine/release/release_checklist.py`
- `/home/bazari/engine/VERSION`
- `/home/bazari/engine/RELEASE_NOTES.md`

## Arquivos atualizados
- `/home/bazari/engine/orchestrator/engine.py` (modo release)
- `/home/bazari/generated/<project>/docker-compose.yml` (gerado/garantido pelo pipeline)

## Artefatos de smoke
- `/home/bazari/generated/<project>/smoke/` (logs/relatórios)
