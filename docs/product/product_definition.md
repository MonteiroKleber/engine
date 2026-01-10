# Product Definition

**Document Version:** 1.0
**Classification:** Commercial Technical Reference
**Last Updated:** 2024-01-15

---

## 1. Definição Canônica do Produto

### O que este produto faz

**Bazari Engine** é um sistema de governança para geração e evolução de software que produz artefatos rastreáveis, verificáveis e auditáveis em cada etapa do ciclo de vida.

### Qual problema enterprise ele resolve

Em ambientes regulados, mudanças em sistemas críticos requerem:
- Aprovação formal antes de release
- Rastreabilidade completa de input para output
- Evidência auditável de cada decisão
- Verificação de integridade sem confiar em processos manuais

Sistemas tradicionais dependem de documentação manual, confiança em processos, e auditorias retrospectivas baseadas em logs dispersos. Isto gera:
- Risco de compliance por falta de evidência
- Custo de auditoria proporcional à complexidade do sistema
- Impossibilidade de verificar integridade de mudanças passadas

Este produto elimina esses problemas gerando, por design, todos os artefatos necessários para auditoria em cada execução.

### Em que momento do ciclo de vida de sistemas ele atua

| Fase | Atuação |
|------|---------|
| Especificação | Captura de requisitos via Wizard, geração de IDL |
| Geração | Transformação de IDL em contratos e código |
| Validação | Gates de integridade, schema, segurança |
| Aprovação | Gate obrigatório antes de release |
| Mudança | Change Requests com escopo controlado |
| Auditoria | AuditPack para verificação offline |

---

## 2. O que o Produto NÃO É

### Não é um gerador automático de código

O sistema não gera código arbitrário a partir de descrições vagas. Toda geração passa por contratos intermediários (IDL, SRS, IR) que são validados por gates antes de qualquer código ser produzido. O código é consequência de contratos verificados, não de prompts.

### Não é uma IA autônoma

Modelos de linguagem são usados apenas para transformação de especificações em contratos estruturados. Após os gates de contrato, nenhuma decisão é tomada por IA. O pipeline de patch, build e release é puramente determinístico.

### Não é uma plataforma low-code/no-code

O sistema produz código completo (Java/Spring, React/TypeScript, SQL). Não há interface drag-and-drop, não há abstração que esconda a implementação. O código gerado é convencional e pode ser auditado, modificado e mantido por desenvolvedores.

### Não é uma ferramenta de DevOps

O sistema não gerencia infraestrutura, não faz deploy em produção, não monitora aplicações em runtime. Ele termina no momento do release local (Docker Compose up + smoke tests). A operação em produção é responsabilidade da organização.

### Não substitui arquitetos, analistas ou compliance

O sistema requer input humano estruturado (especificações, aprovações, change requests). Ele não toma decisões de negócio, não define requisitos, não aprova releases. Humanos continuam responsáveis por todas decisões; o sistema apenas garante que essas decisões sejam rastreáveis.

### Não é uma ferramenta de migração de legacy

O sistema pode receber contexto de sistemas legados (via Legacy Bundle), mas não migra dados, não refatora código existente, não integra automaticamente com sistemas em produção.

---

## 3. Público-Alvo Técnico

### 3.1 Quem Decide (C-level, Conselho, Risco, Compliance)

**Perfil:** Executivos responsáveis por risco operacional e conformidade regulatória.

**Dor principal:**
- Incapacidade de provar, retroativamente, que mudanças em sistemas críticos seguiram processo
- Custo crescente de auditoria proporcional à idade e complexidade dos sistemas
- Risco de sanções regulatórias por falta de evidência de controle

**O que este produto resolve:**
- Cada execução gera evidência estruturada (RunLog, Episode, Approval)
- Auditoria retroativa é trivial: basta verificar hashes
- Compliance é verificável por artefatos, não por declarações

**O que ele NÃO promete:**
- Não elimina necessidade de processo organizacional
- Não substitui governança humana
- Não garante que aprovações são corretas, apenas que foram registradas

---

### 3.2 Quem Avalia (Arquitetos, Segurança, Auditoria)

**Perfil:** Profissionais técnicos responsáveis por validar adoção de ferramentas.

**Dor principal:**
- Ferramentas de geração de código são caixas-pretas
- Impossível auditar o que foi gerado sem confiar no fornecedor
- Mudanças em sistemas não têm rastreabilidade técnica verificável

**O que este produto resolve:**
- Todo artefato tem hash SHA256 verificável
- Código gerado é inspecionável (Java, TypeScript, SQL padrão)
- Pipeline é determinístico: mesmo input = mesmo output
- AuditPack permite verificação offline sem acesso ao sistema

**O que ele NÃO promete:**
- Não garante que código gerado é livre de bugs
- Não substitui code review humano
- Não verifica segurança do código em runtime

