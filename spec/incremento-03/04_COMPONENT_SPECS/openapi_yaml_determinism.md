# OpenAPI YAML — Determinismo e hash

## Objetivo
Garantir que `oap_hash` seja estável para a mesma entrada/IR.

## Recomendação de geração (determinística)
- Gerar OpenAPI como dict e serializar com `yaml.safe_dump`.
- Configuração recomendada:
  - `sort_keys=True`
  - `default_flow_style=False`
  - `allow_unicode=True`
- Normalizar newline: gravar arquivo usando `\n`.

## Hash
- `oap_hash` deve ser `sha256` dos bytes UTF-8 **exatamente como gravados** em `store_data/{project}/OAS/vN.yaml`.
