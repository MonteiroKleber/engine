# Prompt — Dia 1: QA/Release Agent (núcleo)

Implemente o Dia 1 da Semana 10.

Criar:
- `/home/bazari/engine/release/qa_release_agent.py`

Interface fixa:
```py
class QAReleaseAgent:
    def run_smoke(self, repo_path) -> dict
    def run_checklist(self, repo_path) -> dict
    def emit_release_bundle(self, project) -> str
```

Aceite:
- Gera relatório estruturado mesmo com repo mínimo.
