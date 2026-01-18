# Etapa 02 — Prompts (Claude Code)

PROMPT 02.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Decisão oficial (fixa para o MVP):
- `policies.json`, `mandates.json`, `autonomy.json` são **contratos institucionais mínimos obrigatórios**.
- Se qualquer um deles estiver ausente no bundle (ou ausente do `bundle.manifest.json` quando aplicável), o sistema deve considerar o bundle **inválido** e entrar em **SAFE_MODE**.

Tarefa:
1) Leia `docs/specs/fase-1/02-idl-artifacts/spec.md` e siga como contrato.
2) Inspecione no código quais arquivos compõem a IDL hoje (schemas, loaders, normalização, hashing).
3) Escreva os artefatos desta etapa:
   - `docs/specs/fase-1/02-idl-artifacts/idl-v1.md`
   - `docs/specs/fase-1/02-idl-artifacts/canonical-artifacts.md`

Requisitos do conteúdo (obrigatório):
- Em `idl-v1.md`, declare explicitamente que no MVP:
  - `policies.json`, `mandates.json`, `autonomy.json` são obrigatórios para qualquer bundle executável (single-mode e multi-mode).
  - Sem esses contratos, o engine deve ir para SAFE_MODE (bundle inválido).
- Liste as regras mínimas de canonicalização/determinismo (ordem de chaves, encoding, timezone, RNG, etc.) conforme o que o código já faz ou deveria fazer no MVP.
- Em `canonical-artifacts.md`, liste os artefatos mínimos para prova offline e onde eles ficam por run/deploy.

Evidência objetiva:
- Referencie caminhos reais do código (sem colar arquivo inteiro).
- Aponte explicitamente as divergências atuais (ex.: bundle finance-pilot hoje não inclui esses contratos) como gaps, sem implementar nada nesta etapa.

Restrições:
- Não implementar mudanças de código nesta tarefa. Apenas documentação.
- Não inventar comportamento. Quando for “deve”, deixe claro que é a regra canônica do MVP (decisão oficial) e marque como gap se ainda não estiver no código.

Saída esperada:
- Apenas changes nos arquivos de docs citados acima (Etapa 02).
[[CLAUDE_CODE_END]]
