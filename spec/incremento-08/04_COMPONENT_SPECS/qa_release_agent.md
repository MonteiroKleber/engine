# release/qa_release_agent.py — QA/Release Agent

## Objetivo
Centralizar ações de QA e release sobre um repo gerado.

## Interface fixa
```py
class QAReleaseAgent:
    def run_smoke(self, repo_path) -> dict
    def run_checklist(self, repo_path) -> dict
    def emit_release_bundle(self, project) -> str
```

## run_smoke(repo_path) -> dict
- Executa smoke tests (backend + frontend + docker).
- Retorna relatório estruturado (ex.: `ok`, `checks[]`, `artifacts_path`).

## run_checklist(repo_path) -> dict
- Executa checklist final de release (ver `release_checklist.py`).
- Retorna relatório estruturado (ex.: `ok`, `missing[]`, `errors[]`).

## emit_release_bundle(project) -> str
- Gera um bundle “industrial” (relatório JSON/MD + instruções + caminho do repo gerado).
- Retorna path do bundle gerado.

## Regras
- Relatórios devem ser estruturados mesmo com repo mínimo.

## Critério de aceite (Dia 1)
- Gera relatório estruturado mesmo com repo mínimo.
