# Feedback Estrutural do Piloto - PILOT-2026-001

## Metadados

| Campo | Valor |
|-------|-------|
| Piloto | PILOT-2026-001 |
| Data de Execução | 2026-01-08 |
| Data de Análise | 2026-01-08 |
| Artefatos Analisados | runlog.json, manifest.json, approval.json, change_request.json, README_AUDIT.md |
| Documento Base | /docs/pilot/pilot_observations.md |

---

## Itens de Feedback

---

### FB-01

| Campo | Valor |
|-------|-------|
| **ID** | FB-01 |
| **Categoria** | A — Fricção Operacional |
| **Descrição objetiva** | O fluxo de criação de episódio requer passos manuais separados: (1) executar pipeline, (2) criar episódio, (3) registrar contratos, (4) finalizar episódio. Não existe comando único que faça tudo. |
| **Artefato(s) relacionados** | runlog.json, manifest.json |
| **Passo do fluxo** | Após execução do pipeline (main.py --skip-build) |
| **Impacto observado** | Operador precisa executar script Python customizado para vincular artefatos ao episódio |
| **Natureza do problema** | |
| | [x] Ergonomia |
| | [ ] Clareza documental |
| | [ ] Comunicação de erro |
| | [ ] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [x] CLI UX |
| | [x] Documentação |
| | [ ] Ordem de apresentação |
| | [ ] Outro |

---

### FB-02

| Campo | Valor |
|-------|-------|
| **ID** | FB-02 |
| **Categoria** | D — Dúvida de Confiança |
| **Descrição objetiva** | O comando `episodes verify` retorna erro de integridade após aprovação ser adicionada, porque o root_hash foi computado antes da aprovação. Mensagem de erro não distingue entre "modificação maliciosa" e "adição legítima de aprovação". |
| **Artefato(s) relacionados** | manifest.json (integrity.episode_root_hash_sha256) |
| **Passo do fluxo** | Verificação de integridade pós-aprovação |
| **Impacto observado** | Operador pode interpretar erro como problema real quando é comportamento esperado |
| **Natureza do problema** | |
| | [ ] Ergonomia |
| | [ ] Clareza documental |
| | [x] Comunicação de erro |
| | [x] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [x] Mensagem |
| | [ ] CLI UX |
| | [x] Documentação |
| | [ ] Ordem de apresentação |
| | [ ] Outro |

---

### FB-03

| Campo | Valor |
|-------|-------|
| **ID** | FB-03 |
| **Categoria** | B — Carga Cognitiva Humana |
| **Descrição objetiva** | Ao aprovar um episódio, o aprovador não recebe um resumo do que está aprovando. Precisa consultar manualmente o manifest.json ou runlog.json para ver entidades, operações, e contratos gerados. |
| **Artefato(s) relacionados** | approval.json, manifest.json |
| **Passo do fluxo** | Comando `episodes approve` |
| **Impacto observado** | Aprovador escreveu justificativa genérica porque não tinha resumo visual do conteúdo |
| **Natureza do problema** | |
| | [x] Ergonomia |
| | [ ] Clareza documental |
| | [ ] Comunicação de erro |
| | [x] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [x] CLI UX |
| | [ ] Documentação |
| | [x] Ordem de apresentação |
| | [ ] Outro |

---

### FB-04

| Campo | Valor |
|-------|-------|
| **ID** | FB-04 |
| **Categoria** | C — Custo de Governança Percebido |
| **Descrição objetiva** | Para fazer uma mudança governada, foi necessário: (1) criar arquivo CR JSON manualmente, (2) criar arquivo IDL Draft v2 manualmente, (3) executar comando change, (4) executar pipeline separadamente, (5) registrar contratos, (6) aprovar. São 6 passos para uma mudança simples. |
| **Artefato(s) relacionados** | change_request.json, manifest.json (Episode B) |
| **Passo do fluxo** | Fluxo completo de Change Request |
| **Impacto observado** | Sensação de processo "pesado" para mudança que é apenas adicionar 1 campo |
| **Natureza do problema** | |
| | [x] Ergonomia |
| | [ ] Clareza documental |
| | [ ] Comunicação de erro |
| | [x] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | PARCIAL |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [x] CLI UX |
| | [x] Documentação |
| | [ ] Ordem de apresentação |
| | [x] Outro: Templates de CR |
| **Nota** | O número de passos pode ser reduzido com automação de CLI, mas a necessidade de CR formal e aprovação explícita NÃO pode ser removida — isso É a governança. |

