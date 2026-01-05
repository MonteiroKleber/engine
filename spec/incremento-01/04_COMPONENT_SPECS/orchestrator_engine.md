# orchestrator/engine.py — Especificação

## Objetivo
Pipeline mínimo até SRS.

## Etapas (ordem fixa)
1) normalize (`intake/normalizer.py`)
2) classify blueprint (`intake/blueprint_classifier.py`)
3) req_analyst gera SRS (`intake/req_analyst.py`)
4) validate SRS (`validators/srs_validator.py`)
5) se válido: salvar SRS como `vN.json` (`store/artifacts_store.py`)
6) escrever run log (sempre), em `runs/{execution_id}.json`

## Output
- retornar um resultado resumido (para CLI imprimir)
- incluir: `execution_id`, `project`, `blueprint`, `validation.ok`, `saved_version` (se houver), `questions` (se inválido), `paths` (SRS/log)
