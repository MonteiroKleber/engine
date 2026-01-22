# 04-7 Prod Packaging — Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato), mapeamento do runtime atual
**Atualizado:** 2026-01-20 (gaps HIGH resolvidos, demais aceitos)

---

## 1. Resumo de Status

| GAP | Prioridade | Status | Evidência |
|-----|------------|--------|-----------|
| GAP-1 | ALTA | ✅ RESOLVIDO | `ops/env/engine.env.example` |
| GAP-2 | MÉDIA | ✅ RESOLVIDO | `ops/checks/preflight.sh` |
| GAP-3 | ALTA | ✅ RESOLVIDO | `ops/scripts/backup_engine.sh`, `restore_engine.sh` |
| GAP-4 | BAIXA | ⚠️ ACEITO | Documentado no runbook seção 7.3 |
| GAP-5 | MÉDIA | ✅ RESOLVIDO | `ops/checks/smoke_test.sh` |
| GAP-6 | BAIXA | ⚠️ ACEITO | Docker fora do escopo desta etapa |

---

## 2. Gaps Resolvidos

### GAP-1: engine.env.example Desatualizado — ✅ RESOLVIDO

**Prioridade:** ALTA

**Solução implementada:**
Arquivo `ops/env/engine.env.example` completamente reescrito com:
- Variáveis OBRIGATÓRIAS documentadas (`ENGINE_CONSOLE_SESSION_SECRET`, `ENGINE_ISE_ADMIN_TOKEN`)
- Variáveis RECOMENDADAS para produção
- Variáveis de data paths
- Variáveis de segurança e rate limiting
- Comentários explicativos para cada seção

**Evidência:**
```
ops/env/engine.env.example
```

---

### GAP-2: Preflight Script Shell Desatualizado — ✅ RESOLVIDO

**Prioridade:** MÉDIA

**Solução implementada:**
Script `ops/checks/preflight.sh` atualizado e sincronizado com `src/engine/core/preflight.py`:
- ✅ Verifica `ENGINE_CONSOLE_SESSION_SECRET` (min 32 chars)
- ✅ Verifica `ENGINE_ISE_ADMIN_TOKEN`
- ✅ Verifica multi-tenant path isolation (absolute paths)
- ✅ Mantém verificações existentes (bundle, ledger, contracts)

**Evidência:**
```
ops/checks/preflight.sh (linhas 49-127)
```

---

### GAP-3: Scripts de Backup/Restore Ausentes — ✅ RESOLVIDO

**Prioridade:** ALTA (DoD requirement)

**Solução implementada:**

