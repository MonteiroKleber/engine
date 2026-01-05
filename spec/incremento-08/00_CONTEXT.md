# Contexto e Escopo

## Objetivo imutável da Semana 10
Executar texto → sistema rodando (docker-compose), com:
- QA/Release Agent
- smoke tests
- docker-compose final
- gates finais (checklist de release)
- congelamento do Motor v1.0

## Contexto fixo
/home/bazari/
├── engine/
├── templates/
├── generated/
└── store_data/

## Componentes a implementar/atualizar
- `release/qa_release_agent.py`
- `release/release_checklist.py`
- `engine/orchestrator/engine.py` (modo `--release`)
- docker-compose final no repo gerado
- smoke tests (backend + frontend)
- congelamento v1.0 (`VERSION`, `RELEASE_NOTES.md`)

## Regras finais (continuam válidas)
- Engine não se auto-modifica via patch.
- Templates não são alterados.
- Tudo gerado vai para `/home/bazari/generated/<project>`.

## Aceite final
`python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço" --release`
- sistema rodando
- smoke PASS
- logs completos
- motor v1.0.0 identificado
