# intake/req_analyst.py — Especificação

## Objetivo
Gerar um `SRS.json` compatível com `schemas/srs.schema.json`.

## Modo Semana 3
- Se `llm.enabled=false` (padrão): operar em modo MOCK determinístico.

## Regras do modo MOCK
- `summary`: frase curta baseada no texto (ex.: primeiras 1–2 linhas/bullets).
- `actors`: sempre incluir 1 ator padrão `admin`.
- `functional_requirements`: gerar 3–6 FRs usando verbos detectados (ex.: cadastrar/listar/editar).
- `open_questions`: incluir perguntas quando faltarem pistas sobre:
  - autenticação necessária?
  - perfis/roles?
  - entidades principais?

## Restrições
- Nunca inventar regras de negócio específicas (ex.: políticas de desconto, cálculo, SLA etc.).
- Preferir FRs genéricos e verificáveis.

## Saída
- Retornar dict pronto para validação por schema.
