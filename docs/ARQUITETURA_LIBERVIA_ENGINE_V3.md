Perfeito. Abaixo está a **versão corrigida e alinhada do Documento v2**, já incorporando **formalmente a distinção entre Console Operacional do Engine e TARGET Institucional**, no tom certo para **arquitetos seniores** e sem abrir brecha conceitual.

O texto está pronto para **circular entre arquitetos**, inclusive como base de validação externa.

---

# Arquitetura Libervia/EDAP Engine

## Documento Técnico para Validação Arquitetural

**Versão:** 2.1 (Alinhada Arquiteturalmente)
**Data:** Janeiro 2026
**Engine Version:** 8.1.x (API compatível 8.1.1)
**Status:** Documento de alinhamento conceitual e técnico

---

## 1. Visão Geral

O **Libervia/EDAP Engine** é uma plataforma de governança computacional que implementa o padrão **Enterprise Agent**, baseada na separação explícita entre:

* **Decisão institucional**
* **Execução determinística**
* **Enforcement fora do modelo**
* **Auditabilidade independente**

O Engine não é um produto final de negócio.
Ele é uma **infraestrutura institucional** usada para construir produtos institucionais governados.

---

## 2. Proposta de Valor

| Abordagem Tradicional           | Libervia/EDAP Engine                      |
| ------------------------------- | ----------------------------------------- |
| Regras embutidas em código      | Contratos institucionais declarativos     |
| Decisão implícita               | Decisão explícita, versionada e auditável |
| IA com acesso direto a sistemas | IA como ator governado                    |
| Auditoria parcial               | Ledger append-only com hash chain         |
| Frontend + Backend acoplados    | Engine governado + Targets descartáveis   |

> **Nota:** O Engine governa decisões e execução. A experiência do usuário pertence exclusivamente ao Target institucional.

---

## 3. Arquitetura de Alto Nível

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TARGET INSTITUCIONAL (Produto Final)                 │
│        (Web / Mobile / CLI / Chatbot — a ser desenvolvido)               │
│                                                                         │
│   Interfaces específicas do domínio da instituição                      │
│   (financeiro, RH, operações, suporte, etc.)                            │
└───────────────┬─────────────────────────────────────────────────────────┘
                │
        REST API (OpenAPI gerado pelo Bundle)
                │
┌───────────────▼─────────────────────────────────────────────────────────┐
│                         LIBERVIA / EDAP ENGINE                           │
│                                                                         │
│  Runtime Gates (Governança Determinística)                               │
│  - RBAC                                                                  │
│  - SoD                                                                   │
│  - Mandates                                                             │
│  - Autonomy (L0–L4)                                                      │
│                                                                         │
│  Contratos Institucionais (Bundle)                                       │
│  Persistência Governada                                                  │
│  Audit Ledger Append-only                                                │
└───────────────┬─────────────────────────────────────────────────────────┘
                │
        Compilação Governada (ISE)
                │
┌───────────────▼─────────────────────────────────────────────────────────┐
│                         IDL / DSL (Fonte Versionável)                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Definição Formal de TARGET (Esclarecimento Crítico)

### 4.1 O que é o TARGET

O **TARGET** é a **interface do sistema institucional construído a partir do Libervia/EDAP**.

Ele representa:

* O **negócio da instituição**
* O **produto final entregue ao usuário**
* A **experiência operacional real**

Exemplos:

* Portal financeiro interno
* App de aprovação de despesas
* Chatbot institucional
* CLI para times internos

O Target:

* Consome apenas a API REST gerada pelo Bundle
* Não contém lógica de governança
* Não implementa regras de negócio
* Pode ser substituído sem impacto institucional

---

### 4.2 O que o TARGET não é

O TARGET **não é**:

* O console administrativo do Engine
* A interface de operação do Libervia/EDAP
* Um painel de debug ou governança do sistema

---

### 4.3 Console Operacional do Engine (Camada Separada)

O Libervia/EDAP **possui um console operacional embutido**, usado para:

* Administração do próprio Engine
* Governança institucional (mandates, autonomy, policies)
* EGE (pins, drift, rollback)
* Inspeção de ledger e contratos
* Operação técnica do produto

Esse console:

* É parte do **produto Libervia/EDAP**
* Destina-se a **arquitetos e operadores**
* **Não representa** a instituição final
* **Não é o Target**

> Portanto, para fins arquiteturais, **o TARGET institucional permanece não implementado**.

---

## 5. Pipeline de Compilação

O Libervia funciona como um **compilador institucional**.

```
IDL / DSL (texto) 
      ↓
IRCS (Intermediate Representation canônico)
      ↓
Bundle (contratos JSON)
      ↓
Runtime Governado
```

### Fonte de verdade

* **IDL / DSL textual versionável**
* O IR é derivado e verificável
* O Bundle carrega hash do IDL de origem

---

## 6. Persistência (MVP e Evolução)

### 6.1 State Store (MVP)

* Persistência file-based por instituição
* Estado atual das entidades
* Controle de versão por entidade
* Operações atômicas no runtime

### 6.2 Audit Ledger

* Append-only
* Hash chain por instituição
* Verificação de integridade no boot
* Independente do backend de dados

### 6.3 Backend Plugável (Roadmap)

A escolha de storage **não pertence ao Target nem à IA**.

Ela é definida por **configuração institucional governada**.

Implementações previstas:

* JSON (MVP)
* PostgreSQL (alto volume)
* Outros backends compatíveis

---

## 7. Runtime Gates (Governança)

Toda operação passa por **gates determinísticos**, fora do modelo:

1. RBAC
2. SoD
3. Mandates
4. Autonomy (nível mínimo requerido)

Outros controles institucionais:

* Policies
* Approvals
* Invariants
* Freeze / Emergency Stop
* EGE (drift, pins, rollback)

---

## 8. Papel da IA

A IA **não atua no runtime**.

Ela pode:

* Auxiliar na criação do IDL
* Sugerir estruturas
* Ajudar na validação pré-compilação

Ela **não pode**:

* Executar ações
* Bypassar gates
* Alterar contratos em runtime
* Se auto-expandir

IA é tratada como **ator governado**, quando aplicável.

---

## 9. Estado Atual vs Roadmap

### Implementado

* Runtime gates completos
* Ledger por instituição
* Persistência governada
* Console operacional do Engine
* Multi-tenancy isolado

### Roadmap

* Targets institucionais (Web/Mobile/Chatbot)
* DSL textual como entrada primária
* Backend de storage plugável
* Integrações SSO/OIDC no Target

---

## 10. Conclusão Arquitetural

* O Libervia/EDAP **não é um app**
* Ele é uma **infraestrutura institucional**
* O Target é o produto final da instituição
* O Target está **intencionalmente desacoplado**
* O console atual **não é o Target**

Essa separação é essencial para:

* Governança real
* Escalabilidade institucional
* Evolução independente
* Adoção enterprise

---

**Documento preparado para alinhamento arquitetural.**
*Libervia/EDAP Engine — Governança Computacional*
