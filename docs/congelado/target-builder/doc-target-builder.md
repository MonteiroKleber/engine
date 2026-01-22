Congelar o blueprint agora e só avançar para a implementação do Target Builder depois que os últimos alinhamentos do engine e do modelo institucional estiverem 100% estáveis. Isso evita retrabalho e preserva o papel do engine como base canônica.

Abaixo está o documento consolidado e “congelável” do Target Builder v1, exatamente no espírito proposto, escrito para servir como referência arquitetural futura.

Target Builder v1
Blueprint Arquitetural (Congelado)

Status: Congelado para implementação futura
Dependência: Libervia / EDAP Engine (IDL-driven, OpenAPI estável)
Escopo: Geração automática de Target institucional (UI/UX)
Repositório: Separado e desacoplado do engine

1. Objetivo do Target Builder

O Target Builder é um compilador de interface institucional, responsável por gerar automaticamente um Target institucional (UI/UX) a partir dos artefatos produzidos pelo Libervia/EDAP Engine.

Ele não é parte do engine e não executa regras de negócio.
Seu papel é materializar visualmente uma instituição já governada.

Em termos simples:

O engine governa.
O Target apresenta.

2. Separação Arquitetural (Decisão chave)
2.1 Engine vs Target Builder
Componente	Responsabilidade
Engine	Governança, contratos, runtime, ledger, OpenAPI
Target Builder	Geração de UI institucional
Target	Interface final usada pela instituição

O Target Builder:

❌ Não importa código do engine

❌ Não reimplementa regras

❌ Não toma decisões

✅ Consome apenas artefatos estáveis

3. Entradas Canônicas do Target Builder

O Target Builder trabalha exclusivamente com artefatos, nunca com código interno do engine.

3.1 Entradas obrigatórias

openapi.json (gerado pelo engine)

bundle/ (contratos instalados)

bundle.manifest.json

contract_ledger.json

3.2 Entradas opcionais

institution_config.json (para UX e status)

ui_contract.json (customizações e overrides)

workspace/
  inputs/
    openapi.json
    bundle/
      rbac.json
      workflows.json
      approvals.json
      policies.json
      mandates.json
      autonomy.json
      invariants.json
      openapi.yaml
    bundle.manifest.json
    contract_ledger.json
    institution_config.json   (opcional)
    ui_contract.json          (opcional)

4. Saídas do Target Builder

O Target Builder gera código, mas com separação clara entre o que é gerado e o que pode ser customizado.

workspace/
  out/
    target-app/
      src/
        generated/     # código 100% gerado (não editar)
        overrides/     # customizações manuais (preservadas)
        app/           # shell mínimo (routing, theme)
      tb.manifest.json
      tb.lock.json

Regras fundamentais

generated/ é sempre regenerado

overrides/ nunca é sobrescrito

Toda geração é determinística

Toda geração é diffável

5. Interface Pública do Target Builder (v1)
5.1 CLI como interface primária

Comandos previstos:

tb init
Cria workspace inicial + ui_contract.json

tb pull --engine-url --institution-id --bundle
Baixa OpenAPI e bundle do engine

tb generate
Gera o Target institucional

tb dev
Roda o Target localmente (proxy para engine)

tb build
Gera build final do Target

tb diff
Mostra diferenças entre gerações (governança visual)

6. Target Institucional v1 (Web)

O v1 foca em Web Target institucional, não mobile, não chatbot.

6.1 Estrutura base gerada

App Shell institucional

Header com:

instituição

ambiente

bundle hash

estado (freeze, emergency, drift)

Side navigation por módulos/departamentos

Footer com status técnico (engine, hashes, versão)

7. Telas Geradas Automaticamente
7.1 Inbox de Aprovações

Lista de approvals pendentes

Filtros por entidade, status, role

Ações:

Aprovar

Rejeitar

Integração direta com
POST /approvals/{id}/decide

7.2 Telas de Operações (CRUD Governado)

Para cada endpoint governado no OpenAPI:

Tela de criação (POST)

Tela de detalhe (quando aplicável)

Mensagens claras quando gates bloqueiam

O Target não decide nada.
Ele apenas reflete o que o engine permite ou bloqueia.

7.3 Timeline do Caso

Linha do tempo do caso

Eventos do ledger:

gates

decisões

atores

hashes

Correlação visual entre ação e efeito

7.4 Painel de Governança (Read-only)

Visualização de:

policies

mandates

autonomy

Regras efetivas por endpoint

Versões e hashes

7.5 Painel Administrativo

Freeze mode

Emergency stop

Rate limit

EGE:

drift status

pins

proposals

8. UI Contract v1 (Customização Controlada)

Arquivo opcional para ajuste fino de UI sem quebrar geração.

Exemplo
{
  "version": "ui.v1",
  "screens": {
    "POST /finance/expenses": {
      "title": "Nova despesa",
      "field_order": ["amount", "currency", "description"],
      "hidden_fields": ["internal_notes"]
    }
  }
}


Permite:

labels

ordem de campos

campos ocultos

seções visuais

pequenas regras de visibilidade

9. Mapeamento Engine → UI
OpenAPI

Schemas → formulários

Responses → cards

Errors → banners padronizados

Contratos

RBAC → esconder/desabilitar ações

Policies → validações visuais (espelho)

Mandates/Autonomy → avisos de requisito

Freeze/Emergency/EGE → bloqueios globais

10. Versionamento e Integridade

O Target Builder gera:

tb.lock.json

hash do OpenAPI

hash do bundle.manifest

hash do contract_ledger

hash do ui_contract

Isso garante:

UI alinhada a contratos

impossibilidade de drift silencioso

rastreabilidade institucional

11. Escopo do v1 (Congelado)
Incluído

Target Web institucional

Inbox de aprovações

Operações principais (ex: finance)

Painel admin

UI Contract básico

Overrides preserváveis

Fora do v1

Mobile Target

Chatbot Target

Query builder avançado

Designer visual no-code

Multi-target simultâneo

12. Princípios Arquiteturais Preservados

Decisão separada de execução

Enforcement fora da UI

UI como reflexo institucional

Governança auditável

Geração determinística

Override controlado

13. Estado da Proposta

✅ Arquitetura definida

✅ Interfaces claras

✅ Separação engine/target preservada

⏸️ Implementação deliberadamente postergada

A proposta está congelada até alinhamentos finais do engine, DSL e contratos.

14. Conclusão

O Target Builder não é apenas um gerador de telas.
Ele é a materialização visual de uma instituição governada.

Congelar este blueprint agora:

preserva a coerência do sistema

evita decisões prematuras de UI

mantém o engine como fonte de verdade

cria uma base sólida para escala futura

Documento congelado para referência futura.
Libervia / EDAP – Target Builder v1 Blueprint