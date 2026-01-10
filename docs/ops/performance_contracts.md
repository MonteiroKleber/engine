# Performance & Scale Contracts

**Document Version:** 1.0
**Last Updated:** 2024-01-15
**Classification:** Technical Reference

---

## 1. Escopo do Contrato de Performance

### O que este contrato cobre

Este documento define os contratos de performance para os seguintes componentes:

| Componente | Descrição |
|------------|-----------|
| Engine Pipeline | Intake → Gates → Artefatos → Build → Release |
| Wizard | Session management, export |
| Gates | Contract Gate, Impact Gate, Approval Gate, Legacy Gate |
| Legacy Verify | Validation de legacy bundles |
| AuditPack | Geração de pacotes de auditoria |
| Episode Store | Operações de criação, finalização, verificação |

### O que este contrato NÃO cobre

| Área Excluída | Razão |
|---------------|-------|
| Infraestrutura | CPU, memória, I/O são responsabilidade do ambiente |
| Hardware | Performance depende de recursos alocados |
| Rede | Latência e bandwidth são externos |
| Docker daemon | Startup time de containers é variável |
| Storage externo | IOPS e latência dependem do backend |
| LLM provider | Tempo de resposta de APIs externas |
| Maven/npm registries | Download de dependências é externo |

---

## 2. Princípios de Performance (por Design)

### 2.1 Determinismo acima de Throughput

**Princípio:** O sistema prioriza resultados reproduzíveis sobre velocidade de execução.

**Mecanismo:**
- Hash computation usa canonical JSON (`sort_keys=True`, `separators=(",", ":")`)
- Todos artefatos são ordenados antes de processamento
- Nenhum paralelismo implícito que altere ordem de operações

**Implicação:** Dado o mesmo input, o sistema produz os mesmos hashes, independente de timing.

---

### 2.2 Fail-Fast em Gates

**Princípio:** Gates validam e falham imediatamente ao detectar violação.

**Mecanismo:**
- GATE1 (Draft validation) falha antes de compilação
- GATE2 (IDL validation) falha antes de geração
- Impact Gate falha antes de patch application
- Approval Gate falha antes de release

**Implicação:** Erros são detectados na fase mais precoce possível, evitando trabalho downstream.

---

### 2.3 Custos Previsíveis por Fase

**Princípio:** Cada fase tem custo computacional proporcional ao input, não ao histórico.

**Mecanismo:**
- Nenhuma fase acumula estado de execuções anteriores
- Cada episódio é independente
- Hash computation é O(n) onde n = tamanho dos arquivos

**Implicação:** Tempo de execução depende do tamanho do input atual, não do número de episódios existentes.

---

### 2.4 Ausência de Paralelismo Implícito

**Princípio:** Todas operações são sequenciais e explícitas.

**Mecanismo:**
- Pipeline executa fases em ordem fixa
- Nenhum thread pool ou executor paralelo
- Build validation executa componentes sequencialmente

**Implicação:** Performance é previsível; não há contenção de recursos ou race conditions.

---

### 2.5 Bounded Loops

**Princípio:** Todos loops têm limites explícitos definidos em código.

**Mecanismo:**
- Fix Loop: `MAX_FIX_ATTEMPTS = 3`
- Questions per round: `max_questions_per_round = 7`
- Patches per iteration: limitado a 1 patch por causa

**Implicação:** Nenhuma execução pode entrar em loop infinito.

---

## 3. Fases do Pipeline e Métricas Observáveis

### 3.1 Wizard

| Operação | O que acontece | Métricas | Onde aparecem |
|----------|----------------|----------|---------------|
| `start` | Cria session directory, inicializa estado | `duration_ms` | `wizard_runlog.json` |
| `resume` | Carrega session existente | `duration_ms` | `wizard_runlog.json` |
| `export` | Gera IDL Draft, valida, salva | `duration_ms`, `export_path` | `wizard_runlog.json` |
| `apply-blueprint` | Merge blueprint com session | `duration_ms`, `blueprint_id` | `wizard_runlog.json` |

**Campos em wizard_runlog.json:**
```json
{
  "schema_version": "wizard_runlog.v1",
  "session_id": "wiz-abc123",
  "operation": "export",
  "success": true,
  "duration_ms": 150.5,
  "blocked_reason": null
}
```

