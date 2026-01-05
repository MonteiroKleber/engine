# Prompt — Dia 3: Normalizer + Blueprint Classifier

Implemente `intake/normalizer.py` (determinístico, sem LLM):
- trim
- remover espaços duplicados
- limitar tamanho (20k chars)
- separar linhas em bullets

Implemente `intake/blueprint_classifier.py` (determinístico inicial):
- sempre retornar blueprint genérico:
  - mode: "FORCED_GENERIC"
  - confidence: 0.0
  - candidates: [{"blueprint_id":"generic","score":1.0}]
  - reasons: ["classifier_not_enabled_v1"]

Aceite:
- intake sempre seleciona generic.
