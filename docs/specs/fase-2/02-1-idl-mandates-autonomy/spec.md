# Fase 2 — Etapa 2.1: IDL DSL v1.2.2 → IRCS v1 (Fonte de Verdade)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.1)

> Nota: a pasta se chama `02-1-idl-mandates-autonomy` por histórico. O escopo desta etapa foi **pivotado** para alinhar com a documentação oficial: **IDL é DSL textual v1.2.2**, e o engine deve consumir um **IR canônico (IRCS v1)**.

## Fonte de Verdade (normativa)

Para esta etapa, a fonte de verdade é a documentação em `/home/bazari/Downloads/spec-libervia/arquivos`:
- IDL v1.1 (EBNF completa do “core”): `incremento-038.pdf`
- IDL v1.2.1 (extensões + EBNF das extensões): `incremento-049.pdf`, `incremento-050.pdf`
- IDL v1.2.2 (history() + EBNF mínima da extensão): `incremento-061.pdf`
- Congelamento da linguagem (IDL v1.2.2 congelada): `incremento-063.pdf`
- IR canônico do Finance (IRCS v1): `incremento-056.pdf`

## Objetivo

Fazer o engine parar de tratar um JSON ad-hoc como “IDL” e passar a operar com o fluxo canônico:

**IDL (DSL textual v1.2.2)** → **IR canônico (IRCS v1, JSON)** → **Contracts/Bundle** → Runtime.

Entrega mínima desta etapa:
1) Definir o **schema canônico do IRCS v1** (JSON) que o ISE irá consumir.
2) Implementar um conversor mínimo: **IDL DSL (Finance exemplo canônico)** → **IRCS v1 JSON**.
3) Garantir validação determinística (tipos + refs + history()) com erros estáveis.

## Escopo (o que entra / o que não entra)

Inclui (nesta etapa)
- Parser/ingest mínimo da DSL v1.2.2 (subset suficiente para o Finance canônico):
  - `system`, `policy_context`, `actors`, `entities`
  - `invariants`, `separation_of_duties`, `workflows` (com approvals), `operations`
  - `predicate_expr` (com `history()`), conforme docs v1.2.2
- Emissão do IRCS v1 (JSON) determinístico.
- Validações (tipos e referências) do kernel de expressões.

Não inclui (fora desta etapa)
- Refatorar o ISE para consumir IRCS v1 (isso é a Etapa 2.2)
- Legacy Bridge
- AXIOM
- NL → DSL (a entrada pode ser um arquivo DSL manual por enquanto)

## Decisões (canônicas) desta etapa

### 1) “IDL” no engine = DSL textual (não JSON)

A partir desta etapa:
- “IDL” significa **arquivo textual** conforme IDL v1.2.2 (EBNF/semântica).
- O JSON atual parseado por `src/engine/ise/idl_parser.py` deve ser tratado como:
  - **legado** (input antigo), ou
  - **IR provisório** (até migrarmos para IRCS v1).

### 2) IRCS v1 é o contrato de entrada do compilador

O IRCS v1 (JSON) é:
- determinístico
- validável offline
- estável como interface entre linguagem e compilador

### 3) Versão e identificadores

No IRCS v1, manter explicitamente:
- `ir_version: "ircs.v1"`
- `source_idl_version: "idl.v1.2.2"` (ou `idl.v1.2.2+...` se houver patch)
- hash do source (DSL) como `source_idl_sha256` (hex), para prova offline na Etapa 2.3

## IRCS v1 (mínimo) — estrutura alvo

Nesta etapa, a estrutura mínima deve permitir expressar o Finance canônico (docs):
- `system`
- `department`
- `policy_context`
- `actors`
- `entities`
- `invariants` (AST tipado)
- `sod` (AST tipado, com `history()` suportado)
- `workflows` + `approvals`
- `operations.api` (endpoints) com binding para workflow/transition/approval_for

Exemplo de referência (não copiar tudo; é só a âncora do formato): `/home/bazari/Downloads/spec-libervia/arquivos/incremento-056.pdf`.

## Validação (compiler / parser) — regras duras

As validações obrigatórias para o subset:
- `predicate_expr` não pode ser string livre; deve virar AST tipado.
- roots permitidos em expr:
  - `entity.*`, `actor.*`, `context.*` (se declarado), `request.*` (somente onde permitido), `history()` (v1.2.2).
- `history(step)` deve ser limitado a atributos definidos (`actors`, `count`, `last_actor`, `last_at`).
- erros determinísticos (sempre a mesma falha para o mesmo input).

## Definition of Done (Etapa 2.1)

- Existe um caminho executável:
  - input: arquivo DSL v1.2.2 (Finance canônico ou subset equivalente)
  - output: `ir.json` (IRCS v1) determinístico
- O IR resultante valida (tipos + refs + history()) e falha com códigos determinísticos quando inválido.
- O IR preserva o `source_idl_version` e `source_idl_sha256` para prova offline posterior.
