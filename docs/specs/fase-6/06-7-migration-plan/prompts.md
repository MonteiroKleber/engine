# Etapa 6.7 — Prompts (Claude Code)

PROMPT 6.7.1 (Diagnóstico: gaps de migração e ponto de integração)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-7-migration-plan/spec.md` e siga como contrato.
2) Mapeie:
   - onde `ENGINE_API_MODE` é lido/aplicado hoje (6.4)
   - onde seria o lugar correto para rodar “migration checks” no boot
   - como o console status coleta informações hoje e onde injetar “migrated vs not migrated”
3) Proponha o patch mínimo para:
   - checks determinísticos
   - fail em `idl`
   - warnings em `both`

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-7-migration-plan/map.md`
- `docs/specs/fase-6/06-7-migration-plan/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.7.2 (Implementação mínima: migration checks + report no status)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-7-migration-plan/spec.md`.
2) Mudança mínima.
3) Reforços obrigatórios (não discutir, apenas implementar):
   - Executar `run_migration_checks()` no boot **exatamente** no ponto mapeado:
     - entre `run_preflight_checks()` e `register_idl_routes()` no `lifespan` do `server.py`.
   - Regras de modo (determinísticas):
     - `ENGINE_API_MODE=idl`: **hard fail** se qualquer check falhar (sem fallback silencioso).
     - `ENGINE_API_MODE=both`: **não falhar**, mas registrar warnings determinísticos e expor no console.
     - `ENGINE_API_MODE=legacy`: não exigir checks (somente opcional/diagnóstico).
   - Não criar endpoints mutáveis novos; apenas exibir status read-only no console.
   - Não “adivinhar” migração: usar campos estruturados (`operations.json`, `bind.kind`) e cobertura real do dispatcher.

Tarefa:
1) Implementar módulo `migration_check.py` (ou equivalente) que retorna um report estruturado:
   - depts com operations.json presente/ausente
   - operações com bind.kind não suportado
   - colisões relevantes (se expostas pelo idl_router)
2) Integrar no boot:
   - `ENGINE_API_MODE=idl`: falhar determinístico se report tiver erro
   - `ENGINE_API_MODE=both`: logar warnings determinísticos
3) Expor esse report no console status (read-only), sem UI complexa:
   - adicionar um bloco na página Status com “IDL Migration Status”
4) Testes:
   - unit tests do migration check
   - integração: `ENGINE_API_MODE=idl` falha quando operations.json ausente
   - integração: `ENGINE_API_MODE=both` sobe e inclui warnings/report
5) Atualizar docs:
   - `spec.md` status IMPLEMENTADO
   - `map.md` e `gaps.md`

Restrições:
- Não alterar semântica do dispatcher/router.
- Não criar endpoints mutáveis novos.
[[CLAUDE_CODE_END]]