**backup_engine.sh:**
- Comprime `ENGINE_DATA_ROOT` em tarball timestamped
- Inclui institutions_registry.jsonl, institutions/*, config
- Gera manifesto com checksums SHA256
- Cria `.sha256` para verificação do tarball

**restore_engine.sh:**
- Verifica checksum do tarball
- Verifica que engine.service está parado
- Recusa restaurar se target não estiver vazio (sem merge)
- Extrai, valida manifesto, restaura dados
- Valida JSONL após restauração

**Evidência:**
```
ops/scripts/backup_engine.sh (~160 linhas)
ops/scripts/restore_engine.sh (~270 linhas)
```

**Comandos de uso:**
```bash
# Backup
sudo ./ops/scripts/backup_engine.sh /var/backups/engine

# Restore
sudo systemctl stop engine.service
sudo ./ops/scripts/restore_engine.sh /var/backups/engine/engine-backup-YYYYMMDD-HHMMSS.tar.gz
sudo systemctl start engine.service
```

---

### GAP-5: Smoke Test Não Cobre Console — ✅ RESOLVIDO

**Prioridade:** MÉDIA

**Solução implementada:**
Script `ops/checks/smoke_test.sh` atualizado com:
- Test 2: Console root accessible (`/console/` → 200 ou 302)
- Test 3: Login page accessible (`/console/login` → 200, contém `admin_token`)
- Novas flags: `--skip-workflow`, `--console-only`

**Evidência:**
```
ops/checks/smoke_test.sh (linhas 53-89)
```

**Uso:**
```bash
# Teste completo
./ops/checks/smoke_test.sh

# Apenas console (rápido)
./ops/checks/smoke_test.sh --console-only
```

---

## 3. Gaps Aceitos

### GAP-4: Documentação de Rollback EGE — ⚠️ ACEITO

**Prioridade:** BAIXA

**Justificativa:**
O runbook já documenta o rollback via EGE na seção 7.3:
```bash
curl -X POST http://127.0.0.1:8000/admin/ege/<institution_id>/rollback \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_release_id": "<YYYYMMDD-HHMMSS>"}'
```

Documentação mais detalhada pode ser adicionada quando EGE tiver mais uso em produção.

**Evidência:**
```
docs/specs/fase-4/04-7-prod-packaging/runbook.md (seção 7.3)
```

---

### GAP-6: Opção Docker Não Disponível — ⚠️ ACEITO

**Prioridade:** BAIXA

**Justificativa:**
A spec permite "docker compose mínimo OU systemd unit + exemplo". A decisão oficial foi implementar **Opção B (systemd + scripts)**, deixando Docker fora do escopo.

**Trade-offs considerados:**
| Aspecto | systemd | docker-compose |
|---------|---------|----------------|
| Complexidade | Menor | Maior |
| Isolamento | User-level | Container |
| Já existe | ✅ | ❌ |
| Esforço adicional | Zero | Alto |

Docker pode ser adicionado em etapa futura se houver demanda.

---

## 4. Definition of Done — Status Final

Baseado em `spec.md`:

- [x] **Checklist de produção** (envs obrigatórias, paths, permissões, isolamento)
  - ✅ `docs/specs/fase-4/04-7-prod-packaging/checklist.md`
  - ✅ `ops/env/engine.env.example` atualizado

- [x] **Artefato de execução** (docker compose mínimo OU systemd unit + exemplo)
  - ✅ `ops/systemd/engine.service`
  - ✅ `ops/scripts/install_engine_service.sh`

- [x] **Procedimento de backup/restore do data root**
  - ✅ `ops/scripts/backup_engine.sh`
  - ✅ `ops/scripts/restore_engine.sh`
  - ✅ Documentado em `runbook.md` seção 4

- [x] **Operador consegue subir serviço e acessar /console/ com login**
  - ✅ Scripts de deploy existem
  - ✅ Checklist documenta configuração necessária
  - ✅ Smoke test valida console

- [x] **Instruções claras de backup/restore e checklist de pré-produção**
  - ✅ `runbook.md` com comandos reais
  - ✅ `checklist.md` completo

---

## 5. Arquivos de Referência — Status Final

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `ops/systemd/engine.service` | Unit file systemd | ✅ OK |
| `ops/scripts/install_engine_service.sh` | Script de instalação | ✅ OK |
| `ops/scripts/deploy_engine_prod.sh` | Script de deploy | ✅ OK |
| `ops/scripts/rollback_engine_bundle.sh` | Script de rollback | ✅ OK |
| `ops/scripts/backup_engine.sh` | Script de backup | ✅ **NOVO** |
| `ops/scripts/restore_engine.sh` | Script de restore | ✅ **NOVO** |
| `ops/checks/verify_bundle.sh` | Verifica bundle | ✅ OK |
| `ops/checks/preflight.sh` | Preflight checks | ✅ **ATUALIZADO** |
| `ops/checks/smoke_test.sh` | Smoke test | ✅ **ATUALIZADO** |
| `ops/env/engine.env.example` | Env example | ✅ **ATUALIZADO** |
| `src/engine/core/preflight.py` | Preflight runtime | ✅ OK |

---

## 6. Conclusão

**Etapa 04-7 (Prod Packaging) está COMPLETA.**

Todos os gaps de prioridade ALTA foram resolvidos. Os gaps de prioridade BAIXA foram aceitos com justificativa documentada.

O operador agora tem:
1. **Checklist completo** para configuração de produção
2. **Scripts de backup/restore** padronizados com validação
3. **Preflight check shell** sincronizado com runtime Python
4. **Smoke test** que cobre health e console
5. **Runbook** com comandos reais e procedimentos de emergência
