# Etapa 03 — Prompts (Claude Code)

PROMPT 03.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/03-pipeline/spec.md` e siga como contrato.
2) Mapeie o pipeline existente no código (módulos, estados, persistência, export).
3) Verifique explicitamente a compatibilidade ISE → loader:
   - qual formato o ISE emite para `bundle.manifest.json`
   - qual formato o loader espera/valida
   - se bundles gerados pelo ISE sobem ACTIVE no runtime
3) Escreva:
   - `docs/specs/fase-1/03-pipeline/states.md`
   - `docs/specs/fase-1/03-pipeline/trace-contract.md`

Regras:
- Não implemente mudanças de código nesta etapa.
- Se a persistência de `trace.json` não existir para deploy, marque como gap crítico.
- Se o ISE emitir manifest incompatível com o loader, marque como gap crítico (alta severidade) e aponte evidência.
[[CLAUDE_CODE_END]]

PROMPT 03.2
[[CLAUDE_CODE_START]]
Somente se o gap report indicar falha de bloqueio (ex.: build/deploy acontecendo com gaps):
1) Proponha a menor mudança possível para garantir `NEEDS_ANSWERS` como bloqueio duro.
2) Inclua testes que provem o bloqueio.

Saída esperada:
- Patch mínimo + testes + atualização da documentação da Etapa 03.
[[CLAUDE_CODE_END]]

PROMPT 03.3
[[CLAUDE_CODE_START]]
Decisão oficial (MVP):
- O ISE compiler deve emitir `bundle.manifest.json` no **formato do loader**: `{ name, version, description, contracts: [{file, sha256, required}] }`.

Tarefa (implementação mínima):
1) Ajuste o ISE compiler para gerar `bundle.manifest.json` compatível com o loader (não criar novo formato).
2) Garanta que o bundle emitido inclua como `required=true` no manifest, no mínimo:
   - `policies.json`
   - `mandates.json`
   - `autonomy.json`
   - além dos contratos operacionais já exigidos no bundle piloto (rbac/approvals/workflows/sod/invariants).
3) Adicione testes que provem:
   - um bundle gerado pelo ISE carrega no loader sem SAFE_MODE
   - o manifest está no schema `{name, version, contracts[]}`
   - a validação de hash funciona com o prefixo `SHA256:` (ou sem, conforme normalização)

Restrições:
- Não alterar o loader para “aceitar o formato do ISE”; a escolha do MVP é ISE → loader.
- Mudanças devem ser mínimas e com testes.

Saída esperada:
- Patch mínimo + testes + atualização breve de `docs/specs/fase-1/03-pipeline/states.md` ou `trace-contract.md` se necessário.
[[CLAUDE_CODE_END]]
