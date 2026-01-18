# Baseline — Libervia Engine

**Data:** 2026-01-17
**Versão:** 8.1.1
**Fase:** Pin on Deploy (Governed)

---

## 1. Versão do Engine

| Arquivo | Versão |
|---------|--------|
| `pyproject.toml` | 8.1.1 |
| `src/engine/__init__.py` | 8.1.1 |
| `src/engine/api/server.py` | 8.1.1 |

**Descrição:** "Libervia Engine - Phase 8.1.1 Pin on Deploy (Governed)"

---

## 2. Dependências

### Runtime
```
fastapi>=0.109.0
uvicorn>=0.27.0
pyyaml>=6.0
```

### Dev
```
pytest>=8.0.0
httpx>=0.26.0
```

**Python:** >= 3.11

---

## 3. Como Rodar Testes

### Instalação (modo dev)
```bash
cd /home/bazari/engine
pip install -e ".[dev]"
```

### Executar todos os testes
```bash
pytest tests/ -v
```

### Resultado atual
```
1154 passed, 3 skipped in ~17s
```

### Testes pulados (investigar)
| Teste | Arquivo | Motivo |
|-------|---------|--------|
| `test_finalize_with_required_gaps_raises` | `test_nl_finalize.py` | Skip marker |
| `test_finalize_with_required_gaps_allowed` | `test_nl_finalize.py` | Skip marker |
| `test_finalize_endpoint_with_gaps_not_allowed` | `test_nl_finalize.py` | Skip marker |

---

## 4. Como Iniciar o Runtime

### Desenvolvimento (com reload)
```bash
cd /home/bazari/engine
PYTHONPATH=src uvicorn engine.api.server:app --reload --port 8000
```

### Produção (via systemd)
```bash
# 1. Executar preflight
./ops/checks/preflight.sh

# 2. Iniciar engine
uvicorn engine.api.server:app --host 0.0.0.0 --port 8000

# 3. Verificar health
curl http://localhost:8000/health
```

### Variáveis de ambiente principais
| Variável | Descrição | Default |
|----------|-----------|---------|
| `ENGINE_BUNDLE_PATH` | Diretório do bundle | `bundles/finance-pilot` |
| `ENGINE_LEDGER_PATH` | Arquivo do ledger | `var/audit_ledger.jsonl` |
| `ENGINE_STATE_PATH` | Arquivo de estado | `var/state_store.json` |
| `ENGINE_ISE_ADMIN_TOKEN` | Token admin para release/deploy | (obrigatório para deploy) |
| `ENGINE_LOG_LEVEL` | Nível de log | `INFO` |

---

## 5. Estrutura do Projeto

```
/home/bazari/engine/
├── src/engine/
│   ├── api/              # 13 módulos de API (FastAPI)
│   ├── core/             # 28 módulos de lógica core
│   ├── pipeline/         # 9 módulos do pipeline NL→IDL
│   ├── nl/               # Processamento de linguagem natural
│   ├── ise/              # Compilador IDL→Bundle
│   └── loader/           # Carregamento e verificação de bundles
├── tests/                # 97 arquivos de teste (1157 testes coletados)
├── bundles/              # Bundles pré-compilados
│   └── finance-pilot/    # Bundle do MVP financeiro
├── docs/
│   ├── pilot/            # Documentação do pilot
│   └── specs/            # Especificações por fase
├── ops/
│   ├── checks/           # Scripts de verificação
│   │   ├── preflight.sh
│   │   ├── verify_bundle.sh
│   │   └── smoke_test.sh
│   ├── scripts/          # Scripts de deploy
│   │   ├── deploy_engine_prod.sh
│   │   ├── rollback_engine_bundle.sh
│   │   └── install_engine_service.sh
│   └── systemd/          # Configuração systemd
├── var/                  # Dados de runtime (ledger, state)
└── pyproject.toml        # Configuração do projeto
```

---

## 6. Documentação Existente

| Documento | Localização | Status |
|-----------|-------------|--------|
| Definition of Done | `docs/pilot/DEFINITION_OF_DONE.md` | Existe |
| Runbook | `docs/pilot/RUNBOOK.md` | Existe |
| Examples | `docs/pilot/EXAMPLES.md` | Existe |
| Release Checklist | `docs/pilot/RELEASE_CHECKLIST.md` | Existe |
| README | `README.md` | Existe |

---

## 7. Scripts Operacionais

| Script | Localização | Status |
|--------|-------------|--------|
| Preflight | `ops/checks/preflight.sh` | Existe (236 linhas) |
| Verify Bundle | `ops/checks/verify_bundle.sh` | Existe |
| Smoke Test | `ops/checks/smoke_test.sh` | Existe |
| Deploy Prod | `ops/scripts/deploy_engine_prod.sh` | Existe |
| Rollback | `ops/scripts/rollback_engine_bundle.sh` | Existe |
| Install Service | `ops/scripts/install_engine_service.sh` | Existe |

---

## 8. Bundle Finance-Pilot

**Localização:** `bundles/finance-pilot/`

**Contratos esperados:**
- `bundle.manifest.json`
- `contract_ledger.json`
- `rbac.json`
- `workflows.json`
- `approvals.json`
- `sod.json`
- `invariants.json`
- `openapi.yaml`

---

## 9. Endpoints Principais (MVP)

### Core Business
- `POST /finance/expenses` — Criar despesa
- `GET /finance/expenses/{id}` — Consultar despesa
- `POST /approvals/{id}/decide` — Aprovar/rejeitar

### Health
- `GET /health` — Status do engine (ACTIVE ou SAFE_MODE)

### Admin
- `POST /admin/institutions` — Criar instituição
- `GET /admin/institutions/{id}/config` — Configuração
- `PUT /admin/institutions/{id}/config` — Atualizar config

### Pipeline
- `POST /pipeline/build` — Build sem deploy (sandbox)
- `POST /pipeline/deploy` — Deploy completo

### EGE (Governance)
- `POST /admin/ege/drift/check` — Verificar drift
- `POST /admin/ege/proposals` — Criar proposta
- `POST /admin/ege/proposals/{id}/decide` — Decidir proposta

---

## 10. Próximos Passos

Ver `gap-report.md` para análise detalhada do estado atual vs Definition of Done.
