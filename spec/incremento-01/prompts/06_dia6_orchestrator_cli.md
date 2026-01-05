# Prompt — Dia 6: Orchestrator mínimo + CLI

Implemente `orchestrator/engine.py` com pipeline até SRS:
- normalize
- classify blueprint
- req_analyst → SRS
- validate SRS
- salvar SRS (vN)
- escrever run log

Implemente `main.py` CLI:
- comando: `python main.py --project <name> --input "<texto>"`
- imprime resumo do run
- salva artefato e log

Aceite:
- `python main.py --project demo --input "quero um sistema..."` cria `store_data/demo/SRS/v1.json` e um run log.
