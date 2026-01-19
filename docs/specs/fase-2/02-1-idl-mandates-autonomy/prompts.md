# Fase 2 — Etapa 2.1: Prompts (Claude Code)

> Esta etapa foi pivotada: IDL canônica = **DSL textual v1.2.2** (documentação). A saída canônica para o compilador será **IRCS v1** (JSON).

PROMPT 2.1.1 (Mapeamento + Design mínimo: DSL v1.2.2 e IRCS v1)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-1-idl-mandates-autonomy/spec.md` e siga como contrato.
2) Leia (somente como referência normativa) os PDFs:
   - `/home/bazari/Downloads/spec-libervia/arquivos/incremento-038.pdf` (IDL v1.1 EBNF core)
   - `/home/bazari/Downloads/spec-libervia/arquivos/incremento-050.pdf` (EBNF v1.2.1 extensions)
   - `/home/bazari/Downloads/spec-libervia/arquivos/incremento-061.pdf` (history() v1.2.2)
   - `/home/bazari/Downloads/spec-libervia/arquivos/incremento-056.pdf` (IRCS v1 example)
3) No código atual, mapeie:
   - qual é o “input institucional” hoje (JSON parseado por `src/engine/ise/idl_parser.py`)
   - se existe algum parser de DSL textual (provavelmente não)
   - quais estruturas internas seriam um bom ponto de acoplamento para IRCS v1 (ex.: modelo interno do ISE, emitters, etc.)
4) Proponha o caminho mínimo e linear para:
   - DSL v1.2.2 (subset Finance) → IRCS v1 JSON
   - sem ainda refatorar o ISE (essa parte é Etapa 2.2)

Saída esperada (documentação nesta pasta):
- `docs/specs/fase-2/02-1-idl-mandates-autonomy/ircs-v1-schema.md`
- `docs/specs/fase-2/02-1-idl-mandates-autonomy/dsl-subset-v1.2.2.md`
- Um checklist “Implementação mínima” com arquivos/funções alvo

Restrições:
- Não implementar nada neste prompt. Somente diagnóstico e checklist.
[[CLAUDE_CODE_END]]

PROMPT 2.1.2 (Implementação: DSL v1.2.2 → IRCS v1)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-1-idl-mandates-autonomy/spec.md` e siga como contrato.
2) Implementar um conversor mínimo (novo) que receba um texto DSL (IDL v1.2.2 subset) e produza um JSON IRCS v1 determinístico.

Implementação (mínima e objetiva):
A) Novo módulo de ingest DSL → IRCS
1) Criar um pacote dedicado (sugestão; ajustar à organização do repo):
   - `src/engine/idl_dsl/`
2) Implementar:
   - `src/engine/idl_dsl/parser.py`: parse da DSL subset (Finance) para um AST interno
   - `src/engine/idl_dsl/ircs_emit.py`: emissão do IRCS v1 (JSON) determinístico
   - `src/engine/idl_dsl/errors.py`: códigos de erro determinísticos
3) O output IR deve conter no mínimo:
   - `ir_version: "ircs.v1"`
   - `source_idl_version: "idl.v1.2.2"`
   - `source_idl_sha256` (hex, hash do texto DSL original normalizado em UTF-8)

B) Subset suportado (Finance)
4) Implementar somente o subset definido em `dsl-subset-v1.2.2.md` (Etapa 2.1.1):
   - `system`, `policy_context`, `actors`, `entities`
   - `invariants`, `separation_of_duties`, `workflows` (approvals), `operations.api`
   - kernel de expressões com `history()` (v1.2.2)

C) Validação determinística
5) Garantir que expressões não sejam string livre: produzir AST tipado (ou estrutura equivalente) no IR.
6) Bloquear roots proibidos em cada contexto (ex.: `request.*` em `invariants`).

D) CLI mínima (opcional, mas útil)
7) Adicionar um comando simples (ex.: `python -m engine.idl_dsl ...`) para:
   - ler arquivo `.idl`
   - imprimir `ir.json`

E) Testes (obrigatórios)
8) Criar testes de parsing e emissão determinística:
   - parse do Finance canônico (ou um fixture mínimo baseado nele) gera IR estável
   - invalid history attr falha com erro determinístico
   - context.* sem policy_context falha determinístico
   - request.* em invariant falha determinístico

Restrições:
- Não expandir o subset “por criatividade”. Só o que está definido na doc da etapa.
- Não refatorar o ISE nesta etapa (isso é Etapa 2.2).

Saída esperada:
- Patch mínimo + testes passando + atualização breve dos docs desta etapa (checklist/artefatos).
[[CLAUDE_CODE_END]]
