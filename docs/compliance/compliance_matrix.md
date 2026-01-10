# Compliance Control Matrix

**Document Version:** 1.0
**Last Updated:** 2024-01-15
**Classification:** Internal / Audit Reference

---

## 1. Escopo de Compliance

### O que este mapeamento cobre

Este documento mapeia os controles técnicos implementados no **Bazari Engine** contra requisitos típicos de frameworks de compliance enterprise. O mapeamento abrange:

- Pipeline de geração de software (Intake → Gates → Execução → Release)
- Gestão de mudanças via Change Requests
- Aprovações e autorizações
- Trilha de auditoria e rastreabilidade
- Integridade de artefatos
- Verificação offline via AuditPack

### O que este mapeamento NÃO cobre

| Área Excluída | Razão |
|---------------|-------|
| Controles físicos | Segurança de datacenter, acesso físico |
| Recursos Humanos | Background checks, treinamento, desligamento |
| Segurança de rede | Firewalls, IDS/IPS, segmentação |
| Gestão de identidades | IAM, SSO, MFA (sistema assume identidade já validada) |
| Continuidade de negócios | DR, BCP, RPO/RTO |
| Segurança de endpoints | Antivírus, EDR, hardening de workstations |
| Criptografia em trânsito/repouso | TLS, disk encryption (responsabilidade da infra) |

### Natureza do Mapeamento

**Este documento é um mapeamento técnico, não uma certificação.**

O objetivo é demonstrar que os controles técnicos existentes atendem aos requisitos de frameworks de compliance, permitindo que auditores verifiquem a conformidade usando os artefatos gerados pelo próprio sistema.

---

## 2. Frameworks de Referência

### SOC2 Trust Services Criteria

| Critério | Áreas Relevantes |
|----------|------------------|
| CC6 (Logical and Physical Access) | Approval Gate, episode immutability |
| CC7 (System Operations) | RunLog, telemetry, error tracking |
| CC8 (Change Management) | Change Requests, Impact Gate, episode chaining |

### ISO 27001:2022 Controls

| Controle | Descrição | Relevância |
|----------|-----------|------------|
| A.8.9 | Configuration management | IDL contracts, versioned schemas |
| A.8.25 | Secure development lifecycle | Gates, contract validation |
| A.8.32 | Change management | CR workflow, approval gate |
| A.8.34 | Protection of information systems during audit testing | AuditPack, offline verification |

### Controles Bancários Típicos

| Categoria | Requisito Comum | Aplicabilidade |
|-----------|-----------------|----------------|
| Change Advisory Board (CAB) | Aprovação formal de mudanças | Approval Gate obrigatório |
| Segregation of Duties | Separação entre desenvolvedor e aprovador | Approval requer identidade distinta |
| Audit Trail | Rastreabilidade completa | Episode chain, RunLog |
| Non-Repudiation | Impossibilidade de negar ação | Approval records com identidade |

---

## 3. Tabela de Controles

### 3.1 Change Management

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Change Management | Toda mudança deve ser formalmente documentada | Change Request (CR) com schema `change_request.v1` | `change_request.json` com `change_request_id`, `requester`, `reason`, `scope` | `.engine/episodes/<id>/change_request/change_request.json` |
| Change Management | Mudanças devem ter escopo declarado | CR contém `scope.entities_affected`, `scope.usecases_affected`, `target` | CR JSON com campos de escopo | `cat .engine/episodes/<id>/change_request/change_request.json \| jq .scope` |
| Change Management | Escopo declarado deve ser respeitado | Impact Gate valida paths contra `target` | `blocked_reason: "IMPACT_OUT_OF_SCOPE"` no RunLog se violado | `runlog.json` campo `blocked_reason` |
| Change Management | Mudanças muito amplas devem ser bloqueadas | Impact Gate com `MAX_AFFECTED_FILES=25`, `MAX_UNIQUE_TOP_DIRS=4` | `blocked_reason: "IMPACT_TOO_BROAD"` | `runlog.json` campo `blocked_reason` |
| Change Management | Cadeia de mudanças deve ser rastreável | Episode linking via `previous_episode_id` | `manifest.json` campo `links.previous_episode_id` | `.engine/episodes/<id>/manifest.json` |
| Change Management | Hash do CR deve ser preservado | `cr_hash_sha256` computado de JSON canônico | `manifest.json` campo `links.cr_hash_sha256` | Comparar hash stored vs `cr_hash_sha256(cr)` |

