# Templates de Change Request

Este diretorio contem templates pre-formatados para criar Change Requests (CRs) de forma rapida e consistente.

## Templates Disponiveis

| Template | Uso | Arquivo |
|----------|-----|---------|
| **Basico** | Qualquer tipo de mudanca | `cr_basic.json` |
| **Nova Feature** | Adicionar nova funcionalidade | `cr_new_feature.json` |
| **Bugfix** | Correcao de bugs | `cr_bugfix.json` |
| **Migracao de Schema** | Adicionar/modificar campos | `cr_schema_migration.json` |

## Como Usar

1. Copie o template apropriado para seu projeto:
   ```bash
   cp /path/to/templates/cr_new_feature.json ./minha_cr.json
   ```

2. Edite os campos marcados com `[PLACEHOLDER]`:
   - `change_request_id`: ID unico para a CR (ex: CR-FEAT-001)
   - `previous_episode_id`: ID do episodio base
   - `reason`: Motivo da mudanca
   - `requested_by`: Dados do solicitante
   - `scope`: Escopo da mudanca
   - `acceptance_criteria`: Criterios de aceite
   - `volatile.timestamp`: Data/hora da solicitacao

3. Execute o comando change:
   ```bash
   python -m episodes.episodes_cli change \
     --previous-episode-id EPISODE_ID \
     --cr ./minha_cr.json
   ```

## Campos Obrigatorios

Todos os CRs devem conter:

- `schema_version`: Sempre `"idl_change_request.v1"`
- `change_request_id`: Identificador unico
- `previous_episode_id`: Episodio base para a mudanca
- `reason`: Justificativa clara
- `requested_by`: Quem solicitou (nome, papel, org)
- `scope.summary`: Resumo em uma linha
- `acceptance_criteria`: Lista de criterios verificaveis
- `invariants`: Restricoes que devem ser mantidas

## Niveis de Risco

- **low**: Mudanca aditiva, sem alteracao de comportamento existente
- **medium**: Mudanca com impacto moderado, requer testes extras
- **high**: Mudanca critica, requer aprovacao especial e rollback plan

## Severidade de Invariants

- **must**: Obrigatorio - violacao bloqueia a mudanca
- **should**: Recomendado - violacao gera warning
- **may**: Opcional - apenas informativo
