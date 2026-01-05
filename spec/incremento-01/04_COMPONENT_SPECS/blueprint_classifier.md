# intake/blueprint_classifier.py — Especificação

## Objetivo
Classificador determinístico inicial (placeholder).

## Comportamento
Sempre retorna:
- `mode: "FORCED_GENERIC"`
- `confidence: 0.0`
- `candidates: [{"blueprint_id":"generic","score":1.0}]`
- `reasons: ["classifier_not_enabled_v1"]`

## Observação
- Nesta semana a classificação não deve variar com o texto.
