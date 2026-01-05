# Run log — plan_hash

## Objetivo
Rastrear o PLAN versionado por hash.

## Hash obrigatório
- `plan_hash`: sha256 do conteúdo do arquivo `PLAN/vN.json` salvo.

## Recomendação para estabilidade
- Canonicalização JSON:
  - `json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`
  - UTF-8

## Critério
- `plan_hash` deve bater com o arquivo salvo.