---

### 3.3 Quem Opera (Times Técnicos)

**Perfil:** Desenvolvedores e engenheiros que executam o sistema no dia a dia.

**Dor principal:**
- Documentação de mudanças é manual e frequentemente desatualizada
- Processos de approval são externos ao código (tickets, emails)
- Rastrear "por que" uma mudança foi feita requer arqueologia

**O que este produto resolve:**
- Change Request é artefato do sistema, não documento externo
- Approval é registrado no episódio, não em sistema separado
- RunLog captura exatamente o que aconteceu em cada execução
- Erros têm códigos determinísticos, não mensagens ambíguas

**O que ele NÃO promete:**
- Não acelera desenvolvimento (governança tem custo)
- Não elimina necessidade de entender o código gerado
- Não automatiza decisões de design

---

## 4. Proposta de Valor Técnica

### 4.1 Governança por Artefatos

**Valor:** Toda decisão de governança produz artefato verificável.

| Decisão | Artefato | Verificação |
|---------|----------|-------------|
| Especificação aprovada | IDL + hash | `contract_ledger.idl.content_hash_sha256` |
| Mudança autorizada | Change Request + hash | `manifest.links.cr_hash_sha256` |
| Release aprovado | Approval record | `approval.json` com `episode_id` |
| Escopo respeitado | Impact Gate result | `blocked_reason` no RunLog |

**Mecanismo:** Gates validam antes de prosseguir. Falha = bloqueio + evidência.

---

### 4.2 Rastreabilidade Input→Output

**Valor:** Dado qualquer output, é possível identificar exatamente qual input o produziu.

| Output | Rastreável via |
|--------|----------------|
| Código gerado | `episode.manifest.inputs.input_hash_sha256` |
| Contrato (OpenAPI) | `contract_ledger.oas.content_hash_sha256` |
| Episode atual | `links.previous_episode_id` |

**Mecanismo:** Episode Store preserva todos inputs e outputs com hashes.

---

### 4.3 Controle de Mudança Estrutural

**Valor:** Mudanças só acontecem dentro do escopo declarado.

| Controle | Mecanismo | Evidência |
|----------|-----------|-----------|
| Escopo declarado | `change_request.scope.target` | CR arquivado no episódio |
| Escopo respeitado | Impact Gate | `IMPACT_OUT_OF_SCOPE` se violado |
| Amplitude limitada | `MAX_AFFECTED_FILES=25` | `IMPACT_TOO_BROAD` se excedido |
| Paths proibidos | `FORBIDDEN_PATTERNS` | `IMPACT_FORBIDDEN_PATH` |

**Mecanismo:** Impact Gate é obrigatório antes de patch application.

---

### 4.4 Redução de Risco Operacional

**Valor:** Comportamento inesperado é detectável via comparação de RunLogs.

| Risco | Detecção | Evidência |
|-------|----------|-----------|
| Build quebrou | `final_status: "blocked"` | `blocked_reason` no RunLog |
| Fix loop esgotado | `FIX_LOOP_EXHAUSTED` | `fix_loop.aborted_reason` |
| Integridade violada | `verify_integrity()` | Hash mismatch |
| Approval ausente | `APPROVAL_REQUIRED` | Gate bloqueou release |

**Mecanismo:** RunLog canônico com `error_codes` determinísticos.

---

### 4.5 Auditoria Retroativa Trivial

**Valor:** Auditor pode verificar qualquer execução passada sem acesso ao sistema.

| Necessidade | Solução | Como verificar |
|-------------|---------|----------------|
| Provar integridade | AuditPack com hashes | `sha256sum -c sha256sums.txt` |
| Verificar aprovação | `approval.json` no pack | `jq .decision approval.json` |
| Confirmar escopo | CR arquivado | `jq .scope change_request.json` |
| Validar chain | Episode manifest | `jq .links manifest.json` |

**Mecanismo:** AuditPack é ZIP autocontido com instruções de verificação offline.

---

## 5. SKUs Canônicos

### SKU 1 — Design-Time Governance

**O que inclui:**
- Wizard para captura estruturada de requisitos
- Blueprint Registry com verificação de integridade
- Geração de IDL Draft com validação de schema
- Gates de contrato (GATE1, GATE2)
- Geração de artefatos (SRS, IR, OpenAPI, RBAC, Plan)
- ContractLedger com hashes de cada artefato

**Em que fase atua:**
- Especificação inicial de sistemas
- Definição de contratos antes de qualquer código

**Evidências geradas:**
- `wizard_runlog.json` com session tracking
- `idl_draft.json` validado
- `contract_ledger` no RunLog com hashes
- `contracts/` directory no episódio

**O que está fora:**
- Geração de código
- Build e release
- Change Requests (requer SKU 2)
- AuditPack (requer SKU 3)

