# repo/repo_generator.py — Repo Generator

## Objetivo
Criar um repositório gerado (por projeto) a partir dos templates.

## Local
- `/home/bazari/engine/repo/repo_generator.py`

## API obrigatória
```py
create_repo(
  project: str,
  templates_root="/home/bazari/templates",
  output_root="/home/bazari/generated",
)
```

## Resultado esperado
- `/home/bazari/generated/<project>/backend/`
- `/home/bazari/generated/<project>/frontend/`
- `/home/bazari/generated/<project>/db/`
- `/home/bazari/generated/<project>/docker-compose.yml`

## Regras
- Nenhum arquivo fora de `/home/bazari/generated/`.
- Pode sobrescrever um output existente apenas via estratégia explícita (ex.: limpar output_root/project antes) — documentar e garantir segurança.

## Critério de aceite (Dia 2)
- Diretório criado corretamente.
- Nenhum arquivo fora de `generated/`.