---

### FB-05

| Campo | Valor |
|-------|-------|
| **ID** | FB-05 |
| **Categoria** | D — Dúvida de Confiança |
| **Descrição objetiva** | O AuditPack contém dois hashes: `source_root_hash` (do episódio original) e `root_hash` (do pack). A diferença entre eles não é explicada de forma clara no README_AUDIT.md. |
| **Artefato(s) relacionados** | README_AUDIT.md, index.json |
| **Passo do fluxo** | Geração e verificação do AuditPack |
| **Impacto observado** | Auditor pode questionar por que os hashes são diferentes |
| **Natureza do problema** | |
| | [ ] Ergonomia |
| | [x] Clareza documental |
| | [ ] Comunicação de erro |
| | [x] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [ ] CLI UX |
| | [x] Documentação |
| | [ ] Ordem de apresentação |
| | [ ] Outro |

---

### FB-06

| Campo | Valor |
|-------|-------|
| **ID** | FB-06 |
| **Categoria** | B — Carga Cognitiva Humana |
| **Descrição objetiva** | O manifest.json mostra `idl_hash_sha256: null` mesmo quando o sistema foi gerado corretamente. Isso ocorre porque o fluxo usou linguagem natural → SRS → IR, sem passar por IDL canônico. O campo nulo pode gerar dúvida sobre completude. |
| **Artefato(s) relacionados** | manifest.json (contracts.idl_hash_sha256) |
| **Passo do fluxo** | Visualização do episódio |
| **Impacto observado** | Campo nulo pode parecer "faltando algo" quando na verdade é fluxo alternativo válido |
| **Natureza do problema** | |
| | [ ] Ergonomia |
| | [x] Clareza documental |
| | [ ] Comunicação de erro |
| | [x] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [ ] CLI UX |
| | [x] Documentação |
| | [ ] Ordem de apresentação |
| | [ ] Outro |

---

### FB-07

| Campo | Valor |
|-------|-------|
| **ID** | FB-07 |
| **Categoria** | C — Custo de Governança Percebido |
| **Descrição objetiva** | Cada aprovação requer 6 parâmetros obrigatórios no CLI: --episode-id, --decision, --reason, --approver-name, --role, --base-path. É verboso para operação frequente. |
| **Artefato(s) relacionados** | approval.json |
| **Passo do fluxo** | Comando `episodes approve` |
| **Impacto observado** | Comando longo e propenso a erros de digitação |
| **Natureza do problema** | |
| | [x] Ergonomia |
| | [ ] Clareza documental |
| | [ ] Comunicação de erro |
| | [ ] Expectativa humana |
| | [ ] Outro |
| **É permitido corrigir sem quebrar contratos?** | SIM |
| **Tipo de ajuste permitido** | |
| | [ ] Mensagem |
| | [x] CLI UX |
| | [ ] Documentação |
| | [ ] Ordem de apresentação |
| | [x] Outro: Arquivo de configuração para defaults |
| **Nota** | Os parâmetros em si são NECESSÁRIOS para auditoria. O ajuste é apenas ergonômico (ex: ler approver de config file, permitir --interactive). |

---

## Tendências Observadas

### Padrões Repetidos de Dúvida

1. **Hashes diferentes em contextos diferentes**: O mesmo episódio tem hashes diferentes dependendo de quando é verificado (antes/depois de aprovação) e onde é verificado (episódio vs AuditPack). Isso é correto tecnicamente, mas gera dúvida.

2. **Campos nulos vs campos ausentes**: Quando um campo é `null` (como `idl_hash_sha256`), não fica claro se é "não aplicável" ou "erro".

### Pontos Onde Humanos Tentaram "Atalho"

