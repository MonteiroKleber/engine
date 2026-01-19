# Prova Offline - Guia do Auditor

**Data:** 2026-01-18
**Versao:** 1.1
**Etapa:** 07 — EGE, Rollback/SAFE_MODE e Prova Offline

---

## 1. Visao Geral

Este documento descreve como um auditor pode verificar a integridade e conformidade do sistema Libervia Engine **sem executar o runtime** e **sem acesso a banco de dados mutavel**.

A prova offline e baseada em quatro artefatos imutaveis:

| Artefato | Formato | Localizacao | Proposito |
|----------|---------|-------------|-----------|
| `bundle.manifest.json` | JSON | `bundles/<bundle>/` | Integridade dos contratos |
| `contract_ledger.json` | JSON | `bundles/<bundle>/` | Rastreabilidade da compilacao |
| `audit_ledger.jsonl` | JSONL append-only | `var/audit_ledger.jsonl` ou per-institution | Historico de decisoes |
| `trace.json` | JSON | `dev-runs/<run_id>/` (builds) ou `deploy-traces/<release_id>/` (deploys), em `var/institutions/<institution_id>/` quando multi-tenant | Rastreabilidade de operacoes |

---

## 2. Pre-requisitos

O auditor precisa de:
1. Acesso ao sistema de arquivos onde os artefatos estao armazenados
2. Ferramenta para computar SHA256 (`sha256sum` no Linux/Mac, ou qualquer hasher)
3. Parser JSON/JSONL (ex: `jq`, Python)
4. Nenhum acesso ao runtime ou banco de dados

---

## 3. Verificacao de Integridade do Bundle

### 3.1 Verificar Hashes dos Contratos

**Objetivo:** Confirmar que todos os contratos no bundle correspondem aos hashes declarados no manifest.

**Passos:**

```bash
cd bundles/finance-pilot

# 1. Para cada contrato listado no manifest, verificar o hash
for file in $(jq -r '.contracts[].file' bundle.manifest.json); do
    expected=$(jq -r ".contracts[] | select(.file==\"$file\") | .sha256" bundle.manifest.json)
    actual="SHA256:$(sha256sum "$file" | cut -d' ' -f1)"

    if [ "$expected" = "$actual" ]; then
        echo "✅ $file: OK"
    else
        echo "❌ $file: MISMATCH"
        echo "   Expected: $expected"
        echo "   Actual:   $actual"
    fi
done
```

**Resultado esperado:** Todos os arquivos devem ter status "OK".

### 3.2 Verificar Contratos Obrigatorios

**Objetivo:** Confirmar que contratos institucionais obrigatorios estao presentes e marcados como `required: true`.

**Contratos obrigatorios:**
- `policies.json` - Regras de politica
- `mandates.json` - Mandatos permitidos
- `autonomy.json` - Niveis de autonomia

```bash
# Verificar que contratos obrigatorios existem e sao required
for required_file in policies.json mandates.json autonomy.json; do
    is_required=$(jq -r ".contracts[] | select(.file==\"$required_file\") | .required" bundle.manifest.json)

    if [ "$is_required" = "true" ] && [ -f "$required_file" ]; then
        echo "✅ $required_file: presente e required=true"
    else
        echo "❌ $required_file: PROBLEMA (required=$is_required, exists=$(test -f $required_file && echo yes || echo no))"
    fi
done
```

---

## 4. Verificacao do Contract Ledger

### 4.1 Schema Esperado

O `contract_ledger.json` deve conter:

| Campo | Tipo | Descricao | Obrigatorio |
|-------|------|-----------|-------------|
| `ledger_version` | string | Versao do schema | Sim |
| `ledger_id` | string | ID unico do ledger | Sim |
| `bundle_name` | string | Nome do bundle | Sim |
| `bundle_version` | string | Versao do bundle | Sim |
| `manifest_hash` | string | SHA256 do manifest | Sim |
| `idl_hash` | string | SHA256 do IDL fonte | Sim |
| `created_at` | ISO 8601 | Timestamp de criacao | Sim |
| `contracts` | array | Lista de contratos com hashes | Sim |
| `audit_trail` | array | Eventos de auditoria | Sim |

### 4.2 Verificar Contract Ledger

