# Etapa 01 — Baseline e Gap Report

Objetivo
- Congelar o “ponto de partida” e produzir um **Gap Report verificável** contra o Definition of Done do MVP.

Escopo
- Somente leitura e documentação, sem refactor amplo.
- Pode incluir correções pequenas de documentação para refletir o estado real.

Entradas
- Código em `/home/bazari/engine`.
- Definition of Done (MVP) acordado com a liderança.

Saídas (artefatos)
- `docs/specs/fase-1/01-baseline/gap-report.md` com:
  - Checklist DoD: ✅/⚠️/❌ com evidência (arquivo, endpoint, teste).
  - “Riscos críticos” (itens que violam princípios, ex.: execução allow-all).
  - “Decision points” que precisam de escolha explícita.
- `docs/specs/fase-1/01-baseline/baseline.md` com:
  - versão atual (`pyproject.toml`)
  - como rodar testes
  - como rodar runtime localmente (se existir)

Regras
- Nada de “assumir” que está pronto. Só marcar ✅ com evidência.
- Se houver divergência entre doc interna e código, o **código vence** como baseline.

Definition of Done (Etapa 01)
- Gap report escrito, com no mínimo 10 itens de evidência objetiva.
- Riscos críticos explicitados com recomendação de decisão (ex.: default-deny).

