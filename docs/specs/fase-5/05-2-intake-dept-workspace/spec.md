# Fase 5 — Etapa 5.2: Workspace por dept (IDL/IR)

**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-5/00-plano.md` (Etapa 5.2)

## Objetivo

Permitir que a instituição mantenha e navegue múltiplas definições por dept:

- DSL v1.2.2 (texto) por dept
- IRCS v1 (JSON) derivado por dept
- export e diff por dept

## Escopo

Inclui
- UI no console para criar/listar “dept definitions”
- Persistência por instituição (sem DB, append-only quando aplicável)

Não inclui
- Deploy automático
- Gerar bundle automaticamente (isso é Etapa 5.3)

## Regras não negociáveis

- DSL é a fonte (hash UTF-8); IR é derivado determinístico
- Sem misturar depts em uma mesma definição canônica

