# Prompt — Dia 4: REQ Analyst (MOCK)

Implemente `intake/req_analyst.py` no modo Semana 3:
- se llm.enabled=false (padrão): MOCK determinístico
- extrair summary simples
- criar 1 ator padrão admin
- criar 3–6 FRs padrões baseadas em verbos detectados ("cadastrar", "listar", "editar")
- preencher open_questions se faltar: auth required? perfis? entidades?
- gerar `SRS.json` sempre compatível com o schema

Regras:
- nunca inventar regras de negócio específicas.

Aceite:
- raw_text → gera SRS.json compatível com `schemas/srs.schema.json`.