### 3.2 Approval & Authorization

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Approval | Release requer aprovação explícita | Approval Gate bloqueia sem approval | `blocked_reason: "APPROVAL_REQUIRED"` | `runlog.json` se release tentado sem approval |
| Approval | Aprovação deve identificar aprovador | Approval record com `approver.name`, `approver.role`, `approver.org` | `approval.json` | `.engine/episodes/<id>/approvals/approval.json` |
| Approval | Aprovação deve ter justificativa | Campo `reason` obrigatório no approval | `approval.json` campo `reason` | `jq .reason approval.json` |
| Approval | Aprovação vinculada ao episódio específico | Validation `approval.episode_id == episode.episode_id` | `APPROVAL_INVALID` se mismatch | `approval_gate.py` validation |
| Approval | Decisão deve ser explícita | Campo `decision` com valores `approve` ou `reject` | `approval.json` campo `decision` | `jq .decision approval.json` |
| Authorization | Paths sensíveis são proibidos | `FORBIDDEN_PATTERNS` no Impact Gate | `blocked_reason: "IMPACT_FORBIDDEN_PATH"` | `runlog.json` se path sensível detectado |

### 3.3 Audit Trail & Logging

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Audit Trail | Toda execução gera registro | RunLog com schema `runlog.v1` | `runlog.json` com `execution_id`, `final_status`, `duration_ms` | `demo_store/<project>/runlog.json` |
| Audit Trail | Erros são codificados deterministicamente | `error_codes[]` em paridade 1:1 com `errors[]` | Arrays `errors` e `error_codes` no RunLog | `jq '.errors, .error_codes' runlog.json` |
| Audit Trail | Status final é explícito | Campo `final_status` com valores `success`, `blocked`, `failed` | `runlog.json` campo `final_status` | `jq .final_status runlog.json` |
| Audit Trail | Razão de bloqueio é explícita | Campo `blocked_reason` quando `final_status != success` | `blocked_reason` com valor canônico (ex: `GATE1_FAILED`) | `jq .blocked_reason runlog.json` |
| Audit Trail | Métricas de execução preservadas | Campos `duration_ms`, `metrics.*` | `runlog.json` seção `metrics` | `jq .metrics runlog.json` |
| Audit Trail | Contratos gerados são registrados | ContractLedger com hash por artefato | `runlog.json` seção `contract_ledger` | `jq .contract_ledger runlog.json` |
| Audit Trail | Eventos de telemetria emitidos | Telemetry events com `execution_id`, `stage`, `event` | stdout JSON lines | Filtrar por `"event":` em logs |

### 3.4 Integrity & Tamper Detection

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Integrity | Episódios são imutáveis após finalização | `is_finalized()` check em todas operações mutantes | `EpisodeImmutableError` se tentativa | Tentar modificar episódio finalizado |
| Integrity | Hash raiz do episódio verificável | `episode_root_hash_sha256` de sorted files | `manifest.json` campo `integrity.episode_root_hash_sha256` | `python -m episodes.episodes_cli show --episode-id <id>` |
| Integrity | Hashes individuais de arquivos | `file_hashes[]` no manifest | `manifest.json` campo `integrity.file_hashes` | `jq .integrity.file_hashes manifest.json` |
| Integrity | Verificação de integridade disponível | `verify_integrity()` recomputa e compara | `(True, None)` ou `(False, "Hash mismatch...")` | `EpisodeStore().verify_integrity(episode_id)` |
| Integrity | Contratos têm hash individual | `content_hash_sha256` por artefato no ContractLedger | `contract_ledger.<kind>.content_hash_sha256` | `jq .contract_ledger runlog.json` |
| Integrity | Legacy bundles verificados | Legacy Gate valida schema + hash | `legacy_contract_gate_ok`, `legacy_hashes` no RunLog | `jq .legacy runlog.json` |
| Integrity | Blueprint registry verificável | `verify_registry()` compara hashes | `RegistryIntegrityError` se tampered | `python -c "from blueprints.registry_v1 import verify_registry; verify_registry()"` |

