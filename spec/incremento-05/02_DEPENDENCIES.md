# Pré-requisitos de build e ambiente

## Requisitos do sistema (execução local)
O build validator executa comandos e exige que existam no ambiente:
- Backend: `mvn` (Maven)
- Frontend: `npm` (Node.js)

## Semana 7
- Não adicionar dependências Python novas para suportar build.
- O build deve ser executado dentro do diretório gerado:
  - `/home/bazari/generated/<project>/backend`
  - `/home/bazari/generated/<project>/frontend`

## Critério de aceite do build
- Repo vazio (templates puros) passa no build:
  - `mvn test`
  - `npm ci` e `npm run build`
