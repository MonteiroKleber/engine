# Estrutura e paths (Semana 7)

## Diretórios e ownership

### Templates (fora do engine)
- Path: `/home/bazari/templates/`
- Regra: apenas arquivos estáticos.
- Regra: o engine nunca escreve aqui.

Estrutura exigida:
/home/bazari/templates/
├── spring-boot/
├── react-vite/
├── postgres-flyway/
└── docker/

### Output gerado
- Path: `/home/bazari/generated/<project>/`
- Único local permitido para escrita por geração/aplicação de patches.

Resultado esperado:
/home/bazari/generated/demo/
├── backend/
├── frontend/
├── db/
└── docker-compose.yml

### Engine (código do motor)
- Path: `/home/bazari/engine/`
- Regra: Patch Engine não pode escrever aqui.

## Store / Run log
- Esta semana o foco é `/home/bazari/generated/`.
- Run log deve registrar:
  - `repo_path: /home/bazari/generated/<project>`
  - `patch_count`
  - `build_ok`