### 3.5 Segregation of Duties

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Segregation | Aprovador deve ser identificado | `approver.name`, `approver.role` obrigatórios | `approval.json` com dados do aprovador | `jq .approver approval.json` |
| Segregation | Aprovação é ação separada da execução | CLI `approve` distinto de `run` | Approval timestamp vs episode creation timestamp | Comparar `manifest.created_at` com `approval.volatile.timestamp` |
| Segregation | Approval não pode ser auto-gerado pelo pipeline | Approval Gate requer arquivo externo | Ausência de approval → `APPROVAL_REQUIRED` | Pipeline sem approval bloqueia |

### 3.6 Input Validation

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Input Validation | Entrada validada contra schema | JSON Schema validation com `jsonschema` | `GATE1_FAILED` ou `GATE2_BLOCKED` se inválido | `runlog.json` campo `blocked_reason` |
| Input Validation | Schema version explícito | Campo `schema_version` obrigatório | Ex: `idl_draft.v1`, `idl.v1`, `change_request.v1` | `jq .schema_version <input>.json` |
| Input Validation | Path traversal bloqueado | Check `..` em todos paths | `IMPACT_FORBIDDEN_PATH` se detectado | `runlog.json` |
| Input Validation | Patterns sensíveis bloqueados | `FORBIDDEN_PATTERNS` list | Bloqueio de `.env`, `secrets/`, `private_key`, etc. | `gates/impact_gate.py` constante |

### 3.7 Release Governance

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Release | Release requer build success | Pipeline stage dependency | `BUILD_FAILED` se compilação falha | `runlog.json` |
| Release | Release requer smoke tests | Smoke runner em modo `--release` | `SMOKE_FAILED` se testes falham | `runlog.json` |
| Release | Release requer approval | Approval Gate mandatory | `APPROVAL_REQUIRED` se missing | `runlog.json` |
| Release | Episódio criado para cada release | Episode com `execution_id` | `.engine/episodes/<execution_id>/` | `ls .engine/episodes/` |
| Release | AuditPack gerável para compliance | `auditpack` CLI command | `audit-<episode>.zip` com `index.json` | `python -m episodes.episodes_cli auditpack --episode-id <id> --out audit.zip` |

### 3.8 Traceability

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Traceability | Input → Output rastreável | `inputs.input_hash_sha256` no manifest | `manifest.json` seção `inputs` | `jq .inputs manifest.json` |
| Traceability | Contratos intermediários preservados | `contracts/` directory no episódio | `idl.json`, `srs.json`, `ir.json`, `oas.json`, `plan.json` | `ls .engine/episodes/<id>/contracts/` |
| Traceability | Cadeia de episódios navegável | `previous_episode_id` linking | `manifest.json` campo `links` | Seguir chain via `previous_episode_id` |
| Traceability | CR original preservado | `change_request/change_request.json` no episódio | CR completo no episódio | `.engine/episodes/<id>/change_request/` |
| Traceability | Output hash preservado | `outputs.repo_hash_sha256` | `manifest.json` seção `outputs` | `jq .outputs manifest.json` |

### 3.9 Incident Analysis (Post-Mortem)

