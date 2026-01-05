# Regras de segurança (Semana 7)

## Fixadas
- O motor nunca se auto-modifica.
- Templates nunca são alterados.
- Tudo que é gerado vai para `/home/bazari/generated/`.

## Implicações
- Patch Engine deve bloquear qualquer path fora de `/home/bazari/generated/<project>/`.
- Repo generator só escreve dentro de `/home/bazari/generated/<project>/`.
- Build validator só executa comandos dentro de `/home/bazari/generated/<project>/`.