1. **Registro manual de contratos**: O piloto exigiu script Python customizado para vincular artefatos ao episódio. Isso sugere que o fluxo natural seria o pipeline criar o episódio automaticamente.

2. **CR criado manualmente**: O Change Request foi escrito à mão em JSON. Em uso real, operadores provavelmente pediriam templates ou wizard.

### Onde a Governança Foi Questionada

1. **"Por que preciso aprovar se todos os gates passaram?"**
   - Resposta: Porque gates verificam conformidade técnica, mas aprovação é decisão de negócio. São coisas diferentes. Isso É valor, não defeito.

2. **"Por que não posso editar o episódio depois de finalizado?"**
   - Resposta: Porque imutabilidade é o que permite auditoria confiável. Se pudesse editar, não seria auditável. Isso É valor, não defeito.

3. **"Por que o hash muda depois da aprovação?"**
   - Resposta: Porque aprovação é um arquivo novo adicionado. O hash original prova que o conteúdo técnico não mudou. A diferença prova que aprovação foi adicionada depois. Isso É rastreabilidade, não defeito.

---

## Decisões de Produto

### Ajustes Permitidos Pós-Piloto

| ID | Ajuste | Tipo | Justificativa |
|----|--------|------|---------------|
| FB-01 | Criar comando `main.py --create-episode` que execute pipeline E crie episódio automaticamente | CLI UX | Reduz passos manuais sem alterar contratos |
| FB-02 | Melhorar mensagem de `episodes verify` para distinguir "hash diferente por aprovação" de "modificação não autorizada" | Mensagem | Clareza sem alterar comportamento |
| FB-03 | Comando `approve` deve mostrar resumo do episódio antes de pedir confirmação | CLI UX | Decisão informada sem alterar contrato |
| FB-04 | Criar templates de CR para mudanças comuns (add field, add usecase) | Documentação | Ergonomia sem alterar schema |
| FB-05 | Expandir README_AUDIT.md explicando diferença entre source_root_hash e root_hash | Documentação | Clareza para auditores |
| FB-06 | Documentar que `idl_hash_sha256: null` é válido para fluxo natural→SRS→IR | Documentação | Evitar confusão |
| FB-07 | Permitir arquivo `.engine/approver.json` com defaults de approver-name, role, org | CLI UX | Ergonomia sem alterar dados registrados |

### Ajustes Proibidos (Explicitamente Rejeitados)

| Sugestão Hipotética | Por Que NÃO Será Implementado |
|---------------------|-------------------------------|
| "Aprovar automaticamente se todos os gates passarem" | Aprovação é decisão HUMANA, não técnica. Gates verificam conformidade, humanos decidem se querem prosseguir. |
| "Permitir editar episódio depois de finalizado" | Imutabilidade é o que permite auditoria. Sem ela, não há como provar que algo não foi alterado. |
| "Modo rápido sem Change Request" | CR é o registro formal de POR QUE a mudança foi feita. Sem ele, não há rastreabilidade de intenção. |
| "Pular aprovação para mudanças pequenas" | O tamanho da mudança não determina seu impacto. Uma linha pode quebrar produção. Aprovação é sobre responsabilidade, não volume. |
| "Unificar hashes para evitar confusão" | Hashes diferentes em momentos diferentes PROVAM a sequência de eventos. Isso é feature, não bug. |
| "Remover campos nulos do manifest" | Campos nulos documentam que o fluxo NÃO usou aquele artefato. Remover perderia informação. |

---

## Conclusão

O piloto revelou fricções de **ergonomia** e **clareza documental**, mas nenhuma falha de **governança**.

As fricções identificadas são resolvíveis com:
- Melhorias de CLI (comandos compostos, defaults configuráveis)
- Melhorias de mensagens (distinção de erros)
- Melhorias de documentação (explicação de conceitos)

Nenhuma das melhorias sugeridas requer:
- Pular gates
- Automatizar decisões humanas
- Flexibilizar contratos
- Permitir modificação de artefatos finalizados

> **Regra aplicada**: Se algo "incomoda", mas protege o sistema, isso NÃO é bug — é propriedade.
