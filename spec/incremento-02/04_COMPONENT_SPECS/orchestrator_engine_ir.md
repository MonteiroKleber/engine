# orchestrator/engine.py — Atualização do pipeline até IR

## Pipeline (ordem fixa)
1) normalize
2) classify blueprint
3) req_analyst → SRS
4) validate SRS
5) save SRS (vN)
6) domain_modeler → IR
7) validate IR
8) policy validator (IR)
9) save IR (vN) (somente se IR válido + policy ok)
10) write run log (sempre)

## Gate rules
- Se SRS inválido: parar antes do DomainModeler.
- Se IR inválido (schema): não salvar IR e registrar erros.
- Se policy falhar: não salvar IR e registrar erros.

## Run log
- Incluir hashes do input normalizado, SRS e IR (quando IR existir).