```bash
# 1. Verificar que contract_ledger.json existe
if [ ! -f contract_ledger.json ]; then
    echo "❌ contract_ledger.json ausente"
    exit 1
fi

# 2. Verificar campos obrigatorios
for field in ledger_version ledger_id bundle_name manifest_hash idl_hash created_at contracts; do
    value=$(jq -r ".$field // empty" contract_ledger.json)
    if [ -z "$value" ]; then
        echo "❌ Campo ausente: $field"
    else
        echo "✅ $field: presente"
    fi
done

# 3. Verificar que nao e placeholder vazio
contract_count=$(jq '.contracts | length' contract_ledger.json)
if [ "$contract_count" -eq 0 ]; then
    echo "⚠️ AVISO: contract_ledger.json tem entries vazias (placeholder)"
else
    echo "✅ contracts: $contract_count entradas"
fi
```

### 4.3 Cruzar com Manifest

```bash
# Verificar que manifest_hash no contract_ledger corresponde ao hash do manifest atual
ledger_manifest_hash=$(jq -r '.manifest_hash' contract_ledger.json)
actual_manifest_hash="SHA256:$(sha256sum bundle.manifest.json | cut -d' ' -f1)"

if [ "$ledger_manifest_hash" = "$actual_manifest_hash" ]; then
    echo "✅ manifest_hash corresponde ao manifest atual"
else
    echo "❌ manifest_hash NAO corresponde"
    echo "   No ledger:  $ledger_manifest_hash"
    echo "   No arquivo: $actual_manifest_hash"
fi
```

---

## 5. Verificacao do Audit Ledger

### 5.1 Formato JSONL

O `audit_ledger.jsonl` e um arquivo append-only onde cada linha e um evento JSON:

```json
{
  "event_type": "EXPENSE_CREATED",
  "tenant_id": "00000000-0000-0000-0000-000000000000",
  "actor_id": "user-123",
  "actor_roles": ["analyst"],
  "case_id": "expense-456",
  "step": "expense.create",
  "timestamp": "2026-01-18T10:30:00Z",
  "payload": {...},
  "bundle_manifest_sha256": "SHA256:...",
  "contract_ledger_sha256": "SHA256:..."
}
```

### 5.2 Eventos de Governanca

| Evento | Significado |
|--------|-------------|
| `SAFE_MODE_ENTERED` | Runtime entrou em modo seguro |
| `EGE_DRIFT_CHECKED` | Drift foi verificado |
| `EGE_DRIFT_BLOCKED` | Operacao bloqueada por drift |
| `EGE_DRIFT_PROPOSAL_CREATED` | Proposta de resolucao criada |
| `EGE_DRIFT_PROPOSAL_DECIDED` | Proposta aceita/bloqueada |
| `EGE_PIN_PROPOSAL_CREATED` | Proposta de pin criada |
| `EGE_PIN_PROPOSAL_ACCEPTED` | Pin aceito (config atualizada) |
| `EGE_PIN_PROPOSAL_BLOCKED` | Pin bloqueado |
| `ADMIN_KEY_DENIED` | Tentativa de auth admin rejeitada |

### 5.3 Reconstruir Decisoes

```bash
# Exemplo: listar todas as decisoes de expense
grep '"event_type":"EXPENSE_' audit_ledger.jsonl | jq -c '{
  time: .timestamp,
  actor: .actor_id,
  case: .case_id,
  decision: .event_type
}'

# Exemplo: verificar eventos de SAFE_MODE
grep 'SAFE_MODE' audit_ledger.jsonl | jq .

# Exemplo: verificar eventos de drift
grep 'EGE_DRIFT' audit_ledger.jsonl | jq .
```

### 5.4 Verificar Integridade do Ledger

```bash
# Verificar que bundle hashes sao consistentes nos eventos
cat audit_ledger.jsonl | jq -s 'group_by(.bundle_manifest_sha256) | map({hash: .[0].bundle_manifest_sha256, count: length})'
```

---

## 6. Verificacao do Trace

### 6.1 Trace para Builds (Sandbox)

Para cada build sandbox, um `trace.json` e gerado em:
```
bundles/dev-runs/<run_id>/trace.json
```

**Campos do Trace de Build:**

| Campo | Descricao |
|-------|-----------|
| `run_id` | UUID do build |
| `bundle_name` | Nome do bundle |
| `mode` | single ou multi (departamentos) |
| `sir_sha256` | Hash do SIR (Structured Intent Representation) |
| `draft_sha256` | Hash do IDL draft |
| `final_idl_sha256` | Hash do IDL final |
| `bundle_manifest_sha256` | Hash do manifest gerado |
| `contract_ledger_sha256` | Hash do contract_ledger gerado |
| `policy_count` | Numero de politicas |
| `policy_gap_count` | Numero de gaps de politica |
| `has_policy_gaps` | Boolean indicando gaps |

