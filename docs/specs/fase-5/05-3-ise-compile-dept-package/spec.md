# Fase 5 — Etapa 5.3: Compilar dept package (IRCS → bundle)

**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-5/00-plano.md` (Etapa 5.3)

## Objetivo

Compilar um dept (IRCS v1) em um bundle (contracts) compatível com o loader, com prova offline e âncora `source_idl_sha256` real.

## Escopo

Inclui
- CLI/entrypoint e/ou integração via console para compilar IRCS → bundle
- Persistir bundle por instituição/dept (local canônico)
- Proof obrigatório (PASS) para “marcar pronto”

Não inclui
- Ativar o dept no runtime automaticamente (isso depende do modelo de ativação da Etapa 5.1)

## Regras não negociáveis

- bundle.manifest ABI do loader
- contract_ledger coerente com manifest e `source_idl_sha256`
- determinismo

