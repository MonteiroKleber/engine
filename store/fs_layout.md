# Store File System Layout

Este documento descreve a estrutura de diretórios e arquivos do artifacts store.

## Estrutura Geral

```
store_data/
├── {project}/
│   ├── SRS/
│   │   ├── v1.json
│   │   ├── v2.json
│   │   └── ...
│   ├── IR/
│   │   ├── v1.json
│   │   ├── v2.json
│   │   └── ...
│   ├── OAS/
│   │   ├── v1.yaml
│   │   ├── v2.yaml
│   │   └── ...
│   ├── RBAC/
│   │   ├── v1.json
│   │   ├── v2.json
│   │   └── ...
│   ├── PLAN/
│   │   ├── v1.json
│   │   ├── v2.json
│   │   └── ...
│   ├── logs/
│   │   └── (arquivos de log internos)
│   └── runs/
│       ├── {execution_id}_{timestamp}.json
│       └── ...
```

## Tipos de Artefatos (Kinds)

| Kind | Extensao | Descricao |
|------|----------|-----------|
| SRS  | .json    | Software Requirements Specification |
| IR   | .json    | Intermediate Representation |
| OAS  | .yaml    | OpenAPI Specification 3.0 |
| RBAC | .json    | Role-Based Access Control definitions |
| PLAN | .json    | Implementation Plan com tasks |

## Versionamento

- Cada artefato segue o padrao `v{N}.{ext}` onde N comeca em 1
- Versoes sao imutaveis - uma vez criada, nao pode ser alterada
- Nova execucao sempre incrementa a versao
- Todas as versoes de uma execucao devem coincidir (SRS v3, IR v3, OAS v3, RBAC v3, PLAN v3)

## Run Logs

Os logs de execucao sao salvos em `runs/` com o formato:

```
{execution_id}_{timestamp}.json
```

Conteudo do log:
```json
{
  "execution_id": "project_abc123",
  "timestamp": "2024-01-01T12:00:00.000Z",
  "payload": {
    "status": "completed",
    "result": { ... },
    "input_hash": "abc123...",
    "srs_hash": "def456...",
    "ir_hash": "ghi789...",
    "oas_hash": "jkl012...",
    "rbac_hash": "mno345...",
    "plan_hash": "pqr678..."
  }
}
```

## Schemas

Os schemas JSON para validacao estao em `/schemas/`:

- `srs.schema.json` - Schema do SRS
- `ir.schema.json` - Schema do IR
- `rbac.schema.json` - Schema do RBAC
- `plan.schema.json` - Schema do PLAN
- `blueprint.schema.json` - Schema de classificacao de blueprint

## Convencoes

1. **Projetos**: Nomes em snake_case ou kebab-case
2. **Kinds**: Sempre em MAIUSCULAS (SRS, IR, OAS, RBAC, PLAN)
3. **Versoes**: Sempre numericas sequenciais (v1, v2, v3...)
4. **Timestamps**: ISO 8601 format
5. **Hashes**: SHA256 truncado em 16 caracteres