### 6.2 Trace para Deploys (Producao)

Para cada deploy de producao, um `trace.json` e gerado em:
```
deploy-traces/<release_id>/trace.json
```

**Campos do Trace de Deploy:**

| Campo | Descricao |
|-------|-----------|
| `trace_version` | Versao do schema do trace |
| `operation` | "deploy" |
| `release_id` | UUID do release |
| `bundle_name` | Nome do bundle deployado |
| `bundle_hash` | Hash do bundle deployado |
| `sir_sha256` | Hash do SIR |
| `draft_sha256` | Hash do draft IDL |
| `final_idl_sha256` | Hash do IDL final |
| `deployed_at` | Timestamp UTC ISO8601 |
| `institution_id` | UUID da instituicao (se multi-tenant) |

### 6.3 Verificar Trace de Build

```bash
# Listar todos os runs
ls bundles/dev-runs/

# Para um run especifico
run_id="<uuid>"
cat "bundles/dev-runs/$run_id/trace.json" | jq .

# Verificar que hashes correspondem aos arquivos gerados
trace_manifest_hash=$(jq -r '.bundle_manifest_sha256' "bundles/dev-runs/$run_id/trace.json")
actual_manifest_hash=$(sha256sum "bundles/dev-runs/$run_id/bundle.manifest.json" | cut -d' ' -f1)
# Comparar...
```

### 6.4 Verificar Trace de Deploy

```bash
# Listar todos os deploys
ls deploy-traces/

# Para um deploy especifico
release_id="<uuid>"
cat "deploy-traces/$release_id/trace.json" | jq .

# Verificar campos obrigatorios
jq '{
  release: .release_id,
  bundle: .bundle_name,
  deployed_at: .deployed_at,
  sir_hash: .sir_sha256,
  idl_hash: .final_idl_sha256
}' "deploy-traces/$release_id/trace.json"
```

---

## 7. Fluxo Completo de Auditoria

### 7.1 Checklist de Verificacao

```
□ 1. Bundle Manifest
  □ 1.1 Todos os hashes de contratos batem
  □ 1.2 Contratos obrigatorios presentes e required=true

□ 2. Contract Ledger
  □ 2.1 Nao e placeholder (tem entries)
  □ 2.2 manifest_hash corresponde ao manifest
  □ 2.3 idl_hash presente

□ 3. Audit Ledger
  □ 3.1 Eventos sao append-only (timestamps crescentes)
  □ 3.2 bundle_hashes consistentes nos eventos
  □ 3.3 Nenhum SAFE_MODE sem resolucao explicita

□ 4. Trace (Builds)
  □ 4.1 Hashes do trace correspondem aos artefatos
  □ 4.2 policy_gap_count = 0 ou gaps documentados

□ 5. Trace (Deploys)
  □ 5.1 Cada deploy tem trace.json
  □ 5.2 sir_sha256 e final_idl_sha256 presentes
  □ 5.3 deployed_at com timestamp valido
```

### 7.2 Perguntas que a Prova Offline Responde

1. **O que foi decidido?**
   - Eventos no `audit_ledger.jsonl` com `event_type` e `payload`

2. **Sob quais regras?**
   - Contratos no `bundle.manifest.json` com hashes verificaveis
   - `policies.json`, `mandates.json`, `autonomy.json`

3. **Com quais inputs/limites?**
   - Mandatos em `mandates.json` (limites, roles permitidas)
   - Autonomia em `autonomy.json` (niveis requeridos)
   - `payload` nos eventos do ledger

4. **Em qual versao institucional?**
   - `bundle_manifest_sha256` em cada evento
   - `version` no `bundle.manifest.json`
   - `bundle_version` no `contract_ledger.json`

5. **Quando foi deployado?**
   - `deployed_at` no `trace.json` de deploy
   - Eventos EGE_PIN_PROPOSAL_ACCEPTED no audit_ledger

---

## 8. Conclusao

A prova offline permite que um auditor verifique:
- **Integridade** via SHA256 de todos os contratos
- **Rastreabilidade** via eventos append-only no ledger
- **Governanca** via eventos EGE (drift, pin, SAFE_MODE)
- **Versao** via hashes de bundle em cada decisao
- **Deploys** via trace.json em `deploy-traces/`

Todos os artefatos necessarios para prova offline estao implementados.

---

**Status:** MVP COMPLETO ✅
**Data:** 2026-01-18
**Versao:** 1.1 (Trace de deploy implementado)