---

### 3.2 IDL Draft Validation (GATE 1)

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| JSON parse | Tempo de parse | `duration_ms` em telemetry |
| Schema validation | Pass/fail | `blocked_reason: "GATE1_FAILED"` |
| Field validation | Errors count | `errors[]`, `error_codes[]` |

**Telemetry event:**
```json
{
  "execution_id": "exec-123",
  "stage": "gate1",
  "event": "end",
  "duration_ms": 45.2,
  "blocked_reason": ""
}
```

---

### 3.3 IDL Compile (GATE 2)

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| Draft → IDL transformation | Tempo de compilação | `duration_ms` |
| Semantic validation | Pass/fail | `blocked_reason: "GATE2_BLOCKED"` |
| Hash computation | Hash do IDL | `contract_ledger.idl.content_hash_sha256` |

---

### 3.4 Legacy Verify

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| Schema version check | Pass/fail | `legacy_schema_ok` |
| Content hash verification | Pass/fail | `legacy_contract_gate_ok` |
| Ledger cross-reference | Hash match | `legacy_hashes` |

**Campos no RunLog:**
```json
{
  "legacy": {
    "ok": true,
    "provided": true,
    "legacy_schema_ok": true,
    "legacy_contract_gate_ok": true,
    "legacy_hashes": {
      "inventory": "abc123...",
      "human_process": "def456..."
    },
    "errors": [],
    "error_codes": []
  }
}
```

---

### 3.5 Artifact Generation

| Artefato | O que acontece | Métricas | Onde aparecem |
|----------|----------------|----------|---------------|
| SRS | Requirements specification | `requirements_count` | `telemetry.counts` |
| IR | Intermediate representation | `entities_count`, `operations_count` | `telemetry.counts` |
| OpenAPI | API specification | Operations count | `contract_ledger.oas` |
| RBAC | Roles and permissions | Roles count | `contract_ledger.rbac` |
| Plan | Execution plan | `tasks_count` | `telemetry.counts` |

**TelemetryCounts:**
```json
{
  "counts": {
    "requirements_count": 5,
    "entities_count": 3,
    "operations_count": 12,
    "tasks_count": 8,
    "patch_count": 15
  }
}
```

---

### 3.6 Patch Engine

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| Patch generation | `patch_count` | `telemetry.counts` |
| Patch validation | `rewrite_ratio` per file | `patch_manifest.patches[]` |
| Patch application | Files modified | `patch_manifest.files_modified` |

**Patch Manifest metrics:**
```json
{
  "patches": [
    {
      "file_path": "backend/src/User.java",
      "lines_changed": 5,
      "rewrite_ratio": 0.15
    }
  ],
  "policy": {
    "max_rewrite_ratio": 0.80
  }
}
```

---

### 3.7 Build Validation

| Componente | O que acontece | Métricas | Onde aparecem |
|------------|----------------|----------|---------------|
| Backend | Maven compile | `build_ok`, `duration_ms` | `runlog.json` |
| Frontend | npm build | `build_ok`, `duration_ms` | `runlog.json` |
| Fix Loop | Correction attempts | `fix_attempts`, `fixes_applied` | `runlog.json` |

**Fix Loop metrics:**
```json
{
  "fix_loop": {
    "total_attempts": 2,
    "success": true,
    "aborted_reason": "",
    "attempts": [
      {
        "attempt_number": 1,
        "status": "build_failed",
        "error_classified": {...}
      },
      {
        "attempt_number": 2,
        "status": "success"
      }
    ]
  }
}
```

---

### 3.8 Approval Gate

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| Approval check | Present/absent | `approval_status` |
| Episode ID match | Valid/invalid | `blocked_reason: "APPROVAL_INVALID"` |
| Decision check | approve/reject | `approval.decision` |

---

### 3.9 AuditPack Generation

| O que acontece | Métricas | Onde aparecem |
|----------------|----------|---------------|
| File collection | `total_files` | `auditpack_index.stats` |
| Hash computation | Time proportional to size | `duration_ms` |
| ZIP creation | `total_size_bytes` | `auditpack_index.stats` |
| Security check | Forbidden patterns | `AUDITPACK_SECURITY_BLOCKED` |

