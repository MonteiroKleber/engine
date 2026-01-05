# Governança e segurança (Semana 8)

## Fixadas
- Nunca violar contratos (OAS/RBAC) nem policies.
- Nunca escrever fora de `/home/bazari/generated/<project>`.
- Patches devem ser mínimos e auditáveis.

## Implicações
- `UNKNOWN_BUT_PATCHABLE` pode tentar um patch pequeno.
- `FATAL_UNCLASSIFIED` deve encerrar o fluxo com falha (sem tentar patch arriscado).
