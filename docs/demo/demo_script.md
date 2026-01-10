# Demo Script Determinístico

**Document Version:** 1.0
**Classification:** Pre-Sales Technical Reference
**Last Updated:** 2024-01-15

---

## 1. Objetivo da Demo

Esta demo prova que o Bazari Engine implementa governança verificável para geração e evolução de software. Ela demonstra, em sequência lógica, que:

1. Especificações são capturadas de forma estruturada
2. Releases são bloqueados sem aprovação explícita
3. Aprovações são registradas com identidade e razão
4. Mudanças são controladas por escopo declarado
5. Toda execução produz evidências auditáveis offline

**Para quem:** Executivos, arquitetos, compliance, auditoria.

**O que ela NÃO demonstra:**
- Performance em escala (não é benchmark)
- Interface gráfica (não há UI)
- IA criativa (IA é instrumental, não é o valor)
- Deploy em produção (sistema termina no release local)

---

## 2. Pré-requisitos da Demo

### 2.1 Ambiente

| Requisito | Verificação |
|-----------|-------------|
| Python 3.10+ | `python --version` |
| Docker + Docker Compose | `docker compose version` |
| Engine instalado | `cd /home/bazari/engine && python main.py --version` |
| Portas livres | 3000, 5432, 8080 |

### 2.2 Reset do Ambiente

**Executar antes de cada demo:**

```bash
# Limpar episódios anteriores
rm -rf .engine/episodes/*

# Limpar sessões do wizard
rm -rf .engine/wizard/sessions/*

# Limpar store de demos
rm -rf demo_store/demo_governanca

# Limpar projetos gerados
rm -rf /home/bazari/generated/demo_governanca

# Parar containers antigos
docker compose down -v 2>/dev/null || true
```

### 2.3 Fixtures da Demo

**IDL Draft de entrada** (`demo_input.json`):

```json
{
  "schema_version": "idl_draft.v1",
  "project_name": "demo_governanca",
  "domain": "finance",
  "entities": [
    {
      "name": "Conta",
      "fields": [
        {"name": "numero", "type": "string", "required": true},
        {"name": "saldo", "type": "decimal", "required": true},
        {"name": "titular", "type": "string", "required": true}
      ]
    }
  ],
  "usecases": [
    {
      "name": "AbrirConta",
      "actor": "Gerente",
      "entity": "Conta",
      "operation": "create"
    },
    {
      "name": "ConsultarSaldo",
      "actor": "Cliente",
      "entity": "Conta",
      "operation": "read"
    }
  ]
}
```

**Change Request** (`change_request.json`):

```json
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-demo-001",
  "previous_episode_id": "PLACEHOLDER",
  "requester": {
    "name": "Maria Silva",
    "role": "Product Owner"
  },
  "reason": "Adicionar campo de limite de crédito",
  "target": "backend",
  "summary": "Adicionar campo limiteCredito na entidade Conta",
  "risk_level": "low",
  "scope": {
    "entities_affected": ["Conta"],
    "usecases_affected": []
  },
  "acceptance_criteria": [
    "Conta possui campo limiteCredito",
    "API aceita limiteCredito em create/update"
  ]
}
```

### 2.4 Criar Fixtures

```bash
# Criar diretório de demo
mkdir -p /home/bazari/engine/demo_fixtures

# Criar IDL Draft
cat > /home/bazari/engine/demo_fixtures/demo_input.json << 'EOF'
{
  "schema_version": "idl_draft.v1",
  "project_name": "demo_governanca",
  "domain": "finance",
  "entities": [
    {
      "name": "Conta",
      "fields": [
        {"name": "numero", "type": "string", "required": true},
        {"name": "saldo", "type": "decimal", "required": true},
        {"name": "titular", "type": "string", "required": true}
      ]
    }
  ],
  "usecases": [
    {
      "name": "AbrirConta",
      "actor": "Gerente",
      "entity": "Conta",
      "operation": "create"
    },
    {
      "name": "ConsultarSaldo",
      "actor": "Cliente",
      "entity": "Conta",
      "operation": "read"
    }
  ]
}
EOF

# Criar Change Request template
cat > /home/bazari/engine/demo_fixtures/change_request_template.json << 'EOF'
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-demo-001",
  "previous_episode_id": "PLACEHOLDER",
  "requester": {
    "name": "Maria Silva",
    "role": "Product Owner"
  },
  "reason": "Adicionar campo de limite de crédito",
  "target": "backend",
  "summary": "Adicionar campo limiteCredito na entidade Conta",
  "risk_level": "low",
  "scope": {
    "entities_affected": ["Conta"],
    "usecases_affected": []
  },
  "acceptance_criteria": [
    "Conta possui campo limiteCredito",
    "API aceita limiteCredito em create/update"
  ]
}
EOF
```