**AuditPack index stats:**
```json
{
  "stats": {
    "total_files": 12,
    "total_size_bytes": 45678,
    "has_approval": true,
    "has_change_request": false
  }
}
```

---

## 4. Limites Explícitos (Hard Limits)

### 4.1 Limites de Escopo

| Limite | Valor | Onde é aplicado | Comportamento ao exceder | Evidência gerada |
|--------|-------|-----------------|--------------------------|------------------|
| Max affected files | 25 | Impact Gate | `IMPACT_TOO_BROAD` | `blocked_reason` no RunLog |
| Max top directories | 4 | Impact Gate | `IMPACT_TOO_BROAD` | `blocked_reason` no RunLog |
| Max fix attempts | 3 | Fix Loop Agent | `FIX_LOOP_EXHAUSTED` | `aborted_reason: "max_attempts_exceeded"` |
| Max questions per round | 7 | SRS Validator | Questions truncadas | `questions[]` limitado |
| Max lines changed (fix) | 10 | Fix Patch Generator | Patch rejeitado | Fix attempt fails |

### 4.2 Limites de Integridade

| Limite | Valor | Onde é aplicado | Comportamento ao exceder | Evidência gerada |
|--------|-------|-----------------|--------------------------|------------------|
| Max rewrite ratio | 80% | Patch Engine | `PATCH_SECURITY` | `blocked_reason` no RunLog |
| Schema version mismatch | N/A | All validators | Gate failure | `SCHEMA:` prefix error |
| Hash mismatch | N/A | All gates | Integrity failure | `INTEGRITY:` prefix error |

### 4.3 Limites de Input

| Limite | Valor | Onde é aplicado | Comportamento ao exceder | Evidência gerada |
|--------|-------|-----------------|--------------------------|------------------|
| Max input size | 20,000 chars | Normalizer | Input truncado | `truncated: true` |
| Forbidden patterns | Lista fixa | Impact Gate, AuditPack | `IMPACT_FORBIDDEN_PATH` | `blocked_reason` |

### 4.4 Constantes de Código

```python
# gates/impact_gate.py
MAX_AFFECTED_FILES = 25
MAX_UNIQUE_TOP_DIRS = 4

# fix_loop/fix_loop_agent.py
MAX_FIX_ATTEMPTS = 3

# fix_loop/fix_patch_generator.py
MAX_LINES_CHANGED = 10

# intake/normalizer.py
MAX_INPUT_SIZE = 20_000

# observability/patch_manifest.py
max_rewrite_ratio = 0.80  # default

# validators/srs_validator.py
max_questions_per_round = 7  # default
```

---

## 5. Expectativas de Escala

### 5.1 Escala Linear com Tamanho de Input

| Operação | Complexidade | Observação |
|----------|--------------|------------|
| Hash computation | O(n) | n = bytes do arquivo |
| JSON parsing | O(n) | n = caracteres do JSON |
| Schema validation | O(n) | n = número de campos |
| File iteration | O(n) | n = número de arquivos |

### 5.2 Custo Previsível por Episódio

| Componente | Custo | Fatores |
|------------|-------|---------|
| Episode creation | Constante | Independe de episódios existentes |
| Episode finalization | O(n) | n = arquivos no episódio |
| Integrity verification | O(n) | n = arquivos no episódio |
| Episode listing | O(m) | m = número de episódios |

### 5.3 Comportamento com Legacy Bundles Grandes

| Cenário | Comportamento |
|---------|---------------|
| Inventory com muitos sistemas | Hash computation linear com tamanho |
| Human process extenso | Parse time linear |
| Múltiplos artifacts | Verificação sequencial de cada um |

### 5.4 Comportamento com Muitos Artefatos

| Cenário | Comportamento |
|---------|---------------|
| Muitas entidades no IR | Geração sequencial |
| Muitos patches | Aplicação sequencial |
| Muitos arquivos gerados | Build time aumenta proporcionalmente |

### 5.5 Comportamento com Pipelines Longos

| Cenário | Comportamento |
|---------|---------------|
| Build com muitos erros | Fix Loop limitado a 3 tentativas |
| Questions em SRS | Limitado a 7 por round |
| Smoke tests | Execução sequencial, timeout individual |

