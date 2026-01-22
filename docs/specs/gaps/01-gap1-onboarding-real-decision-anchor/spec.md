# GAP 1 — Decisão versionável desde o primeiro dia (âncora real)

## A) Resumo de correção (rastreabilidade)

- **Intenção original (spec anterior):** remover `source_idl_sha256` placeholder e copiar seed DSL por instituição/dept para o data root.
- **Intenção corrigida (produção no cliente):** garantir que **toda instalação inicial** (templates/onboarding) produza um bundle com **âncora real e verificável offline**, sem placeholders, e com seed DSL/IDL preservado de forma versionável desde o primeiro deploy.
- **Impacto:** onboarding passa a ser um caminho “honesto de produção”: sem seed → falha determinística; com seed → hash real + evidência.

### O que foi mantido da versão anterior
- A tese central: **DSL UTF-8 é a fonte**, `source_idl_sha256` é o hash da decisão.
- A direção de implementação: seeds declarados por template e copiados no onboarding.

### O que foi alterado
- Em produção, placeholder é **proibido**: remover fallback `0 * 64` e falhar se seed não existir.
- Exigir que a âncora seja verificável offline **a partir do bundle** (sem depender do path externo do data root).

### O que foi descartado por viés de “piloto”
- Permitir placeholder para “não bloquear demo”.

## B) Spec técnica corrigida (contrato)

### Objetivo
Garantir decisão versionável desde o primeiro dia:

- `source_idl_sha256` **não pode** ser placeholder em bundles gerados
- seed DSL/IDL v1.2.2 deve existir e ser preservado para auditoria
- prova offline deve conseguir verificar a âncora **sem runtime**

### Estado atual (com arquivos/linhas reais)
- Onboarding reescreve `contract_ledger.json` e:
  - quando não existe `source_idl_sha256`, gera placeholder `0 * 64`:
    - `src/engine/console/bundle_generator.py:100-110`
- Prova offline hoje valida apenas “presença + formato” de `source_idl_sha256`:
  - `src/engine/proof/verify.py` (Step 6: valida `source_idl_sha256` via `is_valid_sha256_hex`)

### Mudanças necessárias (mínimas)
1) **Seeds por template**
   - O template registry deve declarar seeds DSL por dept para cada template disponível no onboarding.
   - Os seeds devem viver no repo e serem copiados junto com o bundle gerado.

2) **Armazenar seed DSL dentro do bundle gerado (para prova offline)**
   - Para *single-dept bundle*: adicionar `source.idl` na raiz do bundle gerado.
   - Para *multi-dept bundle*: adicionar `departments/<dept_id>/source.idl` para cada dept do template.
   - Esses arquivos devem entrar no `bundle.manifest.json` como contracts (required=false).

3) **Calcular âncora real e remover placeholder**
   - `source_idl_sha256` deve ser derivado do(s) seed(s) DSL UTF-8:
     - single: `sha256(source.idl bytes)`
     - multi: `sha256( concatenação determinística: "<dept_id>:<sha256(seed_bytes)>\n" ordenado por dept_id )`
   - Remover fallback `0 * 64`. Se seed não existir → falha determinística no onboarding.

4) **Evidência no ledger do bundle**
   - `contract_ledger.json` deve incluir:
     - `source_idl_sha256` (como hoje)
     - `source_idl_version` (já existe em IR; se não existir, setar `idl.v1.2.2`)
     - `source_idl_by_dept` (somente multi; mapa dept_id → sha256(seed))
   - Isso não muda o ABI do proof (campos extras são permitidos).

### Restrições explícitas (o que NÃO mudar)
- Não quebrar `engine.proof.verify_bundle_offline()` nem o schema do manifest usado pelo loader.
- Não inventar “DSL gerada” em runtime; seeds são arquivos estáticos.
- Não introduzir um novo pipeline de deploy: apenas onboarding/templates.

### Eventos de ledger afetados
- Mantém os eventos atuais do onboarding (“bundle_generated” no `contract_ledger.json.audit_trail`).
- Opcional (se existir ledger de instituição no onboarding): emitir evento `TEMPLATE_SEED_INSTALLED` com:
  - template_id, bundle_name, dept_ids, source_idl_sha256, source_idl_by_dept

### Riscos técnicos
- “Circular hashing” já é tratado removendo `contract_ledger.json` do manifest; adicionar `source.idl` não cria circularidade, mas exige atualizar hashes corretamente.

### Impacto esperado
- Templates deixam de ser “bundle solto” e passam a carregar a decisão versionável desde o primeiro dia.
- Auditor consegue validar offline: manifest/ledger/contracts e a âncora do DSL.

## C) Critérios de aceite (produção)

- **PASS/FAIL (runtime/console):**
  - Gerar `finance-pilot` via onboarding resulta em bundle com `source.idl` presente e `source_idl_sha256` real.
  - Gerar `multi-pilot` via onboarding resulta em `departments/finance/source.idl` e `departments/support/source.idl` + `source_idl_by_dept` preenchido + `source_idl_sha256` agregado real.
  - Se template não tiver seed DSL declarado/arquivo → onboarding falha com erro determinístico (sem placeholder).
- **Evidências esperadas no bundle:**
  - `bundle.manifest.json` inclui `source.idl` (single) ou `departments/<dept>/source.idl` (multi) com `required=false`.
  - `contract_ledger.json.source_idl_sha256` é 64-hex e não é `000...`.
- **Prova:**
  - `python -m engine.proof verify <bundle>` continua PASS.
- **Testes automatizados:**
  - Teste valida hash do seed e a âncora resultante.
  - Teste valida proof PASS.

## D) Prompt para Claude Code (ver `prompts.md`)