---

## 3. Narrativa da Demo (Visão Executiva)

**Para o apresentador dizer ao público:**

> "Vamos demonstrar como este sistema implementa governança para geração de software.
>
> **Primeiro**, vamos criar uma especificação usando o Wizard. O sistema captura requisitos de forma estruturada.
>
> **Segundo**, vamos tentar fazer o release do sistema gerado. Vocês verão que o sistema bloqueia — não há aprovação registrada.
>
> **Terceiro**, vamos registrar uma aprovação formal com identidade e justificativa. Só então o release é permitido.
>
> **Quarto**, vamos fazer uma mudança. Vocês verão que a mudança passa por um gate que valida se ela está dentro do escopo declarado.
>
> **Por fim**, vamos gerar um pacote de auditoria. Tudo que fizemos está lá, verificável offline, com hashes.
>
> Em nenhum momento o sistema confiou em processo manual. Governança é artefato, não declaração."

---

## 4. Script Técnico Passo a Passo

### PASSO 1 — Entrada via IDL Draft

**Objetivo:** Mostrar que entrada é estruturada e validada.

**Comando:**

```bash
cd /home/bazari/engine

python main.py \
  --project demo_governanca \
  --input demo_fixtures/demo_input.json \
  --input-mode draft \
  --skip-build
```

**O que acontece:**
1. Engine lê o IDL Draft
2. GATE1 valida schema (`idl_draft.v1`)
3. Contratos são gerados (SRS, IR, OpenAPI, RBAC, Plan)
4. Hashes são computados para cada artefato

**Resultado esperado:**
```
Pipeline concluido com sucesso!

Artefatos gerados (sem build):
  - SRS: v1
  - IR: v1
  - OAS: v1
  - RBAC: v1
  - PLAN: v1
```

**O que apontar na tela:**
- "Vejam que cada artefato tem versão. Nada é implícito."
- "O input foi validado contra um schema. Entrada mal formada seria bloqueada."

**Verificar:**
```bash
# Ver contratos gerados
ls demo_store/demo_governanca/

# Ver hash do IDL no runlog
cat demo_store/demo_governanca/runlog.json | jq '.contract_ledger'
```

---

### PASSO 2 — Execução COM Build (Tentativa de Release)

**Objetivo:** Mostrar que build funciona, mas release é bloqueado sem approval.

**Comando:**

```bash
python main.py \
  --project demo_governanca \
  --input demo_fixtures/demo_input.json \
  --input-mode draft \
  --release
```

**O que acontece:**
1. Contratos são (re)gerados
2. Código é gerado (backend Java, frontend React)
3. Build é executado (Maven, npm)
4. Docker Compose tenta subir
5. **Approval Gate bloqueia** (não há approval)

**Resultado esperado:**
```
Release:
  - APPROVAL_REQUIRED

Pipeline bloqueado!
  blocked_reason: APPROVAL_REQUIRED
```

**O que apontar na tela:**
- "Build passou. Código foi gerado e compilou."
- "Mas o release foi bloqueado. Por quê? Não há aprovação."
- "Isso não é configuração. É design. Sem aprovação, nada sai."

