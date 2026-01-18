"""LLM Prompt templates for NL extraction."""

SYSTEM_PROMPT = """You are a policy extraction assistant. Your task is to extract structured information from natural language policy descriptions.

Extract the following elements:
1. Actors: People or roles mentioned (e.g., "manager", "analyst", "user")
2. Entities: Resources or objects mentioned (e.g., "expense", "invoice", "document")
3. Policies: Rules and constraints described (approval, segregation of duties, RBAC, invariants)
4. Workflows: Sequential processes if described

Output ONLY valid JSON in the exact format specified. Do not include explanations or markdown."""


def build_extraction_prompt(text: str, language: str = "en") -> str:
    """Build the extraction prompt for the LLM.

    Args:
        text: Natural language text to extract from.
        language: Language of the text.

    Returns:
        Formatted prompt string.
    """
    schema_example = """{
  "extraction": {
    "actors": [
      {
        "actor_key": "actor-<normalized-name>",
        "name": "<Display Name>",
        "roles": ["<role1>", "<role2>"]
      }
    ],
    "entities": [
      {
        "entity_key": "entity-<normalized-name>",
        "name": "<Display Name>",
        "entity_type": "<type>"
      }
    ],
    "policies": [
      {
        "policy_key": "policy-<type>-001",
        "policy_type": "<approval|sod|rbac|invariant>",
        "description": "<brief description>",
        "actor_refs": ["actor-..."],
        "entity_refs": ["entity-..."],
        "conditions": {}
      }
    ],
    "workflows": []
  }
}"""

    language_hint = ""
    if language == "pt":
        language_hint = "\n\nNote: The input text is in Portuguese. Extract and normalize role/entity names to English (e.g., 'gerente' -> 'manager', 'despesa' -> 'expense')."

    return f"""Extract structured policy information from the following text.

Input text:
\"\"\"{text}\"\"\"
{language_hint}
Output the extraction in this exact JSON format:
{schema_example}

Rules:
- actor_key must be "actor-" followed by normalized lowercase name (e.g., "actor-manager")
- entity_key must be "entity-" followed by normalized lowercase type (e.g., "entity-expense")
- policy_key must be "policy-<type>-001" format
- policy_type must be one of: approval, sod, rbac, invariant
- roles must be lowercase English (translate if needed)
- Output ONLY the JSON, no markdown, no explanations

JSON:"""
