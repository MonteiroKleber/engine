# Fase 2 — Etapa 2.2: ISE (IRCS v1 → Contracts/Bundle)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.2)

## Fonte de Verdade (normativa)

- IDL DSL v1.2.2 (congelada): `/home/bazari/Downloads/spec-libervia/arquivos/incremento-063.pdf`
- IR canônico (IRCS v1, exemplo): `/home/bazari/Downloads/spec-libervia/arquivos/incremento-056.pdf`
- IRCS v1 schema (repo): `docs/specs/fase-2/02-1-idl-mandates-autonomy/ircs-v1-schema.md`
- ABI do bundle (loader): `docs/specs/fase-1/02-idl-artifacts/idl-v1.md`

## Objetivo

Fazer o ISE compilar a partir do **IRCS v1 (JSON canônico)** e gerar um **bundle executável** compatível com o runtime atual (loader + gates + proof), sem depender do “IDL JSON ad-hoc”.

## Escopo

Inclui
- Novo caminho de compilação: `IRCS v1 JSON` → `contracts/` → `bundle.manifest.json` → `contract_ledger.json`.
- Paridade Finance: compilar um IRCS v1 do Finance (gerado na Etapa 2.1) em um bundle carregável no runtime.
- Prova mínima:
  - hashes SHA256 corretos no manifest
  - `contract_ledger.json` emitido pelo ISE com hashes e referência ao `source_idl_sha256` (que vem da DSL via IR).

Não inclui (fora desta etapa)
- Parser DSL (Etapa 2.1 já cobre)
- NL → DSL
- Legacy Bridge / AXIOM

## Decision Points

1) Integração no ISE
- **Preferido:** adapter `IRCS v1 → modelo interno` e reaproveitar emitters existentes (mínimo, menos duplicação).
- Evitar pipeline paralelo inteiro só para IR.

2) Compatibilidade
- Manter caminho legado (JSON-IDL ad-hoc) por enquanto.
- Novo caminho (IRCS v1) vira o caminho canônico para produção institucional.

## Regras não negociáveis

- **ABI do bundle:** `bundle.manifest.json` deve seguir o schema do loader (array `contracts[]` com `{file, sha256, required}`).
- **Sem permissividade por ausência:** contratos marcados `required=true` ausentes → SAFE_MODE.
- **Determinismo:** a mesma entrada IRCS v1 deve gerar os mesmos artefatos (exceto timestamps, se existirem, devem estar fora dos hashes ou ser explicitamente controlados).

## Entrega mínima (Etapa 2.2)

### 1) Entrada: IRCS v1

O ISE deve aceitar um objeto IRCS v1 (dict) ou um arquivo `ir.json` com:
- `ir_version: "ircs.v1"`
- `source_idl_version: "idl.v1.2.2"`
- `source_idl_sha256` (hex)

### 2) Saída: bundle executável

Gerar bundle com, no mínimo:
- `bundle.manifest.json` (ABI do loader)
- `contract_ledger.json` (com hashes e prova mínima)
- contracts necessários para o Finance no runtime atual:
  - `rbac.json`
  - `approvals.json`
  - `workflows.json`
  - `sod.json`
  - `invariants.json`
  - `policies.json`
  - `mandates.json`
  - `autonomy.json`

### 3) CLI mínima (recomendado)

Adicionar um entrypoint simples para compilar:
- `PYTHONPATH=src python -m engine.ise compile-ircs path/to/ir.json -o out_bundle_dir`

(Pode ser uma subopção do CLI existente, se houver.)

## Testes (obrigatórios)

- Compilar IRCS v1 do Finance gera bundle que:
  - carrega no loader como ACTIVE (não SAFE_MODE)
  - permite o fluxo E2E mínimo do Finance (create + approval decide), conforme contratos gerados
- Verificações determinísticas:
  - `bundle.manifest.json` lista contratos com `required: true` e `sha256` no formato esperado
  - `contract_ledger.json` referencia corretamente o `source_idl_sha256` e hashes dos contratos

## Definition of Done

- Existe um caminho estável: `IRCS v1 → bundle` (sem usar o JSON-IDL ad-hoc).
- Bundle gerado sobe ACTIVE no runtime.
- Os artefatos permitem prova offline mínima (para fechar Etapa 2.3 sem “gambiarra”).

