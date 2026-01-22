# Fase 5 — Etapa 5.4: Runtime com múltiplos bundles ativos (por dept)

**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-5/00-plano.md` (Etapa 5.4)

## Objetivo

Permitir que uma instituição rode com múltiplos departamentos ativos, cada um com seu bundle.

## Escopo

Inclui
- Resolução determinística de bundle ativo por dept
- Roteamento seguro (dept prefix / dept path)
- Isolamento de state_store e ledger por dept

Não inclui
- Mudanças de DSL/IR

## Regras não negociáveis

- Nenhuma execução fora de contratos
- Erros anti-inference
- SAFE_MODE quando bundle inválido

