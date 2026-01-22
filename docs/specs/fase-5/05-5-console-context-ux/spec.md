# Fase 5 — Etapa 5.5: Console UX de contexto (instituição vs dept)

**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-5/00-plano.md` (Etapa 5.5)

## Objetivo

Deixar o console “impossível de confundir” em termos de escopo:

- o que é global da instituição
- o que é específico do dept

## Escopo

Inclui
- Barra de contexto (instituição/dept)
- Links/rotas sempre preservando o contexto
- Página home com depts reais (derivados do modelo canônico de ativação)

Não inclui
- Redesign visual completo

## Regras não negociáveis

- Não esconder escopo em querystring “invisível”
- Não misturar dados de depts diferentes na mesma view sem deixar explícito

