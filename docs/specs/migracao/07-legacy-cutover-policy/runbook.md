# Runbook — Legacy Cutover (Migração 07)

## Objetivo

Fazer a transição segura:
- `legacy` → `both` (medir e reduzir uso de legacy)
- `both` → `idl` (cutover final, sem legacy routers)

## Passo 1 — Rodar em `ENGINE_API_MODE=both` (medição)

1) Suba o engine com `ENGINE_API_MODE=both`.
2) Rode a operação real (aplicação cliente) por um período.
3) Consulte a telemetria (console/status) e identifique:
   - endpoints legacy-only ainda usados
   - frequência e último uso

## Passo 2 — Resolver endpoints legacy-only

Para cada endpoint legacy-only que ainda aparece:
- (A) migrar para IDL (adicionar em `operations.json` do bundle e garantir dispatcher/gates suportam), ou
- (B) descontinuar o endpoint no cliente

## Passo 3 — Cutover para `ENGINE_API_MODE=idl`

1) Suba com `ENGINE_API_MODE=idl`.
2) Valide smoke tests do baseline (Migração 06).
3) Monitore 404/unsupported — isso indica operações que ainda dependiam do legacy.

## Importante: Limitações do modo `both`

- Rotas colidentes (mesmo `method/path`) podem ser atendidas pelo handler “primeiro registrado”.
- Portanto, “ver pouco legacy” em `both` não prova que o IDL cobre tudo.
- O corte real é validado em `idl`, onde legacy não existe.