### 5.6 Comportamento com Múltiplos Episódios

| Cenário | Comportamento |
|---------|---------------|
| Listing de episódios | O(n) onde n = número de episódios |
| Verificação de todos | `verify_all()` é O(n × m) onde m = arquivos médio |
| Episode chaining | Lookup de previous é O(1) |

---

## 6. Anti-Objetivos de Performance

### 6.1 Não é Low-Latency

**O sistema não tenta:**
- Minimizar tempo de resposta individual
- Otimizar para sub-segundo responses
- Usar caching agressivo

**Por quê:** Governança requer verificação completa a cada operação. Caching poderia mascarar modificações.

---

### 6.2 Não é Real-Time

**O sistema não tenta:**
- Processar eventos em streaming
- Reagir a mudanças em tempo real
- Manter estado em memória entre execuções

**Por quê:** Auditabilidade requer execuções discretas com artefatos persistentes.

---

### 6.3 Não é Auto-Healing

**O sistema não tenta:**
- Corrigir erros automaticamente sem limite
- Recuperar de falhas silenciosamente
- Reiniciar operações failed

**Por quê:** Governança requer que falhas sejam explícitas e auditáveis. `MAX_FIX_ATTEMPTS = 3` existe por design.

---

### 6.4 Não é Throughput-Oriented

**O sistema não tenta:**
- Maximizar execuções por segundo
- Paralelizar para aumentar throughput
- Batch processing implícito

**Por quê:** Cada execução deve ser rastreável individualmente. Paralelismo implícito quebraria determinismo.

---

### 6.5 Não é Otimizado para Execução Contínua

**O sistema não tenta:**
- Manter conexões persistentes
- Warm-up de caches
- Pre-loading de dados

**Por quê:** Cada execução inicia do zero para garantir independência e reprodutibilidade.

---

## 7. Como Verificar Performance na Prática

### 7.1 Verificar Duração Total

```bash
# No RunLog
cat demo_store/<project>/runlog.json | jq .duration_ms
```

**Interpretação:** `duration_ms` é o tempo total em milissegundos desde intake até final_status.

---

### 7.2 Verificar Duração por Stage

```bash
# Filtrar telemetry events de end
grep '"event":"end"' output.log | jq -s '.[] | {stage, duration_ms}'
```

**Interpretação:** Cada stage emite `duration_ms` no evento de end.

---

### 7.3 Verificar Counts

```bash
# No RunLog
cat demo_store/<project>/runlog.json | jq .counts
```

**Output esperado:**
```json
{
  "requirements_count": 5,
  "entities_count": 3,
  "operations_count": 12,
  "tasks_count": 8,
  "patch_count": 15
}
```

---

### 7.4 Verificar Fix Loop

```bash
cat demo_store/<project>/runlog.json | jq .fix_loop
```

**Campos relevantes:**
- `total_attempts`: Quantas tentativas ocorreram
- `success`: Se build final passou
- `aborted_reason`: Por que parou (se não success)

---

### 7.5 Comparar Execuções

```bash
# Comparar duração entre execuções
diff <(cat runlog_v1.json | jq .duration_ms) \
     <(cat runlog_v2.json | jq .duration_ms)

# Comparar counts
diff <(cat runlog_v1.json | jq .counts) \
     <(cat runlog_v2.json | jq .counts)
```

---

### 7.6 Detectar Regressão

**Indicadores de regressão:**

| Métrica | Regressão se | Onde verificar |
|---------|--------------|----------------|
| `duration_ms` | Aumentou significativamente | `runlog.json` |
| `fix_loop.total_attempts` | Aumentou | `runlog.json` |
| `patch_count` | Aumentou sem mudança de input | `runlog.json` |
| Número de `errors` | Aumentou | `runlog.json` |

**Script de verificação:**
```bash
#!/bin/bash
# Comparar métricas entre duas execuções
OLD=$1
NEW=$2

echo "Duration:"
echo "  Old: $(jq .duration_ms $OLD)"
echo "  New: $(jq .duration_ms $NEW)"

echo "Fix attempts:"
echo "  Old: $(jq .fix_loop.total_attempts $OLD)"
echo "  New: $(jq .fix_loop.total_attempts $NEW)"

echo "Errors:"
echo "  Old: $(jq '.errors | length' $OLD)"
echo "  New: $(jq '.errors | length' $NEW)"
```

