# Fase 5 — Etapa 5.1: Modelo canônico de ativação multi-dept

**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-5/00-plano.md` (Etapa 5.1)

## Objetivo

Definir o modelo canônico para uma instituição rodar com múltiplos departamentos, sem ambiguidade:

- “instalar” vs “ativar”
- como resolver bundle ativo por `(institution_id, dept_id)`
- como representar isso no config/ledger e no console

## Escopo

Inclui
- Especificação do modelo (storage + APIs internas) para “active depts set”
- Regras de fallback e compatibilidade com estado atual do engine

Não inclui
- Implementação (fica para o prompt de implementação desta etapa)

## Regras não negociáveis

- Isolamento por `(institution_id, dept_id)`
- Prova offline não pode depender de runtime
- Sem “heurística” para escolher dept/bundle ativo

## Definition of Done (documentação)

- Spec descreve exatamente:
  - formato e local do “mapa de depts ativos”
  - precedência (pinned vs current vs template)
  - eventos no ledger
  - erros determinísticos

