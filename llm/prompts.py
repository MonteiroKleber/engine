"""Templates de prompts para o LLM."""

from typing import Dict


SYSTEM_PROMPTS: Dict[str, str] = {
    "analyst": """Você é um analista de requisitos de software experiente.
Sua função é analisar requisitos de usuários e extrair informações estruturadas.
Responda sempre em português brasileiro.""",

    "classifier": """Você é um especialista em classificação de projetos de software.
Sua função é identificar o tipo de projeto e blueprint mais adequado.
Responda sempre em português brasileiro.""",

    "clarifier": """Você é um especialista em elicitação de requisitos.
Sua função é gerar perguntas de clarificação para requisitos ambíguos.
Responda sempre em português brasileiro.""",
}


PROMPT_TEMPLATES: Dict[str, str] = {
    "analyze_requirements": """Analise os seguintes requisitos e extraia informações estruturadas:

{requirements}

Retorne um JSON com:
- functional_requirements: lista de requisitos funcionais
- non_functional_requirements: lista de requisitos não-funcionais
- ambiguities: lista de pontos ambíguos que precisam clarificação""",

    "classify_blueprint": """Com base nos requisitos abaixo, classifique o tipo de blueprint mais adequado:

{requirements}

Tipos disponíveis: {blueprint_types}

Retorne um JSON com:
- blueprint_type: tipo selecionado
- confidence: confiança de 0 a 1
- reasoning: justificativa""",

    "generate_clarifications": """Analise os requisitos abaixo e gere perguntas de clarificação:

{requirements}

Máximo de perguntas: {max_questions}

Retorne uma lista JSON de perguntas ordenadas por prioridade.""",
}
