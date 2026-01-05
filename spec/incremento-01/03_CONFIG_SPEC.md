# Configuração (config/engine.yaml)

## Campos obrigatórios
- `store_root: ./store_data`
- `project_default_language: pt-BR`
- `intake.max_questions_per_round: 7`
- `intake.blueprint_confidence_threshold: 0.85`

## Exemplo recomendado
```yaml
store_root: ./store_data
project_default_language: pt-BR
intake:
  max_questions_per_round: 7
  blueprint_confidence_threshold: 0.85
llm:
  enabled: false
```

Notas:
- `llm.enabled` não foi listado como obrigatório na demanda, mas é recomendado explicitar para evitar ambiguidade no comportamento do `req_analyst`.