---

### SKU 2 — Change Governance

**O que inclui:**
- Change Request schema e validação
- Impact Gate com limites de escopo
- Episode chaining (`previous_episode_id`)
- Approval Gate obrigatório
- Patch Engine com policy enforcement
- Fix Loop com limite de tentativas
- Build validation (backend + frontend)
- Release pipeline (Docker Compose + smoke tests)

**Como controla mudanças:**
1. CR declara escopo (`target`, `entities_affected`)
2. Impact Gate valida paths contra escopo
3. Approval Gate bloqueia release sem approval
4. Episode novo é criado linkado ao anterior
5. CR original é arquivado no episódio

**Evidências geradas:**
- `change_request.json` no episódio
- `manifest.links.cr_hash_sha256`
- `manifest.links.previous_episode_id`
- `approval.json` com decision e approver
- `runlog.json` com `final_status` e `blocked_reason`

**O que está fora:**
- Geração inicial (requer SKU 1)
- AuditPack (requer SKU 3)
- Legacy integration

---

### SKU 3 — Audit & Traceability Pack

**O que inclui:**
- AuditPack CLI para geração de ZIPs verificáveis
- `index.json` com `root_hash_sha256`
- `sha256sums.txt` para verificação padrão
- `README_AUDIT.md` com instruções offline
- Security check (forbidden patterns)
- Legacy Bundle validation
- Legacy Gate integration
- Episode integrity verification

**Para quem é:**
- Auditoria interna
- Auditoria externa (SOC2, ISO)
- Reguladores (Banco Central, CVM)
- Due diligence (M&A, investimento)

**Evidências geradas:**
- `auditpack/index.json` com todos hashes
- `auditpack/hashes/sha256sums.txt`
- `auditpack/README_AUDIT.md`
- Legacy validation no RunLog
- Episode manifest com integrity hashes

**O que está fora:**
- Geração de código (requer SKU 1)
- Change management (requer SKU 2)
- Certificação formal (requer auditor externo)

---

### Matriz de SKUs

| Capacidade | SKU 1 | SKU 2 | SKU 3 |
|------------|-------|-------|-------|
| Wizard | ✓ | — | — |
| Blueprint Registry | ✓ | — | — |
| Contract Generation | ✓ | — | — |
| Contract Gates | ✓ | ✓ | — |
| Code Generation | — | ✓ | — |
| Change Requests | — | ✓ | — |
| Impact Gate | — | ✓ | — |
| Approval Gate | — | ✓ | — |
| Build & Release | — | ✓ | — |
| AuditPack | — | — | ✓ |
| Legacy Integration | — | — | ✓ |
| Episode Verification | — | — | ✓ |

---

## 6. Como o Produto é Adotado

### Fase 1: Piloto Controlado

**Escopo:** Um sistema novo, não-crítico, com equipe técnica receptiva.

**Objetivo:** Validar que o sistema funciona no ambiente da organização.

**Duração típica:** 4-8 semanas.

**O que acontece:**
1. Instalação do Engine (Docker ou local)
2. Captura de requisitos via Wizard
3. Geração de sistema completo
4. Validação de artefatos gerados
5. Teste de fluxo de approval
6. Geração de AuditPack

**Critério de sucesso:** Sistema gerado funciona, artefatos são verificáveis.

---

### Fase 2: Adoção Parcial

**Escopo:** Sistemas novos em uma área de negócio.

**Objetivo:** Estabelecer processo de governança com o Engine.

**Duração típica:** 3-6 meses.

**O que acontece:**
1. Definição de processo de approval formal
2. Integração com fluxo de mudanças existente
3. Treinamento de times técnicos
4. Primeiros Change Requests em sistemas piloto
5. Primeira auditoria usando AuditPacks

**Critério de sucesso:** Mudanças são rastreáveis, auditoria aceita evidências.

---

### Fase 3: Expansão

**Escopo:** Padronização para novos sistemas em múltiplas áreas.

**Objetivo:** Engine como padrão para sistemas novos.

**Duração típica:** 6-12 meses.

**O que acontece:**
1. Blueprints customizados por domínio
2. Integração com sistemas de approval existentes
3. AuditPacks em releases regulares
4. Métricas de governança coletadas

**Critério de sucesso:** Novos sistemas nascem governados.

---

### O que NÃO acontece

- Migração massiva de sistemas existentes
- Substituição de ferramentas de DevOps
- Mudança de cultura organizacional por ferramenta
- Adoção obrigatória sem patrocínio executivo

---

## 7. Diferenciação Estrutural

### Classe de Problemas Resolvidos

Ferramentas tradicionais de desenvolvimento resolvem:
- Como escrever código mais rápido
- Como testar código automaticamente
- Como fazer deploy com menos fricção

