# Relatório: Melhorar Diagnóstico de IDL via CLI

**Data**: 2026-01-11
**Problema**: `SCHEMA: IDL parse failed at line 1, col 1: Unexpected character: @`

---

## Diagnóstico

O ISE-SaaS chama o Engine via subprocess:
```bash
python3 main.py --project X --input /path/to/spec.idl --input-mode idl ...
```

O erro "Unexpected character: @" ocorria porque:

1. O Engine recebia `raw_input = "/tmp/workspace/spec.idl"`
2. A lógica antiga verificava se o arquivo existia: `if path.exists() and path.is_file()`
3. Se o arquivo **não existia**, nada acontecia e `input_payload` permanecia como o **caminho** (`/tmp/...`)
4. O parser tentava parsear `/tmp/workspace/spec.idl` como conteúdo IDL
5. O primeiro caractere `/` era "unexpected"

---

## Solução Implementada

### 1. Detecção Explícita de Path

Nova função `_looks_like_path()` que detecta se a string parece um caminho:
- Contém `/` ou `\\`
- Termina com `.idl`
- Não contém keywords IDL (`entity`, `actor`, etc.)

### 2. Erro Classificado para Arquivo Não Encontrado

Se parece path mas arquivo não existe:
```
SCHEMA: IDL input file not found: /path/to/spec.idl
error_code: IDL_INPUT_FILE_NOT_FOUND
```

### 3. Snippet de Diagnóstico em Erros de Parse

Quando o parse falha, o erro agora inclui `first_chars`:
```
SCHEMA: IDL parse failed at line 1, col 1: ... (source=/path/file.idl, first_chars='@version("1.0.0")\n@in')
```

Isso ajuda a identificar rapidamente se o conteúdo começa com caractere inesperado.

---

## Arquivos Alterados

| Arquivo | Mudança |
|---------|---------|
| `orchestrator/engine.py` | Linhas 469-547: Nova lógica de detecção path vs inline, erros classificados |
| `tests/test_idl_e2e_pipeline.py` | Linhas 515-675: 6 novos testes em `TestIDLInputDiagnostics` |

---

## Novos Error Codes

| Error Code | Significado |
|------------|-------------|
| `IDL_INPUT_FILE_NOT_FOUND` | Caminho passado como input, mas arquivo não existe |
| `IDL_INPUT_FILE_READ_ERROR` | Arquivo existe mas não pode ser lido (permissões, etc.) |
| `IDL_PARSE_FAILED` | (existente) Parse falhou, agora com `first_chars` no erro |

---

## Testes Adicionados

```
TestIDLInputDiagnostics:
  ✅ test_file_not_found_returns_classified_error  [A] Path inexistente -> IDL_INPUT_FILE_NOT_FOUND
  ✅ test_parse_error_includes_first_chars         [B] Conteúdo inválido -> erro com first_chars
  ✅ test_valid_file_still_works                   [C] Arquivo válido continua funcionando
  ✅ test_inline_content_still_works               [C] Conteúdo inline continua funcionando
  ✅ test_path_detection_with_slash                Path com / detectado
  ✅ test_path_detection_with_idl_extension        Path com .idl detectado
```

---

## Resultados dos Testes

```bash
cd /home/bazari/engine && python -m pytest tests/test_idl_e2e_pipeline.py -v
# 21 passed in 0.40s
```

Todos os testes do IDL E2E passam, incluindo:
- 15 testes existentes (sem regressão)
- 6 novos testes de diagnóstico

---

## Exemplo de Uso

### Antes (confuso):
```
Errors: SCHEMA: IDL parse failed at line 1, col 1: Unexpected character: /
```

### Depois (claro):
```
Errors: SCHEMA: IDL input file not found: /tmp/missing/spec.idl
error_codes: ["IDL_INPUT_FILE_NOT_FOUND"]
```

Ou para parse errors com arquivo existente:
```
Errors: SCHEMA: IDL parse failed at line 1, col 1: Unexpected character: @ (source=/tmp/file.idl, first_chars='@version("1.0.0")\n@in')
```

---

**Status**: IMPLEMENTADO E TESTADO