| Categoria | Requisito de Compliance | Mecanismo no Sistema | Evidência Gerada | Onde Verificar |
|-----------|------------------------|---------------------|------------------|----------------|
| Incident Analysis | Erros são reproduzíveis | Error codes determinísticos | `error_codes[]` canônico | `jq .error_codes runlog.json` |
| Incident Analysis | Pipeline state capturado | RunLog com todos stages | `runlog.json` completo | `cat runlog.json` |
| Incident Analysis | Input original preservado | `input/` directory no episódio | Arquivo de entrada original | `.engine/episodes/<id>/input/` |
| Incident Analysis | Fix loop documentado | `fix_attempts`, `fixes_applied` no RunLog | Histórico de correções tentadas | `jq .fix_loop runlog.json` |
| Incident Analysis | Diagnostic report disponível | Diagnostic report artifact | `diagnostic_report.json` | `demo_store/<project>/diagnostic_report.json` |

---

## 4. Controles por Fase do Ciclo de Vida

### 4.1 Entrada (Wizard / Draft)

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| Schema validation | Wizard session schema `wizard_session.v1` | `WIZARD_SCHEMA_INVALID` se inválido |
| Blueprint registry integrity | Hash verification antes de aplicar | `WIZARD_REGISTRY_INTEGRITY_ERROR` se tampered |
| Session tracking | Session ID único `wiz-<hex>` | `wizard/sessions/<session_id>/` |
| Export validation | IDL Draft schema validation no export | `idl_draft.json` validado |

### 4.2 Contratos (IDL, Gates)

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| IDL schema validation | `idl.v1` JSON Schema | `GATE1_FAILED` se schema inválido |
| Contract hash recording | ContractLedger entry por artefato | `contract_ledger` no RunLog |
| Contract gate pass/fail | Boolean `contract_gate_ok` | `contract_gate_error` se falhou |
| SRS/IR/OAS generation tracking | Hash de cada contrato gerado | `content_hash_sha256` por kind |

### 4.3 Execução

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| Execution ID determinístico | `exec-<timestamp>-<random>` ou `change-<hex>` | `execution_id` no RunLog |
| Stage tracking | Telemetry events por stage | `{"stage": "...", "event": "start/end"}` |
| Duration tracking | `duration_ms` no RunLog | Tempo total de execução |
| Error capture | `errors[]` + `error_codes[]` 1:1 | Arrays paralelos no RunLog |

### 4.4 Release

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| Build validation | Maven/npm compile obrigatório | `BUILD_FAILED` se falha |
| Docker compose up | Container startup check | `DOCKER_UP_FAILED` se falha |
| Readiness check | Health endpoint polling | `READINESS_FAILED` se timeout |
| Smoke tests | Automated smoke test suite | `SMOKE_FAILED` se falha |
| Release report | Summary document | `release_report.json` |

### 4.5 Mudança

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| CR schema validation | `change_request.v1` schema | `CR_SCHEMA_INVALID` se inválido |
| Previous episode validation | `previous_episode_id` must exist | `PREVIOUS_EPISODE_NOT_FOUND` se não existe |
| CR-argument match | `CR.previous_episode_id == --previous-episode-id` | `CR_PREVIOUS_MISMATCH` se diferente |
| Impact assessment | Impact Gate analysis | `ImpactGateResult` com metrics |
| Episode chaining | New episode links to previous | `links.previous_episode_id` no manifest |

### 4.6 Auditoria

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| AuditPack generation | ZIP with deterministic structure | `auditpack/index.json` |
| Root hash computation | `<path>\n<sha256>\n` blob hash | `root_hash_sha256` no index |
| Security check | Forbidden patterns blocked | `AUDITPACK_SECURITY_BLOCKED` se violado |
| Offline verification | README with verification code | `README_AUDIT.md` com scripts |
| sha256sums file | Standard checksum format | `hashes/sha256sums.txt` |

---

## 5. O que o Sistema ELIMINA por Design

### 5.1 Mudança sem Aprovação

**Eliminado:** Release de código sem aprovação formal registrada.

**Mecanismo:** Approval Gate verifica presença de `approval.json` com `decision: "approve"` e `episode_id` matching.

