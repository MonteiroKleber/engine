# GAP 1 — Prompts (Claude Code) (produção)

PROMPT 01.1 (Diagnóstico rápido)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/gaps/01-gap1-onboarding-real-decision-anchor/spec.md` e siga como contrato.
2) Mapear exatamente:
   - onde o onboarding gera `source_idl_sha256` placeholder (linha e função)
   - como o template registry define templates hoje
   - como o proof valida `source_idl_sha256` hoje
3) Propor o patch mínimo para:
   - templates declararem seed DSL por dept
   - onboarding incluir seed DSL **dentro do bundle gerado** (para prova offline)
   - onboarding calcular `source_idl_sha256` real (sem placeholder)

Saída esperada:
- `docs/specs/gaps/01-gap1-onboarding-real-decision-anchor/gaps.md` (o que falta, com paths)
[[CLAUDE_CODE_END]]

PROMPT 01.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/gaps/01-gap1-onboarding-real-decision-anchor/spec.md`.
2) Não introduza workflow novo. Só feche o GAP com o mínimo.

Tarefa:
1) Atualizar o template registry para declarar seeds DSL por dept (mínimo: finance-pilot e multi-pilot).
2) Adicionar seeds DSL no repo (arquivos .idl) para os templates necessários.
3) Atualizar o onboarding (`src/engine/console/bundle_generator.py`) para:
   - falhar determinísticamente se seed não existir (produção: sem placeholder)
   - copiar/adicionar os seeds **dentro do bundle gerado**:
     - single: `source.idl`
     - multi: `departments/<dept_id>/source.idl`
   - incluir esses arquivos no `bundle.manifest.json` como contracts com `required=false`
   - calcular:
     - single: `source_idl_sha256 = sha256(source.idl bytes UTF-8)`
     - multi: `source_idl_sha256 = sha256(concat determinística "<dept_id>:<sha256(seed_bytes)>\n")`
   - gravar:
     - `source_idl_sha256`
     - `source_idl_by_dept` (multi)
     no `contract_ledger.json`
   - remover o fallback `\"0\" * 64`
4) Adicionar testes:
   - onboarding gera bundle com `source_idl_sha256` real
   - seed DSL existe no bundle gerado (source.idl / departments/<dept>/source.idl)
   - hash confere
   - proof PASS

Saída esperada:
- Patch mínimo + testes + atualização breve da spec (se necessário).
[[CLAUDE_CODE_END]]
