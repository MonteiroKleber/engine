# Prompt — Dia 2: Repo Generator

Implemente o Dia 2 da Semana 7.

Criar `/home/bazari/engine/repo/repo_generator.py`.

Função obrigatória:
```py
create_repo(
  project: str,
  templates_root="/home/bazari/templates",
  output_root="/home/bazari/generated",
)
```

Resultado esperado:
/home/bazari/generated/demo/
├── backend/
├── frontend/
├── db/
└── docker-compose.yml

Critério de aceite:
- Diretório criado corretamente.
- Nenhum arquivo fora de `generated/`.