**Verificar:**
```bash
# Ver blocked_reason no runlog
cat demo_store/demo_governanca/runlog.json | jq '.blocked_reason'
# Resultado: "APPROVAL_REQUIRED"

# Ver que episódio foi criado
ls .engine/episodes/

# Guardar o episode_id para próximos passos
EPISODE_ID=$(cat demo_store/demo_governanca/runlog.json | jq -r '.execution_id')
echo "Episode ID: $EPISODE_ID"
```

---

### PASSO 3 — Registrar Aprovação

**Objetivo:** Mostrar que aprovação é ação explícita com identidade.

**Comando:**

```bash
# Usar o episode_id do passo anterior
EPISODE_ID=$(cat demo_store/demo_governanca/runlog.json | jq -r '.execution_id')

python -m episodes.episodes_cli approve \
  --episode-id "$EPISODE_ID" \
  --decision approve \
  --reason "Código revisado, testes passaram, aprovado para produção" \
  --approver-name "João Santos" \
  --role "Tech Lead" \
  --org "Acme Corp"
```

**O que acontece:**
1. Approval record é criado com:
   - Identidade do aprovador
   - Decisão explícita
   - Justificativa
   - Timestamp
2. Approval é vinculado ao episódio específico

**Resultado esperado:**
```
SUCCESS: Approval added: appr-XXXXXXXX
Episode: exec-XXXXXXXX
Decision: approve
Gate Status: PASSED (approved)
```

**O que apontar na tela:**
- "Aprovação não é checkbox. É registro com identidade."
- "Se perguntarem 'quem aprovou?', a resposta está aqui."
- "O approval está vinculado a ESTE episódio, não a outro."

**Verificar:**
```bash
# Ver approval registrado
cat .engine/episodes/$EPISODE_ID/approvals/approval.json | jq '.'

# Ver campos de identidade
cat .engine/episodes/$EPISODE_ID/approvals/approval.json | jq '.approver'
```

---

### PASSO 4 — Release Após Aprovação

**Objetivo:** Mostrar que agora o release é permitido.

**Comando:**

```bash
# Re-executar com --release
python main.py \
  --project demo_governanca \
  --input demo_fixtures/demo_input.json \
  --input-mode draft \
  --release
```

**O que acontece:**
1. Pipeline executa novamente
2. Approval Gate verifica: aprovação existe e é válida
3. Docker Compose sobe os containers
4. Smoke tests executam
5. Release completa com sucesso

**Resultado esperado:**
```
Release:
  - Docker Compose: OK
  - Smoke Tests: OK (5/5)
  - RELEASE: SUCCESS

Pipeline concluido com sucesso!
```

**O que apontar na tela:**
- "Agora passou. A única diferença: existe aprovação."
- "Isso prova que o controle funciona."

**Verificar:**
```bash
# Ver final_status
cat demo_store/demo_governanca/runlog.json | jq '.final_status'
# Resultado: "success"

# Ver containers rodando
docker compose -f /home/bazari/generated/demo_governanca/docker-compose.yml ps
```

---

### PASSO 5 — Change Request (Mudança Governada)

**Objetivo:** Mostrar que mudanças passam por gate de escopo.

**Preparar CR:**

```bash
# Pegar episode_id atual
EPISODE_ID=$(cat demo_store/demo_governanca/runlog.json | jq -r '.execution_id')

# Criar CR com previous_episode_id correto
cat > demo_fixtures/change_request.json << EOF
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-demo-001",
  "previous_episode_id": "$EPISODE_ID",
  "requester": {
    "name": "Maria Silva",
    "role": "Product Owner"
  },
  "reason": "Adicionar campo de limite de crédito para compliance PLD",
  "target": "backend",
  "summary": "Adicionar campo limiteCredito na entidade Conta",
  "risk_level": "low",
  "scope": {
    "entities_affected": ["Conta"],
    "usecases_affected": []
  },
  "acceptance_criteria": [
    "Conta possui campo limiteCredito",
    "API aceita limiteCredito em create/update"
  ]
}
EOF
```

**Comando:**

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id "$EPISODE_ID" \
  --cr demo_fixtures/change_request.json \
  --dry-run