**Se violado:** Pipeline bloqueia com `blocked_reason: "APPROVAL_REQUIRED"`.

---

### 5.2 Release sem Rastreabilidade

**Eliminado:** Código em produção sem registro de origem.

**Mecanismo:** Todo release cria episódio com:
- `execution_id` único
- `inputs.input_hash_sha256`
- `outputs.repo_hash_sha256`
- `contract_ledger` com hashes de todos artefatos

**Verificável:** Dado código em produção, é possível identificar episódio de origem via hashes.

---

### 5.3 Alteração Silenciosa de Histórico

**Eliminado:** Modificação de episódios anteriores sem detecção.

**Mecanismo:**
- Episódios são append-only após `finalize_episode()`
- `episode_root_hash_sha256` computado de todos arquivos
- `verify_integrity()` detecta qualquer modificação

**Se violado:** Hash mismatch detectável via verificação.

---

### 5.4 Dependência de Confiança Implícita

**Eliminado:** Assumir que artefatos não foram modificados.

**Mecanismo:**
- Todos artefatos têm `content_hash_sha256`
- Legacy bundles verificados via Legacy Gate
- Blueprint registry com hash verification
- AuditPack com verificação offline

**Filosofia:** Zero-trust em artefatos. Verificação explícita sempre possível.

---

### 5.5 Erro sem Código Determinístico

**Eliminado:** Erros ambíguos ou não reproduzíveis.

**Mecanismo:**
- Todo erro tem `error_code` canônico
- `errors[]` e `error_codes[]` em paridade 1:1
- Prefixos padronizados: `SCHEMA:`, `INTEGRITY:`, `IMPACT:`, `GOVERNANCE:`, `SECURITY:`, `POLICY:`

**Resultado:** Dado `error_code`, comportamento é determinístico e documentado.

---

### 5.6 IA após Gates (Comportamento Não-Determinístico)

**Eliminado:** Decisões não-determinísticas após validação de contratos.

**Mecanismo:**
- IA usada apenas para geração de contratos (SRS, IR)
- Após Contract Gate, processamento é puramente determinístico
- Patch engine segue regras fixas, não LLM

**Garantia:** Dado mesmo input, mesma saída de patch (modulo timestamps voláteis).

---

### 5.7 Escopo Não Declarado

**Eliminado:** Mudanças afetando áreas não declaradas no CR.

**Mecanismo:**
- CR declara `target` (frontend, backend, db, etc.)
- Impact Gate valida paths contra `TARGET_PATH_MAPPING`
- Paths fora do escopo → `IMPACT_OUT_OF_SCOPE`

**Resultado:** Impossível afetar `backend/` se CR declara `target: "frontend"`.

---

## 6. Limitações e Dependências Externas

### 6.1 Dependências de Infraestrutura

| Dependência | Responsabilidade | Impacto se Comprometido |
|-------------|------------------|------------------------|
| File system integrity | Infraestrutura | Modificação de arquivos entre operações não detectada em tempo real |
| Docker daemon | Infraestrutura | Containers podem ser modificados se daemon comprometido |
| OS user permissions | Infraestrutura | Usuário com sudo pode bypassar controles |
| Network isolation | Infraestrutura | Exfiltração de dados possível se rede não segmentada |

### 6.2 Controles Detectáveis mas não Fisicamente Impedidos

| Cenário | Detecção | Prevenção |
|---------|----------|-----------|
| Modificação de episódio no filesystem | `verify_integrity()` detecta hash mismatch | Não impedido fisicamente |
| Criação manual de approval.json | Auditoria detecta padrões anômalos | Não impedido fisicamente |
| Modificação de blueprint | `verify_registry()` detecta | Não impedido fisicamente |
| Modificação de RunLog | Hash não protege RunLog diretamente | Não impedido fisicamente |

### 6.3 Controles Organizacionais Ainda Necessários

