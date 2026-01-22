# Fase 3 — Etapa 3.7: Intake Assistido (NL → Draft → Gaps → DSL/IR)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.7)

## Objetivo

Adicionar ao console um fluxo assistido para criar/editar **rascunhos** de definição institucional, sem automação autônoma:

- entrada de texto (intenção)
- geração de rascunho (DSL/IR) e gaps
- UI para perguntas/respostas (NEEDS_ANSWERS)
- export do resultado (DSL/IR) para revisão humana

## Escopo

Inclui
- UI e rotas do console para:
  - formulário de "intake" (texto)
  - mostrar Draft IR/DSL + gaps
  - coletar respostas e re-finalizar
  - exportar artefatos

Não inclui
- Deploy automático
- Aplicar mudanças em produção
- IA tomando decisão

## Regras não negociáveis

- IA é assistente: gera rascunho, nunca aplica.
- Qualquer ação mutável deve ser governada (proposals) e isso não entra aqui.
- Tudo deve ser exportável e verificável.

## Entregas mínimas

1) Rotas console ✅
- `GET /console/intake` - Formulário inicial com toggle NL/DSL
- `POST /console/intake` - Gera draft + gaps (NL) ou IR direto (DSL)
- `POST /console/intake/answer` - Coleta respostas para gaps
- `POST /console/intake/finalize` - Aplica respostas e gera DSL/IR final
- `GET /console/intake/export?format=ir` - Download IR JSON

2) Integrações ✅
- Reusa pipeline existente NL/SIR/gap/finalize (`engine.nl.*`)
- Modo "manual DSL" implementado: usuário cola DSL e o console valida/gera IR via `engine.idl_dsl.parse_dsl()`

3) Testes ✅
- 16 novos testes cobrindo:
  - Autenticação (X-Admin-Token)
  - Fluxo básico de draft→gaps→finalize
  - Modo NL e modo DSL
  - Export IR JSON
  - Nav link

## Implementação

### Rotas (console/routes.py)

| Rota | Método | Linha | Descrição |
|------|--------|-------|-----------|
| `/console/intake` | GET | 844 | Formulário inicial |
| `/console/intake` | POST | 880 | Processa NL ou DSL |
| `/console/intake/answer` | POST | 975 | Aplica respostas |
| `/console/intake/finalize` | POST | 1075 | Finaliza draft |
| `/console/intake/export` | GET | 1142 | Download JSON |

### Templates (console/templates/)

| Template | Descrição |
|----------|-----------|
| `intake.html` | Formulário inicial com toggle NL/DSL |
| `intake_draft.html` | Preview draft, gaps, questions, answers form |
| `intake_result.html` | Resultado final, validação, export |

### State Management

Estado passado via hidden form fields (stateless server):
- `sir_json`: SIR serializado
- `draft_json`: Draft serializado
- `gaps_json`: Gaps serializados
- `remaining_gaps_json`: Gaps restantes

### Fluxo NL

```
input_text → extract() → SIR → generate_draft() → Draft
                                    ↓
                              detect_gaps() → Gaps
                                    ↓
                              [answer questions]
                                    ↓
                              apply_answers() → Updated Draft
                                    ↓
                              finalize() → Final IDL
                                    ↓
                              export → IR JSON
```

### Fluxo DSL (fallback)

```
input_text → parse_dsl() → IRCS → intake_result.html → export → IR JSON
```

## Definition of Done

- [x] Um operador consegue gerar um rascunho via texto (NL mode)
- [x] Um operador consegue gerar um rascunho via DSL (DSL mode)
- [x] Um operador consegue ver e responder gaps no console
- [x] Um operador consegue fechar gaps e finalizar
- [x] Um operador consegue exportar IR para revisão humana

## Limitações conhecidas

- Export DSL não implementado (requer IR→DSL converter)
- Modo NL usa extractor determinístico por padrão (LLM opcional via env)