Este produto resolve:
- Como provar que uma mudança foi autorizada
- Como verificar que o escopo declarado foi respeitado
- Como auditar retroativamente sem confiar em documentação manual

### Por que isso é Estrutural

**Governança por design, não por processo:**

Ferramentas tradicionais dependem de processo externo para governança:
- Tickets em sistema separado
- Aprovações em email
- Documentação em wiki
- Logs em sistemas dispersos

Este produto gera governança como artefato da execução:
- Approval é arquivo no episódio
- CR é arquivo no episódio
- Hash de integridade é computado automaticamente
- Verificação é offline e independente

**Implicação:** Governança não pode ser esquecida, burlada ou perdida. Ela é consequência de usar o sistema.

---

### Por que Ferramentas Tradicionais Não Resolvem

| Problema | Ferramenta Tradicional | Este Produto |
|----------|------------------------|--------------|
| Provar approval | Screenshot de ticket | `approval.json` com hash |
| Verificar escopo | Revisão manual de commit | Impact Gate automático |
| Auditar mudança | Reconstruir história de commits | Episode com CR arquivado |
| Integridade | Confiar no repositório | `episode_root_hash_sha256` |

---

## 8. Riscos de Má Adoção

### Quando o Produto NÃO Deve Ser Usado

**Prototipação rápida:**
O sistema tem overhead de governança. Protótipos descartáveis não precisam de rastreabilidade.

**Sistemas triviais:**
Se um sistema pode ser reescrito em um dia, governança formal é desproporcional.

**Organizações sem processo de mudança:**
Se não existe processo de approval, o Gate de Approval será visto como obstáculo, não como proteção.

**Times que querem "mover rápido e quebrar coisas":**
O sistema prioriza rastreabilidade sobre velocidade. Culturas que valorizam speed acima de tudo não se beneficiam.

---

### Organizações que NÃO se Beneficiam

| Perfil | Por que não |
|--------|-------------|
| Startups em fase de descoberta | Especificações mudam muito rápido |
| Times de produto sem compliance | Overhead sem benefício percebido |
| Projetos open-source sem governança | Não há quem aprove formalmente |
| Organizações sem cultura de documentação | Artefatos serão ignorados |

---

### Pré-Requisitos Culturais Mínimos

1. **Processo de approval existe** (mesmo que informal)
2. **Mudanças são planejadas** (não apenas reagidas)
3. **Documentação é valorizada** (não vista como burocracia)
4. **Auditoria é realidade** (interna ou externa)
5. **Patrocínio executivo** para governança

---

## 9. Conclusão Executiva

### Por que este Produto Existe

Organizações reguladas enfrentam um problema estrutural: provar que sistemas críticos foram desenvolvidos e modificados seguindo processo controlado.

Soluções tradicionais dependem de:
- Documentação manual (pode ser falsificada ou perdida)
- Logs de sistemas dispersos (difícil correlacionar)
- Confiança em processo (não verificável tecnicamente)

Este produto existe para transformar governança de software de processo declarativo para artefato verificável.

---

### Por que é Difícil de Copiar

**Determinismo completo:**
Requer que todo o pipeline seja projetado para produzir mesmos outputs dado mesmo input. Adicionar determinismo a sistemas existentes é refatoração arquitetural.

**Governança por design:**
Requer que gates sejam obrigatórios, não opcionais. Sistemas construídos para flexibilidade não podem adicionar obrigatoriedade sem quebrar workflows existentes.

**Hash chain de episódios:**
Requer append-only storage com verificação de integridade. Sistemas com modelo de dados mutável não podem garantir que histórico não foi alterado.

**AuditPack autocontido:**
Requer que toda evidência seja exportável sem dependência do sistema. Sistemas que dependem de banco de dados para auditoria não oferecem verificação offline.

---

### Por que é Relevante em Ambientes Regulados

| Requisito Regulatório | Como este produto atende |
|-----------------------|--------------------------|
| Segregação de funções | Approval separado de execução |
| Trilha de auditoria | Episode chain com hashes |
| Integridade de registros | `episode_root_hash_sha256` |
| Verificação independente | AuditPack offline |
| Controle de mudança | Impact Gate + CR |
| Evidência de autorização | `approval.json` |

---

### Posicionamento Final

**Este produto é um sistema de governança para geração de software.**

Ele não compete com:
- IDEs (não é onde código é escrito)
- CI/CD (não faz deploy em produção)
- Low-code (não simplifica programação)
- IA autônoma (não toma decisões)

Ele compete com:
- Processos manuais de documentação
- Planilhas de controle de mudança
- Emails de approval
- Auditorias baseadas em entrevistas

**O valor não é gerar código. O valor é gerar evidência.**

---

*Este documento define o produto para fins de posicionamento comercial técnico. Não constitui contrato, garantia de funcionalidade, ou promessa de resultados específicos.*
