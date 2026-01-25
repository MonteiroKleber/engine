# Agent Guardrails (Claude Code / outros agentes)

Este documento existe para evitar repetição do incidente de **deleção de arquivos untracked** e “reversões” amplas sem confirmação.

## Regras de Ouro (não negociáveis)

1) **PROIBIDO** deletar/mover arquivos fora do allowlist.
2) **PROIBIDO** rodar `git clean` (qualquer flag), `rm -rf`, ou “limpeza” automatizada.
3) **PROIBIDO** deletar arquivos **untracked** (mesmo que “não estejam no git”).
4) Se o agente achar que precisa deletar/mover algo: **listar exatamente os paths e parar pedindo OK**.
5) Mudanças devem ser **mínimas** e restritas ao escopo.

## Procedimento obrigatório antes de qualquer patch

- Rodar e colar a saída literal:
  - `git status --porcelain`
  - `git diff --name-only`
- Se houver qualquer arquivo importante “??” (untracked) relacionado ao trabalho: **parar e pedir para o humano commitar/checkpoint** antes de continuar.

## Procedimento obrigatório antes de finalizar

- Rodar e colar a saída literal:
  - `git status --porcelain`
  - `git diff --name-status`
- Confirmar explicitamente:
  - “Não deletei arquivos untracked”
  - “Não rodei git clean / rm -rf”
  - “Mudanças fora do allowlist: nenhuma”

## Prompt “padrão duro” (copiar/colar no Claude)

```
Você está no repositório /home/bazari/engine.

Objetivo: implementar somente o escopo descrito abaixo (patch mínimo).

GUARDRAILS (hard):
1) É PROIBIDO deletar qualquer arquivo/diretório, inclusive untracked.
2) É PROIBIDO mover/renomear diretórios.
3) É PROIBIDO rodar `git clean` (qualquer flag) e `rm -rf`.
4) Se você achar que precisa deletar/mover algo, pare e peça aprovação listando os paths.
5) Não toque em nada fora do ALLOWLIST.

Pré-flight (obrigatório):
- Cole a saída literal de:
  - git status --porcelain
  - git diff --name-only
- Se houver arquivos untracked relevantes (??) no escopo, NÃO prossiga: peça para o humano commitar/checkpoint.

ALLOWLIST (únicos paths que você pode editar):
- <PREENCHER AQUI, ex.: src/engine/core/dispatcher.py
- <...>

Tarefas:
- <PREENCHER AQUI>

Hard gates antes de declarar DONE:
- Cole a saída literal de:
  - git status --porcelain
  - git diff --name-status
- Confirme: “não deletei untracked”, “não usei git clean”, “sem mudanças fora do allowlist”.
```

