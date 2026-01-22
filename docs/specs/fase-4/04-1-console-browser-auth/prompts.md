# Fase 4 — Etapa 4.1: Prompts (Claude Code)

PROMPT 4.1.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-1-console-browser-auth/spec.md` e siga como contrato.
2) Mapeie a auth atual do console:
   - onde `_require_admin_token()` valida `X-Admin-Token`
   - quais rotas do console são POST hoje
   - como o FastAPI app está configurado (middlewares, templates)
3) Proponha o mecanismo mínimo de sessão:
   - cookie assinado vs server-side session
   - onde armazenar secret (env/config)
4) Produza:
   - `docs/specs/fase-4/04-1-console-browser-auth/gaps.md`
   - `docs/specs/fase-4/04-1-console-browser-auth/api.md` (rotas login/logout + comportamento HTML/JSON)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.1.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Implementar login por token → sessão via cookie, com CSRF básico para POSTs do console.
- Manter compatibilidade com `X-Admin-Token`.
Requisito operacional (obrigatório):
- `ENGINE_CONSOLE_SESSION_SECRET` deve estar configurado.
- Se estiver ausente, a aplicação deve falhar de forma determinística no startup/preflight (não gerar secret automaticamente).


Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-1-console-browser-auth/spec.md` e siga como contrato.
2) Implementar rotas:
   - `GET /console/login`
   - `POST /console/login`
   - `GET /console/logout`
3) Implementar middleware/deps para:
   - autenticar via cookie OU via `X-Admin-Token`
   - exigir CSRF em rotas POST do console
4) Ajustar comportamento:
   - requests HTML sem auth → redirect para login
   - requests JSON sem auth → erro JSON atual
5) Adicionar testes cobrindo:
   - login/logout
   - redirect behavior
   - CSRF bloqueia POST sem token
   - CSRF permite POST com token

Documentação:
- Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