```

**O que acontece:**
1. CR é validado contra schema
2. `previous_episode_id` é verificado (deve existir)
3. Impact Gate avalia escopo
4. `--dry-run` mostra o que aconteceria sem criar episódio

**Resultado esperado:**
```
Dry run: validation passed
  Change Request ID: cr-demo-001
  Previous Episode ID: exec-XXXXXXXX
  CR Hash: sha256:XXXXXXXX
  Would Create Episode: change-XXXXXXXX
```

**O que apontar na tela:**
- "A mudança declara escopo: target=backend, entities_affected=[Conta]"
- "O Impact Gate vai verificar se as mudanças reais estão dentro desse escopo"
- "Se alguém tentar mudar frontend quando declarou backend, será bloqueado"

**Executar de verdade (sem --dry-run):**

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id "$EPISODE_ID" \
  --cr demo_fixtures/change_request.json
```

**Verificar:**
```bash
# Ver novo episódio criado
ls .engine/episodes/

# Ver link com episódio anterior
NEW_EPISODE=$(ls -t .engine/episodes/ | head -1)
cat .engine/episodes/$NEW_EPISODE/manifest.json | jq '.links'
```

---

### PASSO 6 — Demonstrar Bloqueio de Escopo (Opcional)

**Objetivo:** Mostrar que escopo é enforced, não declarativo.

**Criar CR que viola escopo:**

```bash
cat > demo_fixtures/change_request_violacao.json << EOF
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-violacao",
  "previous_episode_id": "$EPISODE_ID",
  "requester": {
    "name": "Atacante",
    "role": "Developer"
  },
  "reason": "Tentativa de mudança fora do escopo",
  "target": "frontend",
  "summary": "Declarando frontend mas tentando mudar backend",
  "risk_level": "low",
  "scope": {
    "entities_affected": []
  },
  "acceptance_criteria": []
}
EOF
```

**O que apontar:**
- "Este CR declara target=frontend"
- "Mas se as mudanças afetarem backend, o Impact Gate bloqueará"
- "O sistema não confia na declaração. Ele verifica."

---

### PASSO 7 — AuditPack (Auditoria Offline)

**Objetivo:** Mostrar que tudo é verificável offline.

**Comando:**

```bash
# Usar episódio aprovado
EPISODE_ID=$(cat demo_store/demo_governanca/runlog.json | jq -r '.execution_id')

python -m episodes.episodes_cli auditpack \
  --episode-id "$EPISODE_ID" \
  --out demo_audit_pack.zip \
  --include-artifacts
```

**O que acontece:**
1. Todos arquivos do episódio são coletados
2. Hashes SHA256 são computados
3. Root hash é derivado
4. ZIP é criado com estrutura verificável

**Resultado esperado:**
```
SUCCESS: AuditPack created: demo_audit_pack.zip
  Episode: exec-XXXXXXXX
  Root Hash: sha256:XXXXXXXX
  Total Files: XX
```

**Explorar o AuditPack:**

```bash
# Extrair
unzip -o demo_audit_pack.zip -d demo_audit_extracted

# Ver estrutura
tree demo_audit_extracted/auditpack/

# Ver index com hashes
cat demo_audit_extracted/auditpack/index.json | jq '.files[:3]'

# Ver root hash
cat demo_audit_extracted/auditpack/index.json | jq '.root_hash_sha256'

# Ver approval
cat demo_audit_extracted/auditpack/episode/approvals/approval.json | jq '.'

# Verificar integridade (como auditor faria)
cd demo_audit_extracted/auditpack
sha256sum -c hashes/sha256sums.txt
cd ../..
```

**O que apontar na tela:**
- "Tudo está aqui: runlog, approval, contratos, hashes"
- "Um auditor pode verificar isso sem acesso ao sistema"
- "O sha256sum prova que nada foi alterado"
- "Isto é evidência, não documentação"

---

### PASSO 8 — Verificação de Integridade

**Objetivo:** Mostrar que tampering é detectável.

