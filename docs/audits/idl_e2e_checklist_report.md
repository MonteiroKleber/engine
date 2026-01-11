# IDL E2E Pipeline - Checklist de Validação Final

**Data:** 2026-01-10
**Executor:** Claude Opus 4.5
**Objetivo:** Validar comportamento canônico do pipeline IDL → IR → OAS → artefatos

---

## Resumo Executivo

| Status | Resultado |
|--------|-----------|
| **GERAL** | **OK** |
| Testes Passaram | 7/7 |
| Regressões | 0 |
| Anomalias Críticas | 0 |

---

## Resultado por Checklist

### 1️⃣ Smoke Test — IDL arquivo → pipeline (sem build)

**Status:** PASS

**Comando:**
```bash
python main.py \
  --project checklist_idl_file \
  --input /tmp/sample.idl \
  --input-mode idl \
  --skip-build
```

**Evidências:**
- `final_status`: `artifacts_only` → `success` (no runlog)
- `blocked_reason`: `None`
- `error_codes`: `[]` (presente e vazio)
- Artefatos gerados:
  - IR: `/home/bazari/engine/demo_store/checklist_idl_file/IR/v1.json`
  - OAS: `/home/bazari/engine/demo_store/checklist_idl_file/OAS/v1.yaml`
  - RBAC: `/home/bazari/engine/demo_store/checklist_idl_file/RBAC/v1.json`
  - PLAN: `/home/bazari/engine/demo_store/checklist_idl_file/PLAN/v1.json`
- `SRS Version`: `vNone` (correto - IDL pula SRS)

---

### 2️⃣ Smoke Test — IDL inline (string) → pipeline

**Status:** PASS

**Comando:**
```bash
python main.py \
  --project checklist_idl_inline \
  --input 'system inline { ... } entities { ... }' \
  --input-mode idl \
  --skip-build
```

**Evidências:**
- Pipeline executou com sucesso
- `final_status`: `artifacts_only`
- Comportamento idêntico ao teste com arquivo
- Artefatos gerados corretamente

---

### 3️⃣ Teste de Erro Classificado — IDL inválido

**Status:** PASS

**Comando:**
```bash
python main.py \
  --project checklist_idl_invalid \
  --input "isso nao eh idl" \
  --input-mode idl \
  --skip-build
```

**Evidências:**
- `final_status`: `idl_parse_failed`
- `error_codes`: `['IDL_PARSE_FAILED']` (presente e correto)
- Mensagem de erro clara:
  ```
  SCHEMA: IDL parse failed at line 1, col 1: Line 1, Column 1: Expected section keyword, got IDENTIFIER
  ```
- Sem stacktrace confuso
- `blocked_reason` no runlog: `None` (telemetry mostra `CONTRACT_GATE_FAILED`)

---

### 4️⃣ Regressão — Linguagem natural continua funcionando

**Status:** PASS

**Comando:**
```bash
python main.py \
  --project checklist_natural \
  --input "Sistema de cadastro de clientes com nome e email" \
  --input-mode natural \
  --skip-build
```

**Evidências:**
- Pipeline executou normalmente
- `SRS Version`: `v1` (diferente de IDL que é `vNone`)
- Artefatos gerados: SRS, IR, OAS, RBAC, PLAN
- Nenhum erro novo
- Fluxo natural não foi afetado

---

### 5️⃣ AUTO detect — IDL detectado corretamente

**Status:** PASS

**Comando:**
```bash
python main.py \
  --project checklist_auto \
  --input /tmp/sample.idl \
  --input-mode auto \
  --skip-build
```

**Evidências:**
- Auto detectou IDL corretamente
- `SRS Version`: `vNone` (indica que usou fluxo IDL)
- Comportamento igual ao `--input-mode idl` explícito
- Artefatos gerados corretamente

---

### 6️⃣ Inspeção do RunLog (ponto crítico)

**Status:** PASS

