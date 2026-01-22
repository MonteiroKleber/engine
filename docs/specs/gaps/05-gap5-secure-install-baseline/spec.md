# GAP 5 — Instalação de produção v0 (baseline operacional + defaults seguros)

## A) Resumo de correção (rastreabilidade)

- **Intenção original (spec anterior):** introduzir “modo de instalação” (dev vs prod) e endurecer preflight/envs.
- **Intenção corrigida (produção no cliente):** transformar isso em um baseline operacional que o cliente consiga executar hoje: envs obrigatórias, preflight determinístico, defaults seguros na criação de instituição, e “critérios objetivos de instalação aceitável”.
- **Impacto:** reduz risco de “instalação que funciona mas é insegura” (spoof, rotas legado abertas, stub ligado).

### O que foi mantido
- Não assumir cluster/HA.
- Manter systemd/scripts/runbook como caminho mínimo.

### O que foi alterado
- Não basta documentação: produção precisa de enforcement no preflight e de defaults seguros na criação de instituições.

### O que foi descartado por viés de “piloto”
- “prod = só documentação”. Em instalação real, isso vira incidente.

## B) Spec técnica corrigida (contrato)

### Objetivo
Garantir que uma instalação single-instance em produção no cliente tenha baseline seguro:

- preflight falha determinísticamente quando requisitos mínimos não são atendidos
- instituição criada já nasce com defaults seguros (sem depender de “lembrar de configurar”)
- runbook/checklist são verificáveis

### Estado atual (com arquivos/linhas reais)
- Preflight já valida:
  - isolamento de paths em multi-tenant
  - `ENGINE_CONSOLE_SESSION_SECRET`
  - `src/engine/core/preflight.py:85-158`
- Defaults de flags por instituição hoje são permissivos:
  - `require_institution_header_for_runtime=False`, `allow_legacy_routes=True`, `enable_contracts_stub=True`
  - `src/engine/core/institution_config.py:50-57`
- Runbook e scripts existem:
  - `ops/env/engine.env.example`
  - `ops/checks/preflight.sh`, `ops/checks/smoke_test.sh`
  - `ops/scripts/backup_engine.sh`, `ops/scripts/restore_engine.sh`

### Mudanças necessárias (mínimas)
1) **ENGINE_INSTALL_MODE**
   - Introduzir `ENGINE_INSTALL_MODE` com valores:
     - `dev` (default)
     - `prod`
   - Este flag não muda arquitetura; só muda defaults e enforcement.

2) **Preflight (prod)**
   - Em `ENGINE_INSTALL_MODE=prod`, preflight deve falhar se:
     - `ENGINE_ISE_ADMIN_TOKEN` ausente
     - `ENGINE_AUTH_MODE` não for `strict` (depende do GAP 2)
   - Em `prod`, registrar no log (e opcionalmente no ledger) o baseline ativo.

3) **Defaults seguros na criação de instituição**
   - Ao criar instituição (admin endpoint existente), em `prod`:
     - criar `config/ACTIVE.json` com defaults seguros:
       - `flags.require_institution_header_for_runtime=true`
       - `flags.allow_legacy_routes=false` (a menos que explicitamente habilitado depois)
       - `flags.enable_contracts_stub=false`
     - `defaults.default_dept` e `defaults.default_bundle_name` permanecem, mas a execução deve exigir header institucional.

4) **Runbook/checklist**
   - Garantir que `ops/env/engine.env.example` reflita:
     - `ENGINE_INSTALL_MODE=prod`
     - `ENGINE_AUTH_MODE=strict`
     - secrets necessários
   - Smoke test deve validar:
     - `/health`
     - `/console/login`

### Restrições explícitas (o que NÃO mudar)
- Não introduzir Kubernetes/HA/cluster.
- Não mudar arquitetura de storage (continua data root + JSON/JSONL).
- Não criar “setup wizard” novo fora do console já existente.

### Eventos de ledger afetados
- Opcional (preferível): evento `INSTALL_BASELINE_ACTIVE` no ledger global/institucional (se aplicável).
- Eventos existentes de config/admin continuam.

### Riscos técnicos
- Defaults seguros podem impactar devs se `ENGINE_INSTALL_MODE` for setado incorretamente; por isso o default deve ser `dev`.

### Impacto esperado
- O cliente consegue instalar e operar sem “passar pano” em segurança.

## C) Critérios de aceite (produção)

- `ENGINE_INSTALL_MODE=prod`:
  - preflight falha se `ENGINE_ISE_ADMIN_TOKEN` ausente
  - preflight falha se `ENGINE_AUTH_MODE` != `strict`
- Criar uma instituição em `prod` gera config com defaults seguros (flags) e isso é verificável no arquivo `institutions/<id>/config/ACTIVE.json`.
- `ops/env/engine.env.example` contém baseline prod (com envs obrigatórias).
- Smoke test cobre `/health` e `/console/login`.

## D) Prompt para Claude Code (ver `prompts.md`)