**Comando:**

```bash
# Verificar integridade do episódio
python -c "
from episodes.episode_store import EpisodeStore
store = EpisodeStore()
valid, msg = store.verify_integrity('$EPISODE_ID')
print(f'Valid: {valid}')
print(f'Message: {msg}')
"
```

**Resultado esperado:**
```
Valid: True
Message: None
```

**Demonstrar detecção de tampering (opcional):**

```bash
# Modificar um arquivo (simular tampering)
echo "TAMPERED" >> .engine/episodes/$EPISODE_ID/runlog.json

# Verificar novamente
python -c "
from episodes.episode_store import EpisodeStore
store = EpisodeStore()
valid, msg = store.verify_integrity('$EPISODE_ID')
print(f'Valid: {valid}')
print(f'Message: {msg}')
"
```

**Resultado esperado:**
```
Valid: False
Message: Hash mismatch: expected sha256:XXX, got sha256:YYY
```

**O que apontar:**
- "Qualquer modificação é detectada"
- "Não confiamos em processo. Verificamos matematicamente."

**Reverter tampering (se demonstrou):**
```bash
# Regenerar runlog original via re-execução ou restaurar de backup
git checkout .engine/episodes/$EPISODE_ID/runlog.json 2>/dev/null || true
```

---

## 5. Resultados Esperados (Checklist)

| Passo | Resultado Esperado | Artefato Gerado | O que isso Prova |
|-------|-------------------|-----------------|------------------|
| 1. IDL Draft | Contratos gerados | `demo_store/demo_governanca/*.json` | Entrada é validada |
| 2. Tentativa Release | `APPROVAL_REQUIRED` | `runlog.json` com blocked_reason | Sem approval, sem release |
| 3. Aprovação | Approval registrado | `approval.json` | Identidade é capturada |
| 4. Release | `final_status: success` | Episode completo | Approval libera release |
| 5. Change Request | Episode linkado | `manifest.links` | Mudanças são rastreáveis |
| 6. Escopo violado | `IMPACT_OUT_OF_SCOPE` | `blocked_reason` | Escopo é enforced |
| 7. AuditPack | ZIP com hashes | `auditpack/index.json` | Auditoria é offline |
| 8. Integridade | Valid: True/False | Verificação matemática | Tampering é detectável |

---

## 6. Mensagens-Chave para o Público

**Para o apresentador usar durante a demo:**

| Momento | Mensagem |
|---------|----------|
| Bloqueio sem approval | "Aqui não existe deploy silencioso." |
| Registro de approval | "Toda decisão vira contrato." |
| CR com escopo | "Mudança não é exceção. É processo." |
| AuditPack | "Auditoria não é um evento, é um subproduto." |
| Verificação de hash | "Não confiamos. Verificamos." |
| Fim da demo | "O valor não é gerar código. O valor é gerar evidência." |

---

## 7. Erros Comuns e Como Responder

### P: "E se alguém criar approval falso direto no filesystem?"

**R:** "O approval.json está dentro do episódio. Se alguém modificar, o hash do episódio não bate. Tampering é detectável via verify_integrity(). Além disso, o arquivo de approval está no AuditPack que foi gerado antes da modificação."

---

### P: "E se o desenvolvedor aprovar o próprio código?"

**R:** "O sistema registra quem aprovou. Se a organização exige segregação, isso é verificável no approval.json. O sistema não impede, mas torna visível. Controle organizacional é responsabilidade da organização."

---

### P: "Isso não deixa o desenvolvimento mais lento?"

**R:** "Sim. Governança tem custo. A pergunta é: qual é o custo de não ter governança? Em ambientes regulados, a resposta é: sanções, multas, e perda de licença."

---

### P: "E se o sistema cair no meio da execução?"

**R:** "Cada fase emite telemetria. O runlog captura o estado. Se falhar, você sabe exatamente onde. Não há estado implícito."

---

### P: "Como sabemos que o código gerado é seguro?"

