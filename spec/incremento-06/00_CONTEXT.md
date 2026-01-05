# Contexto e Escopo

## Objetivo imutável da Semana 8
Transformar o motor em um executor autônomo governado capaz de:
- gerar código funcional real (não stub)
- interpretar erros de build
- corrigir com patches mínimos
- repetir até sucesso ou erro estrutural
- sem violar contratos/policies/paths

Fluxo:
raw → … → PLAN → repo → build
                ↳ fail → FixLoop → patch → retry
                ↳ success → sistema funcional

## Contexto fixo (paths)
Tudo continua em `/home/bazari/`:
- Engine: `/home/bazari/engine`
- Templates: `/home/bazari/templates`
- Output: `/home/bazari/generated/<project>`

## Componentes a implementar/atualizar
- `fix_loop/error_classifier.py`
- `fix_loop/fix_loop_agent.py`
- `fix_loop/fix_patch_generator.py`
- `compilers/backend_compiler.py` (real)
- `compilers/frontend_compiler.py` (real)
- `orchestrator/engine.py` (integração do fix loop)
- testes e demo

## Regras absolutas
- `MAX_FIX_ATTEMPTS = 3`
- Cada iteração: 1 patch, 1 causa
- Patches passam pelas mesmas rules da Semana 7
- Nenhuma escrita fora de `/home/bazari/generated/<project>`

## Run log (Semana 8)
Além dos campos já existentes, incluir:
- `fix_attempts` (int)
- `fixes_applied[]` (lista de objetos com error_class + patch summary)
- `final_status` (ex.: SUCCESS | FAILED_FATAL | FAILED_MAX_ATTEMPTS)

## Critério de pronto (Semana 8 concluída)
- Compilers reais (backend + frontend) geram código funcional.
- Fix Loop ativo e limitado (≤3 tentativas).
- Autocorreção governada sem violar paths/contratos.
- Sistema funcional end‑to‑end.
- Testes verdes.
