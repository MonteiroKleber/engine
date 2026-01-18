# Release Checklist — Libervia Engine Pilot

## PT-BR

### Pré-Deploy

#### Código
- [ ] Todos os testes passando (`pytest tests/ -v`)
- [ ] Versão atualizada em `pyproject.toml`
- [ ] Versão atualizada em `src/engine/__init__.py`
- [ ] Versão atualizada em `src/engine/api/server.py`
- [ ] Changelog atualizado (se aplicável)

#### Bundle
- [ ] `bundle.manifest.json` presente e válido
- [ ] Todos os contratos obrigatórios presentes
- [ ] Hashes SHA-256 corretos no manifest
- [ ] `rbac.json` com roles e permissions corretas
- [ ] `approvals.json` com regras de aprovação
- [ ] `sod.json` com regras de segregação
- [ ] `invariants.json` com schemas de validação

#### Ambiente
- [ ] `ENGINE_BUNDLE_PATH` configurado
- [ ] `ENGINE_LEDGER_PATH` configurado
- [ ] `ENGINE_STATE_PATH` configurado
- [ ] `ENGINE_LOG_LEVEL` configurado (INFO ou DEBUG)
- [ ] `ENGINE_RATE_LIMIT_PER_MINUTE` configurado (default: 60)
- [ ] `ENGINE_MAX_BODY_BYTES` configurado (default: 262144)
- [ ] `ENGINE_CORS_ORIGINS` configurado (se necessário)

#### Infraestrutura
- [ ] Diretório do ledger existe e tem permissão de escrita
- [ ] Diretório do state store existe e tem permissão de escrita
- [ ] systemd unit `engine.service` configurado
- [ ] Firewall permite porta 8000 (ou porta configurada)

### Deploy

```bash
# 1. Executar preflight
./ops/checks/preflight.sh

# 2. Parar serviço (se upgrade)
sudo systemctl stop engine

# 3. Backup do ledger (se upgrade)
cp var/audit_ledger.jsonl var/audit_ledger.jsonl.bak.$(date +%Y%m%d%H%M%S)

# 4. Atualizar código
git pull origin main
pip install -e .

# 5. Iniciar serviço
sudo systemctl start engine

# 6. Verificar health
curl -s http://localhost:8000/health | jq '.mode'
# Esperado: "ACTIVE"
```

### Pós-Deploy

- [ ] Health check retorna 200 ACTIVE
- [ ] Logs não mostram erros
- [ ] Primeiro request de teste funciona
- [ ] Ledger está gravando eventos
- [ ] Métricas básicas disponíveis

### Rollback

```bash
# 1. Parar serviço
sudo systemctl stop engine

# 2. Restaurar código anterior
git checkout <commit-anterior>
pip install -e .

# 3. Restaurar ledger (se necessário)
# CUIDADO: Apenas se o novo ledger estiver corrompido
cp var/audit_ledger.jsonl.bak.<timestamp> var/audit_ledger.jsonl

# 4. Reiniciar
sudo systemctl start engine

# 5. Verificar
curl -s http://localhost:8000/health | jq '.mode'
```

---

## EN

### Pre-Deploy

#### Code
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Version updated in `pyproject.toml`
- [ ] Version updated in `src/engine/__init__.py`
- [ ] Version updated in `src/engine/api/server.py`
- [ ] Changelog updated (if applicable)

#### Bundle
- [ ] `bundle.manifest.json` present and valid
- [ ] All required contracts present
- [ ] SHA-256 hashes correct in manifest
- [ ] `rbac.json` with correct roles and permissions
- [ ] `approvals.json` with approval rules
- [ ] `sod.json` with segregation rules
- [ ] `invariants.json` with validation schemas

#### Environment
- [ ] `ENGINE_BUNDLE_PATH` configured
- [ ] `ENGINE_LEDGER_PATH` configured
- [ ] `ENGINE_STATE_PATH` configured
- [ ] `ENGINE_LOG_LEVEL` configured (INFO or DEBUG)
- [ ] `ENGINE_RATE_LIMIT_PER_MINUTE` configured (default: 60)
- [ ] `ENGINE_MAX_BODY_BYTES` configured (default: 262144)
- [ ] `ENGINE_CORS_ORIGINS` configured (if needed)

#### Infrastructure
- [ ] Ledger directory exists and is writable
- [ ] State store directory exists and is writable
- [ ] systemd unit `engine.service` configured
- [ ] Firewall allows port 8000 (or configured port)

### Deploy

```bash
# 1. Run preflight
./ops/checks/preflight.sh

# 2. Stop service (if upgrade)
sudo systemctl stop engine

# 3. Backup ledger (if upgrade)
cp var/audit_ledger.jsonl var/audit_ledger.jsonl.bak.$(date +%Y%m%d%H%M%S)

# 4. Update code
git pull origin main
pip install -e .

# 5. Start service
sudo systemctl start engine

# 6. Verify health
curl -s http://localhost:8000/health | jq '.mode'
# Expected: "ACTIVE"
```

### Post-Deploy

- [ ] Health check returns 200 ACTIVE
- [ ] Logs show no errors
- [ ] First test request works
- [ ] Ledger is recording events
- [ ] Basic metrics available

### Rollback

```bash
# 1. Stop service
sudo systemctl stop engine

# 2. Restore previous code
git checkout <previous-commit>
pip install -e .

# 3. Restore ledger (if necessary)
# CAUTION: Only if new ledger is corrupted
cp var/audit_ledger.jsonl.bak.<timestamp> var/audit_ledger.jsonl

# 4. Restart
sudo systemctl start engine

# 5. Verify
curl -s http://localhost:8000/health | jq '.mode'
```
