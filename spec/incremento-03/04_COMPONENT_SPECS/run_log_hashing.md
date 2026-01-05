# Run log — Hashes (Semana 5)

## Objetivo
Rastreabilidade e reprodutibilidade por hashes para contratos.

## Hashes obrigatórios
- `oap_hash`: hash do arquivo YAML salvo (`OAS/vN.yaml`), bytes UTF-8 exatos.
- `rbac_hash`: hash do JSON canonicalizado do RBAC (recomendado) ou bytes exatos do arquivo salvo (escolher 1 e padronizar).

## Recomendação para consistência
- Para RBAC: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` → sha256.
- Para OAS: garantir que o YAML gerado use `\n` e seja sempre o mesmo para o mesmo IR.
