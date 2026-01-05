# Contexto e Escopo

## Objetivo imutável da Semana 4
Implementar IR Canônico com:
- `schemas/ir.schema.json` (oficial)
- `agents/domain_modeler.py` (gera IR a partir do SRS)
- `validators/ir_validator.py` (gate por schema)
- versionamento do IR no store
- testes unitários + integração do pipeline até IR

## Entradas e saídas esperadas
- Entrada do pipeline: `raw_text` (CLI)
- Artefatos persistidos:
  - SRS: `store_data/{project}/SRS/vN.json`
  - IR: `store_data/{project}/IR/vN.json`
- Run log deve incluir hashes (input, SRS, IR).

## Não-objetivos
- LLM / SDK de LLM.
- Enriquecimento inteligente de domínio.
- Inferir entidades não presentes no SRS.

## Definição de pronto (Semana 4 concluída)
- Pipeline até IR funcionando (gera, valida, faz policy gate, versiona).
- IR rastreável (versionamento + hashes no run log).
- `pytest` 100% verde.
- Demo:
  - `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`
  - gera `store_data/demo/SRS/v1.json`
  - gera `store_data/demo/IR/v1.json`
  - grava run log com `input_hash`, `srs_hash`, `ir_hash`.
