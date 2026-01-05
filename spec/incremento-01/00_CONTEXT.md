# Contexto e Escopo

## Objetivo da Semana 3
Implementar um pipeline de intake mínimo que:
- Normaliza o texto de entrada.
- Classifica blueprint (forçado para `generic` nesta semana).
- Gera um `SRS.json` determinístico (modo MOCK).
- Valida o SRS contra schema (`jsonschema`).
- Se válido: versiona e salva no artifact store.
- Se inválido: bloqueia e gera perguntas de esclarecimento.
- Fornece CLI `python main.py --project <name> --input "<texto>"`.

## Não-objetivos (explicitamente fora do escopo)
- Integração real com SDK de LLM.
- Classificação inteligente de blueprint.
- “SRS perfeito” com regras específicas de negócio.

## Restrições
- Sem dependência de SDK de LLM. `llm/client.py` deve ser interface + mock.
- Comportamento determinístico (mesma entrada → mesma saída), exceto IDs de execução/log.
- Estrutura de arquivos do repo deve ser exatamente a árvore definida.

## Definição de pronto (critério de conclusão)
A Semana 3 termina quando:
- `python main.py --project demo --input "quero um sistema..."`:
  - gera `SRS.json` válido
  - salva `store_data/demo/SRS/v1.json`
  - grava um run log
- `pytest` passa.
