# Run log — Hashes e reprodutibilidade

## Objetivo
Garantir que a demo da Semana 4 seja reproduzível e rastreável por hashes.

## Algoritmo
- Hash: `sha256`.

## O que hashear
- `input_hash`: hash do input **normalizado**.
- `srs_hash`: hash do SRS persistido (JSON canonicalizado).
- `ir_hash`: hash do IR persistido (JSON canonicalizado).

## Canonicalização JSON (recomendação firme)
- `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`
- UTF-8 bytes

## Campos mínimos no run log (Semana 4)
- `input_hash`, `srs_hash`, `ir_hash`
- paths/versions de SRS e IR