---

### 7.7 Verificar AuditPack Stats

```bash
unzip -p audit.zip auditpack/index.json | jq .stats
```

**Output esperado:**
```json
{
  "total_files": 12,
  "total_size_bytes": 45678,
  "has_approval": true,
  "has_change_request": false
}
```

---

## 8. Limitações Conhecidas

### 8.1 Dependência de Infraestrutura

| Componente | Dependência | Impacto |
|------------|-------------|---------|
| File I/O | Disk IOPS | Hash computation time |
| Process execution | CPU | Build time |
| Memory | RAM disponível | Large file processing |
| Network | Bandwidth | Maven/npm downloads |

### 8.2 Dependência do Tamanho de Input

| Input | Impacto |
|-------|---------|
| IDL Draft grande | Mais tempo de parsing e validation |
| Legacy bundle grande | Mais tempo de hash verification |
| Muitos patches | Mais tempo de application |
| Projeto grande | Mais tempo de build |

### 8.3 Detecção sem Prevenção

| Cenário | Detecta | Previne |
|---------|---------|---------|
| Build lento | Sim (duration_ms) | Não |
| Fix loop próximo do limite | Sim (total_attempts) | Não impede chegar a 3 |
| Hash computation lenta | Sim (stage duration) | Não |

### 8.4 Onde Sistema Detecta Degradação

| Degradação | Como detectar | Onde aparece |
|------------|---------------|--------------|
| Build ficou mais lento | `duration_ms` aumentou | `runlog.json` |
| Mais tentativas de fix | `total_attempts` aumentou | `runlog.json` |
| Mais erros | `errors.length` aumentou | `runlog.json` |
| Files aumentaram | `total_files` aumentou | `auditpack_index.json` |

### 8.5 Variabilidade Externa

| Fonte | Variabilidade | Mitigação |
|-------|---------------|-----------|
| LLM response time | Alta | Não controlável pelo sistema |
| Maven/npm download | Alta | Depende de registry e rede |
| Docker startup | Média | Depende de imagens e recursos |
| Disk I/O | Média | Depende de storage backend |

---

## 9. Conclusão Técnica

### Performance é Contractual, não Ad-Hoc

O sistema define limites explícitos em código:

```python
MAX_FIX_ATTEMPTS = 3      # Nunca mais que 3 tentativas
MAX_AFFECTED_FILES = 25   # Nunca mais que 25 arquivos
max_rewrite_ratio = 0.80  # Nunca mais que 80% de rewrite
```

Esses valores são **contratos**, não configurações. Mudá-los requer decisão arquitetural.

---

### Previsibilidade > Velocidade

| Escolha | Alternativa | Por que escolhemos |
|---------|-------------|-------------------|
| Sequencial | Paralelo | Determinismo garantido |
| Fail-fast | Retry infinito | Erros são explícitos |
| Bounded loops | Unbounded | Nunca loop infinito |
| Hash always | Hash on-demand | Integridade verificável |

---

### Aceitável e Desejável em Enterprise

**Por que isso é adequado:**

1. **Auditabilidade:** Cada execução produz artefatos verificáveis com métricas explícitas
2. **Previsibilidade:** Dado input de tamanho X, tempo é proporcional a X
3. **Rastreabilidade:** Degradação é detectável via comparação de RunLogs
4. **Governança:** Limites são enforced, não sugeridos

**Trade-off explícito:**
- **Aceitamos:** Execuções mais lentas que sistemas otimizados
- **Ganhamos:** Garantia de determinismo, auditabilidade, e governança

---

### Como Validar

Um arquiteto enterprise pode responder "isso escala?" verificando:

1. **Limites são explícitos?** Sim, definidos em constantes de código
2. **Complexidade é previsível?** Sim, O(n) em todos componentes
3. **Métricas são observáveis?** Sim, `duration_ms`, `counts`, `stats`
4. **Regressão é detectável?** Sim, comparando RunLogs
5. **Loops são bounded?** Sim, `MAX_FIX_ATTEMPTS = 3`

---

**Este documento define contratos de comportamento, não promessas de SLA. Performance real depende da infraestrutura onde o sistema executa.**
