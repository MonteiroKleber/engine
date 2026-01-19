# Fase 2 — Etapa 2.3: Prova Offline Clean (DSL/IR → Bundle)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.3)

## Fonte de Verdade (normativa)

- IDL DSL v1.2.2 (congelada): `/home/bazari/Downloads/spec-libervia/arquivos/incremento-063.pdf`
- IRCS v1 (exemplo canônico): `/home/bazari/Downloads/spec-libervia/arquivos/incremento-056.pdf`
- IRCS v1 schema: `docs/specs/fase-2/02-1-idl-mandates-autonomy/ircs-v1-schema.md`
- ABI do bundle/manifest (loader): `docs/specs/fase-1/02-idl-artifacts/idl-v1.md`

## Objetivo

Permitir verificação **offline** (sem rodar runtime) de que:

1) uma decisão institucional (DSL v1.2.2) está ancorada por `source_idl_sha256`
2) o bundle em produção corresponde a essa decisão, via hashes verificáveis

Em uma frase:
**Sem executar o sistema, provar integridade do bundle e vínculo com a decisão (DSL).**

## Escopo

Inclui
- Procedimento canônico de auditoria offline.
- Implementação de um verificador mínimo (CLI) para:
  - validar `bundle.manifest.json`
  - validar SHA256 de cada contract listado
  - validar `contract_ledger.json` e consistência com o manifest
  - validar presença e formato de `source_idl_sha256`
- Testes positivos e negativos.

Não inclui
- Auditoria do `audit_ledger.jsonl` runtime (fora do escopo desta etapa).

## Regras não negociáveis

- A prova offline deve funcionar com arquivos do bundle + ledger de contratos.
- Hashing:
  - SHA256 em hex (64 chars)
  - aceitar `SHA256:<hex>` na entrada, comparar pelo `<hex>`.
- Erros determinísticos (códigos), sem “best effort”.

## Artefatos mínimos

### bundle.manifest.json

- schema do loader: `{name, version, description, contracts:[{file, sha256, required}]}`

### contract_ledger.json

Deve conter, no mínimo:
- `ledger_version`
- `bundle_name`, `bundle_version`
- `manifest_hash` (SHA256 do manifest)
- `source_idl_sha256` (hex; hash do texto DSL UTF-8)
- `contracts[]` com `{file, sha256}` coerentes com o manifest

Decisão desta etapa:
- `source_idl_sha256` é a âncora canônica de “decisão versionável” na prova offline.

## Procedimento canônico (auditor offline)

Entrada: diretório do bundle.

1) Ler `bundle.manifest.json`
2) Para cada `contracts[].file`:
   - verificar que existe
   - calcular SHA256(bytes) e comparar com o `sha256` do manifest
3) Ler `contract_ledger.json`
4) Verificar:
   - `manifest_hash` bate com SHA256 do manifest
   - `contracts[]` do ledger batem com o manifest (mesmo arquivo e mesmo hash)
   - `source_idl_sha256` existe e é SHA256 hex válido
5) Resultado:
   - PASS: integridade + vínculo com decisão
   - FAIL: erro determinístico + divergências

## Definition of Done

- Existe um comando offline que valida integridade do bundle e o vínculo com `source_idl_sha256`.
- Existem testes automáticos cobrindo PASS/FAIL.
- A documentação descreve o procedimento oficial.