**R:** "Não sabemos. O sistema não garante ausência de bugs ou vulnerabilidades. Ele garante rastreabilidade. Você sabe exatamente qual input gerou qual output, e pode auditar."

---

### P: "Isso substitui code review?"

**R:** "Não. O sistema não revisa código. Ele registra que houve aprovação. Se a aprovação inclui code review é decisão organizacional."

---

### P: "E se precisarmos fazer rollback?"

**R:** "Cada episódio é imutável. O anterior continua existindo. Rollback é deploy do episódio anterior, não modificação de histórico."

---

### P: "Como integramos com nosso sistema de tickets?"

**R:** "O approval pode incluir referência externa no campo reason. Ex: 'Aprovado conforme JIRA-123'. O sistema não integra, mas preserva a referência."

---

## 8. Encerramento

### O que foi provado

1. **Governança é obrigatória** — Release sem approval é bloqueado
2. **Identidade é registrada** — Aprovador é identificado com nome, role, org
3. **Escopo é enforced** — Impact Gate valida mudanças contra declaração
4. **Rastreabilidade é completa** — Episodes linkam com previous_episode_id
5. **Auditoria é trivial** — AuditPack contém tudo, verificável offline
6. **Integridade é verificável** — Hashes detectam qualquer modificação

### O que NÃO foi mostrado (por escolha)

- Performance em escala (não é o valor)
- Customização de templates (existe, mas não é governança)
- Integração com CI/CD externo (possível, mas fora do escopo)
- UI gráfica (não existe)

### Próximo Passo Natural

**Não é venda. É piloto.**

> "Se o que vocês viram faz sentido para o problema de vocês, o próximo passo é um piloto controlado: um sistema novo, não-crítico, com uma equipe técnica receptiva. Em 4-8 semanas, vocês terão evidência concreta de que isso funciona no ambiente de vocês."

---

## Apêndice: Script de Reset Completo

```bash
#!/bin/bash
# reset_demo.sh
# Executar antes de cada demo

set -e

cd /home/bazari/engine

echo "=== Limpando ambiente da demo ==="

# Parar containers
docker compose -f /home/bazari/generated/demo_governanca/docker-compose.yml down -v 2>/dev/null || true

# Limpar episódios
rm -rf .engine/episodes/*
echo "Episódios limpos"

# Limpar sessões wizard
rm -rf .engine/wizard/sessions/*
echo "Sessões wizard limpas"

# Limpar store
rm -rf demo_store/demo_governanca
echo "Store limpo"

# Limpar projeto gerado
rm -rf /home/bazari/generated/demo_governanca
echo "Projeto gerado limpo"

# Limpar AuditPacks de demo
rm -f demo_audit_pack.zip
rm -rf demo_audit_extracted

echo "=== Ambiente pronto para demo ==="
```

---

## Apêndice: Verificação Pré-Demo

```bash
#!/bin/bash
# verify_demo_ready.sh
# Verificar que ambiente está pronto

echo "=== Verificando pré-requisitos ==="

# Python
python --version || { echo "ERRO: Python não encontrado"; exit 1; }

# Docker
docker compose version || { echo "ERRO: Docker Compose não encontrado"; exit 1; }

# Engine
python main.py --version || { echo "ERRO: Engine não funciona"; exit 1; }

# Portas
for port in 3000 5432 8080; do
  if lsof -i :$port > /dev/null 2>&1; then
    echo "AVISO: Porta $port em uso"
  fi
done

# Fixtures
if [ ! -f demo_fixtures/demo_input.json ]; then
  echo "AVISO: Fixtures não criadas. Execute a seção 2.4 primeiro."
fi

# Episódios limpos
if [ -d .engine/episodes ] && [ "$(ls -A .engine/episodes 2>/dev/null)" ]; then
  echo "AVISO: Existem episódios. Execute reset_demo.sh."
fi

echo "=== Verificação concluída ==="
```

---

*Este script é determinístico. Executado nas mesmas condições, produz os mesmos resultados. Qualquer desvio indica problema de ambiente, não de sistema.*
