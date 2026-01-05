# Prompt — Dia 7: Freeze + Demo CLI

Implemente a Tarefa 4.8 (Dia 7) da Semana 4.

1) Run log com hashes obrigatórios
Garantir que o run log inclua:
- hash do input (normalizado)
- hash do SRS
- hash do IR

2) Demonstração obrigatória
Rodar:
- `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`

Resultados obrigatórios:
- `store_data/demo/SRS/v1.json`
- `store_data/demo/IR/v1.json`
- run log com `input_hash`, `srs_hash`, `ir_hash`

Critério de aceite:
- `pytest` 100% verde
- demo CLI gera SRS e IR sempre reproduzível (hashes estáveis para mesma entrada).