**Campos Obrigatórios:**
| Campo | Valor | Status |
|-------|-------|--------|
| `schema_version` | `runlog.v1` | OK |
| `final_status` | `success` | OK |
| `blocked_reason` | `None` | OK |
| `error_codes` | `[]` | OK (presente e vazio) |
| `duration_ms` | `0` | OK (presente) |

**Campos Específicos do Modo IDL:**
| Campo | Valor | Status |
|-------|-------|--------|
| `srs_version` | `None` | OK (IDL pula SRS) |
| `srs_path` | `None` | OK |
| `ir_version` | `1` | OK |

**Flags:**
```json
{
  "srs_ok": true,
  "ir_ok": true,
  "policy_ok": true,
  "contracts_ok": true,
  "plan_ok": true,
  "build_ok": false,
  "release_ok": false
}
```

**Counts:**
```json
{
  "requirements_count": 2,
  "entities_count": 1,
  "operations_count": 5,
  "tasks_count": 8,
  "patch_count": 0
}
```

---

### 7️⃣ Inspeção de Semântica (qualidade do IR)

**Status:** PASS

**IR Gerado (`checklist_idl_file/IR/v1.json`):**

**Meta:**
- `project_name`: "Sistema Checklist_Idl_File"
- `source`: "idl" (indica origem)
- `srs_version`: `null` (correto)

**Entities:**
- Entity `store` mapeada corretamente
- Fields: `id`, `name`, `cnpj`, `is_active`
- Tipos mapeados: `uuid`, `string`, `boolean`
- Constraints preservadas: `required`, `unique`, `default`

**API Intent:**
- `resources`: `["store"]` (lista de strings)
- `operations`: 5 operações CRUD padrão
  - `POST /store`
  - `GET /store`
  - `GET /store/{id}`
  - `PUT /store/{id}`
  - `DELETE /store/{id}`

**Roles (de actors):**
- `admin` com permissions `["manage_stores", "view_reports"]`
- Descrição preservada

**NFR:**
- `{}` (vazio - IDL de teste não tinha NFRs)

**Verificação de Integridade:**
- Nada inventado além do que está no IDL
- CRUD derivado apenas das entidades declaradas
- Actors → Roles: mapeamento 1:1 correto

---

## Anomalias Encontradas

| # | Descrição | Severidade | Impacto |
|---|-----------|------------|---------|
| 1 | `duration_ms` no runlog é `0` | Baixa | Apenas cosmético |

**Detalhes:**
- O campo `duration_ms` no payload do runlog aparece como `0`, mas a duração real é calculada e exibida no output (ex: `Duration: 18.72ms`). Isso é uma inconsistência menor - o valor no resultado do run é diferente do valor persistido no runlog.

---

## Conclusão Objetiva

**Pipeline IDL E2E está canônico.**

O pipeline IDL → IR → OAS → artefatos funciona conforme especificado:

1. `--input-mode idl` é respeitado e não ignorado
2. IDL textual é parseado e convertido para IR diretamente (sem SRS)
3. Erros de parse são classificados com `IDL_PARSE_FAILED`
4. O modo natural não foi afetado (sem regressões)
5. O modo auto detecta IDL corretamente
6. RunLog contém todos os campos obrigatórios
7. IR gerado tem estrutura correta e semântica preservada

---

## Evidências de Comando

```bash
# Todos os comandos executados em /home/bazari/engine
# Data: 2026-01-10

# Checklist 1
python main.py --project checklist_idl_file --input /tmp/sample.idl --input-mode idl --skip-build

# Checklist 2
python main.py --project checklist_idl_inline --input 'system inline {...}' --input-mode idl --skip-build

# Checklist 3
python main.py --project checklist_idl_invalid --input "isso nao eh idl" --input-mode idl --skip-build

# Checklist 4
python main.py --project checklist_natural --input "Sistema de cadastro..." --input-mode natural --skip-build

# Checklist 5
python main.py --project checklist_auto --input /tmp/sample.idl --input-mode auto --skip-build
```

---

**Fim do Relatório**