| Área | Controle Necessário | Sistema Fornece |
|------|---------------------|-----------------|
| Identidade do aprovador | Verificação de que aprovador é quem diz ser | Registro de `approver.name`, `approver.role` |
| Segregação real | Garantia de que aprovador ≠ desenvolvedor | Evidência de identidades distintas |
| Política de aprovação | Definição de quem pode aprovar o quê | Framework para registro de approval |
| Revisão de código | Garantia de revisão efetiva | Evidência de que approval foi registrado |
| Backup e retenção | Preservação de episódios por período exigido | Artefatos estruturados para backup |

### 6.4 Limitações Conhecidas do Sistema

| Limitação | Descrição | Mitigação |
|-----------|-----------|-----------|
| Assinatura manual | Approval sem verificação criptográfica | Controle organizacional + audit trail |
| Single approver | Sem suporte nativo a multi-party approval | Controle organizacional |
| Timestamps voláteis | Timestamps excluídos de hashes | Sequência de episódios fornece ordenação |
| File system trust | Confiança em integridade entre operações | Verificação antes de operações críticas |
| No real-time monitoring | Detecção apenas em verificação explícita | Integração com monitoring externo |

---

## 7. Conclusão Executiva

### Sistema Compliance-by-Design

O Bazari Engine implementa controles de compliance **por design**, não por política declarativa. Cada controle é:

1. **Implementado em código** - Não depende de processo manual para enforcement
2. **Verificável por artefatos** - Auditor pode validar usando apenas os arquivos gerados
3. **Determinístico** - Mesmo input produz mesma decisão de controle

### Auditoria Retroativa Trivial

Dado qualquer episódio no sistema, um auditor pode:

```bash
# 1. Verificar integridade do episódio
python -m episodes.episodes_cli show --episode-id <id>

# 2. Verificar aprovação
cat .engine/episodes/<id>/approvals/approval.json

# 3. Verificar chain de mudanças
jq .links.previous_episode_id .engine/episodes/<id>/manifest.json

# 4. Gerar pacote de auditoria offline
python -m episodes.episodes_cli auditpack --episode-id <id> --out audit.zip

# 5. Verificar integridade do pacote (offline, sem sistema)
cd auditpack && sha256sum -c hashes/sha256sums.txt
```

### Controles Verificáveis, Não Declarativos

| Aspecto | Declarativo (tradicional) | Verificável (este sistema) |
|---------|---------------------------|---------------------------|
| "Mudança foi aprovada" | Documento afirma aprovação | `approval.json` com hash linkado ao episódio |
| "Escopo foi respeitado" | Checklist manual | Impact Gate validou paths automaticamente |
| "Código não foi alterado" | Confiança no processo | `episode_root_hash_sha256` verificável |
| "Erro foi documentado" | Log manual | `error_codes[]` determinístico no RunLog |

### Adequação para Ambientes Regulados

O sistema fornece os primitivos necessários para compliance em ambientes enterprise e bancários:

- **Change Management**: CR formal, Impact Gate, episode chaining
- **Approval Workflow**: Gate obrigatório, audit trail, identidade registrada
- **Audit Trail**: RunLog canônico, episódios imutáveis, AuditPack offline
- **Integrity**: Hashes SHA256 em todos níveis, verificação disponível
- **Traceability**: Input → Contracts → Output completamente rastreável

### Recomendações para Auditores

1. **Verificar integridade** de episódios antes de aceitar evidências
2. **Gerar AuditPack** para preservação offline de evidências
3. **Validar episode chain** para mudanças incrementais
4. **Confirmar approval records** linkam ao episódio correto
5. **Executar sha256sum** em artefatos do AuditPack

### Limitações a Considerar

1. Assinatura de approval é manual, não criptográfica
2. Controles organizacionais necessários para identidade e segregação
3. Dependência de infraestrutura para proteção física de arquivos
4. Detecção de tampering requer verificação explícita

---

**Este documento serve como referência técnica para mapeamento de compliance. Não constitui certificação SOC2, ISO 27001, ou qualquer outro framework. A conformidade formal requer avaliação por auditor qualificado.**
