"""Analista de requisitos com mini-gramática determinística.

Extrai entidades, campos e relações de texto livre PT-BR sem usar LLM.
Implementa 4 formas de parsing (A, B, C, D) em ordem de prioridade.
"""

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


# ==================== CONSTANTES ====================

# Token separadores
SEP_ENTITY = "§ENT§"
SEP_FIELDS = "§FLD§"

# Tabela de exceções para singularização
SINGULAR_EXCEPTIONS = {
    "pais": "pai",
    "meses": "mes",
    "maes": "mae",
    "caes": "cao",
    "paes": "pao",
    "alemoes": "alemao",
    "capitaes": "capitao",
    "cidadaos": "cidadao",
    "itens": "item",
}

# Artigos a remover do início de nomes
ARTICLES = {"o", "a", "os", "as", "um", "uma", "uns", "umas"}

# Stopwords a remover do meio de campos
FIELD_STOPWORDS = {"do", "da", "de", "para", "dos", "das"}

# Palavras que sao campos, NUNCA podem virar entidades
FIELD_ONLY_WORDS = {
    "nome", "cnpj", "cpf", "endereco", "endereço", "email", "telefone",
    "data", "valor", "preco", "preço", "quantidade", "descricao", "descrição",
    "status", "tipo", "codigo", "código", "numero", "número", "observacao",
    "observação", "ativo", "inativo", "peso", "altura", "largura",
}

# Palavras que indicam o tipo de sistema, NAO sao entidades
SYSTEM_KEYWORDS = {
    "sistema", "cadastro", "controle", "gestao", "gestão", "gerenciamento",
    "modulo", "módulo", "aplicacao", "aplicação", "plataforma", "software",
}

# Padrões para detectar relações textuais
RELATION_PATTERNS = [
    (r"(\w+)\s+pertence\s+a\s+(\w+)", "many_to_one"),  # X pertence a Y
    (r"(\w+)\s+tem\s+(\w+)", "one_to_many"),  # X tem Y (inverte)
    (r"(\w+)\s+possui\s+(\w+)", "one_to_many"),  # X possui Y (inverte)
    (r"(\w+)\s+vinculado\s+a\s+(\w+)", "many_to_one"),  # X vinculado a Y
    (r"(\w+)\s+associado\s+a\s+(\w+)", "many_to_one"),  # X associado a Y
]

# Perguntas padrão para open_questions
DEFAULT_OPEN_QUESTIONS = [
    "Autenticação é necessária? Qual tipo (login/senha, OAuth, SSO)?",
    "Quais perfis de usuário existem além de admin?",
    "Quais são as principais entidades/recursos do sistema?",
    "Existem regras de permissão específicas por perfil?",
    "Há necessidade de auditoria/log de ações?",
]

# ==================== REGRAS v2 ====================

# Tipos de regras suportados
RULE_TYPES = {
    "REQUIRED_RELATION": "required_relation",
    "OWNERSHIP_REQUIRED": "ownership_required",
    "CONVERSION": "conversion",
    "PARTIAL_PAYMENT": "partial_payment",
    "STATUS_DEPENDS_ON_PAYMENT": "status_depends_on_payment",
}

# Padrões para parsing de regras
RULE_PATTERNS = [
    # A: todo X deve ter Y → REQUIRED_RELATION(X, Y)
    (r"todo\s+(\w+)\s+deve\s+ter\s+(\w+)", "REQUIRED_RELATION"),
    (r"toda\s+(\w+)\s+deve\s+ter\s+(\w+)", "REQUIRED_RELATION"),
    (r"cada\s+(\w+)\s+deve\s+ter\s+(\w+)", "REQUIRED_RELATION"),

    # B: X pertence a Y → OWNERSHIP_REQUIRED(X, Y)
    (r"(\w+)\s+pertence\s+a\s+(\w+)", "OWNERSHIP_REQUIRED"),
    (r"(\w+)\s+deve\s+pertencer\s+a\s+(\w+)", "OWNERSHIP_REQUIRED"),

    # C: X pode virar Y → CONVERSION(X, Y)
    (r"(\w+)\s+pode\s+virar\s+(\w+)", "CONVERSION"),
    (r"(\w+)\s+pode\s+ser\s+convertido\s+em\s+(\w+)", "CONVERSION"),
    (r"(\w+)\s+pode\s+se\s+tornar\s+(\w+)", "CONVERSION"),

    # D: X pode ter valor parcial → PARTIAL_PAYMENT(X)
    (r"(\w+)\s+pode\s+ter\s+valor\s+parcial", "PARTIAL_PAYMENT"),
    (r"(\w+)\s+aceita\s+pagamento\s+parcial", "PARTIAL_PAYMENT"),

    # E: status de X depende de pagamento → STATUS_DEPENDS_ON_PAYMENT(X)
    (r"status\s+de\s+(\w+)\s+depende\s+de\s+pagamento", "STATUS_DEPENDS_ON_PAYMENT"),
    (r"status\s+do\s+(\w+)\s+depende\s+de\s+pagamento", "STATUS_DEPENDS_ON_PAYMENT"),
]

# Marcadores de FK opcional
OPTIONAL_FK_MARKERS = {"opcional", "optional", "pode ser vazio", "nao obrigatorio"}


# ==================== NORMALIZAÇÃO ====================


def remove_accents(text: str) -> str:
    """Remove acentos usando NFKD."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Aplica normalização determinística completa.

    1. lower()
    2. remover acentos
    3. normalizar espaços
    4. substituir separadores por tokens
    5. normalizar conectores de lista
    """
    # 1. Lowercase
    result = text.lower()

    # 2. Remover acentos
    result = remove_accents(result)

    # 3. Normalizar espaços (múltiplos -> um)
    result = re.sub(r"\s+", " ", result)

    # 4. Substituir separadores por tokens
    # ; | \n -> SEP_ENTITY
    result = re.sub(r"[;\|\n]+", SEP_ENTITY, result)
    # : -> SEP_FIELDS (mas não se estiver dentro de parênteses)
    # Fazemos isso depois do parse para não quebrar "data/hora"

    # 5. Normalizar conectores de lista
    # ", e " -> ", "
    result = re.sub(r",\s+e\s+", ", ", result)
    # " e " no meio de listas -> ", " (cuidado para não pegar "cadastro de X e Y")
    # Isso será tratado no parse de fields

    return result.strip()


def singularize(word: str) -> str:
    """Singularização determinística simples."""
    word = word.strip().lower()

    # Verificar exceções primeiro
    if word in SINGULAR_EXCEPTIONS:
        return SINGULAR_EXCEPTIONS[word]

    # Regras de singularização PT-BR
    if word.endswith("oes"):
        return word[:-3] + "ao"
    if word.endswith("aes"):
        return word[:-3] + "ao"
    if word.endswith("eis"):
        return word[:-3] + "el"
    if word.endswith("is") and len(word) > 3:
        # animais -> animal, mas não "pais"
        if not word.endswith("ais"):
            return word[:-2] + "l"
    if word.endswith("res") and len(word) > 4:
        # tutores -> tutor
        return word[:-2]
    if word.endswith("es") and len(word) > 3:
        # clientes -> cliente
        return word[:-1]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return word[:-1]

    return word


def to_snake_case(text: str) -> str:
    """Converte texto para snake_case."""
    # Remover acentos primeiro
    text = remove_accents(text.lower())
    # Substituir espaços e hífens por underscore
    text = re.sub(r"[\s\-]+", "_", text)
    # Remover caracteres não alfanuméricos (exceto underscore)
    text = re.sub(r"[^a-z0-9_]", "", text)
    # Remover underscores duplicados
    text = re.sub(r"_+", "_", text)
    # Remover underscores no início e fim
    return text.strip("_")


def remove_articles(name: str) -> str:
    """Remove artigos do início do nome."""
    words = name.split()
    if words and words[0] in ARTICLES:
        return " ".join(words[1:])
    return name


def clean_field_name(name: str) -> str:
    """Limpa nome de campo removendo stopwords internas."""
    words = name.split("_")
    cleaned = [w for w in words if w and w not in FIELD_STOPWORDS]
    return "_".join(cleaned) if cleaned else name


# ==================== TIPAGEM DE CAMPOS ====================


def infer_field_type(field_name: str) -> Tuple[str, bool, bool]:
    """Infere tipo, required e unique de um campo pelo nome.

    Returns:
        Tuple de (type, required, unique)
    """
    name = field_name.lower()

    # Campos com tipos específicos
    if "data" in name or "date" in name:
        return "date", True, False
    if "hora" in name or "time" in name:
        return "time", True, False
    if "email" in name:
        return "string", True, True
    if "telefone" in name or "celular" in name or "whatsapp" in name or "phone" in name:
        return "string", False, False
    if name == "cpf":
        return "string", True, True
    if name == "cnpj":
        return "string", True, True
    if name == "crmv":
        return "string", True, True
    if "valor" in name or "preco" in name or "total" in name:
        return "decimal", True, False
    if "peso" in name:
        return "decimal", False, False
    if "quantidade" in name or "qtd" in name:
        return "integer", True, False
    if name == "ativo":
        return "boolean", True, False

    # Default: string, required, não unique
    return "string", True, False


# ==================== PARSING ====================


class EntityDeclaration:
    """Representa uma declaração de entidade parseada."""

    def __init__(self, name: str, fields: List[str], source_form: str):
        self.name = name
        self.fields = fields
        self.source_form = source_form  # "A", "B", "C", "D"
        self.warnings: List[str] = []


def parse_field_list(field_text: str) -> List[str]:
    """Parseia lista de campos.

    Trata:
    - Splitting por vírgula
    - "data/hora" -> ["data", "hora"]
    - Normalização para snake_case
    - Remoção de stopwords
    - Deduplicação mantendo ordem
    """
    fields: List[str] = []
    seen: Set[str] = set()

    # Normalizar " e " final para vírgula
    field_text = re.sub(r"\s+e\s+(?=[^,]*$)", ", ", field_text)

    # Split por vírgula
    parts = [p.strip() for p in field_text.split(",")]

    for part in parts:
        if not part:
            continue

        # Remover parênteses internos (obs)
        part = re.sub(r"\([^)]*\)", "", part).strip()

        # Ignorar tudo após "=" (não suportado)
        if "=" in part:
            part = part.split("=")[0].strip()

        # Tratar "data/hora" -> ["data", "hora"]
        if "/" in part:
            subfields = [s.strip() for s in part.split("/")]
            for sf in subfields:
                if sf:
                    normalized = clean_field_name(to_snake_case(sf))
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        fields.append(normalized)
        else:
            normalized = clean_field_name(to_snake_case(part))
            if normalized and normalized not in seen:
                seen.add(normalized)
                fields.append(normalized)

    return fields


def parse_form_a(text: str) -> List[EntityDeclaration]:
    """Forma A: entity(fields) - múltiplos matches via regex global.

    Ex.: tutores (nome, cpf, telefone); pets (nome, especie, raca)
    """
    entities: List[EntityDeclaration] = []

    # Regex para capturar "entity_name (field_list)"
    # Aceita entity_name com letras, números, espaços e hífens
    pattern = r"([a-z][a-z0-9\s\-]*?)\s*\(([^)]+)\)"

    for match in re.finditer(pattern, text):
        raw_name = match.group(1).strip()
        raw_fields = match.group(2).strip()

        # Limpar nome da entidade
        name = remove_articles(raw_name)
        name = singularize(name)
        name = to_snake_case(name)

        if not name or len(name) < 2:
            continue

        # Parsear campos
        fields = parse_field_list(raw_fields)

        entities.append(EntityDeclaration(name, fields, "A"))

    return entities


def parse_form_b(text: str) -> List[EntityDeclaration]:
    """Forma B: "cadastro/controle/gestao de X com A, B, C"

    Ex.: cadastro de empresas com nome, cnpj e endereco
    """
    entities: List[EntityDeclaration] = []

    # Padrões aceitos
    patterns = [
        r"(?:cadastro|cadastrar|sistema\s+de\s+cadastro|controle|gestao|gerenciamento)\s+de\s+(\w+)\s+com\s+(.+?)(?=" + SEP_ENTITY + r"|$)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            raw_name = match.group(1).strip()
            raw_fields = match.group(2).strip()

            name = singularize(raw_name)
            name = to_snake_case(name)

            if not name or len(name) < 2:
                continue

            fields = parse_field_list(raw_fields)
            entities.append(EntityDeclaration(name, fields, "B"))

    return entities


def parse_form_c(text: str) -> List[EntityDeclaration]:
    """Forma C: "X: A, B, C"

    Ex.: tutor: nome, cpf, telefone
    """
    entities: List[EntityDeclaration] = []

    # Substituir : por SEP_FIELDS para parsing
    text_with_sep = text.replace(":", SEP_FIELDS)

    # Padrão: entity_name SEP_FIELDS field_list
    pattern = r"([a-z][a-z0-9\s\-]*?)\s*" + SEP_FIELDS + r"\s*([^" + SEP_ENTITY + r"]+)"

    for match in re.finditer(pattern, text_with_sep):
        raw_name = match.group(1).strip()
        raw_fields = match.group(2).strip()

        # Ignorar se parece ser hora (ex: "10:30")
        if raw_name.isdigit():
            continue

        name = remove_articles(raw_name)
        name = singularize(name)
        name = to_snake_case(name)

        if not name or len(name) < 2:
            continue

        fields = parse_field_list(raw_fields)
        entities.append(EntityDeclaration(name, fields, "C"))

    return entities


def parse_form_d(text: str) -> Tuple[List[EntityDeclaration], List[str]]:
    """Forma D: Lista apenas de entidades (campos vazios + warning).

    Ex.: quero cadastrar tutor e pet e veterinario
    Ex.: sistema de produtos
    """
    entities: List[EntityDeclaration] = []
    warnings: List[str] = []

    # Padrões que indicam lista de entidades
    patterns = [
        # "cadastrar/criar/gerenciar X e Y"
        r"(?:cadastrar|criar|gerenciar|controlar)\s+(.+?)(?=" + SEP_ENTITY + r"|$)",
        # "sistema de X" ou "cadastro de X" (palavra simples, sem "com")
        r"(?:sistema|cadastro|controle|gestao|gerenciamento)\s+de\s+(\w+)(?:\s|$|" + SEP_ENTITY + r")",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            entity_list = match.group(1).strip()

            # Split por "e" ou ","
            parts = re.split(r"\s+e\s+|,\s*", entity_list)

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Verificar se já foi capturado por outra forma (tem parênteses)
                if "(" in part:
                    continue

                # Ignorar se parece ser parte de "com campos"
                if part.startswith("com "):
                    continue

                # Ignorar palavras compostas com "de" no meio (ex: "cadastro de empresas")
                if " de " in part:
                    continue

                name = remove_articles(part)
                name = singularize(name)
                name = to_snake_case(name)

                # NUNCA criar entidade a partir de FIELD_ONLY_WORDS ou SYSTEM_KEYWORDS
                name_normalized = remove_accents(name)
                if name in FIELD_ONLY_WORDS or name_normalized in FIELD_ONLY_WORDS:
                    continue
                if name in SYSTEM_KEYWORDS or name_normalized in SYSTEM_KEYWORDS:
                    continue

                if name and len(name) >= 2:
                    decl = EntityDeclaration(name, [], "D")
                    decl.warnings.append(f"fields_missing_for_entity:{name}")
                    entities.append(decl)
                    warnings.append(f"fields_missing_for_entity:{name}")

    return entities, warnings


def parse_entities(text: str) -> Tuple[List[EntityDeclaration], List[str]]:
    """Parseia texto e extrai todas as entidades.

    Aplica formas A, B, C, D em ordem, evitando duplicatas.
    """
    # Normalizar texto
    normalized = normalize_text(text)

    all_entities: List[EntityDeclaration] = []
    all_warnings: List[str] = []
    seen_names: Set[str] = set()

    # Split por SEP_ENTITY para processar blocos
    blocks = normalized.split(SEP_ENTITY)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Tentar Forma A primeiro (mais específica)
        form_a = parse_form_a(block)
        for decl in form_a:
            if decl.name not in seen_names:
                seen_names.add(decl.name)
                all_entities.append(decl)

        # Se não encontrou nada com Forma A, tentar B
        if not form_a:
            form_b = parse_form_b(block)
            for decl in form_b:
                if decl.name not in seen_names:
                    seen_names.add(decl.name)
                    all_entities.append(decl)

            # Se não encontrou nada com A ou B, tentar C
            if not form_b:
                form_c = parse_form_c(block)
                for decl in form_c:
                    if decl.name not in seen_names:
                        seen_names.add(decl.name)
                        all_entities.append(decl)

    # Forma D: aplicar no texto completo para pegar entidades soltas
    form_d, warnings_d = parse_form_d(normalized)
    for decl in form_d:
        if decl.name not in seen_names:
            seen_names.add(decl.name)
            all_entities.append(decl)
    all_warnings.extend(warnings_d)

    return all_entities, all_warnings


# ==================== PARSING DE REGRAS v2 ====================


class RuleDeclaration:
    """Representa uma regra parseada."""

    def __init__(
        self,
        rule_type: str,
        entity_a: str,
        entity_b: Optional[str] = None,
        raw_text: str = "",
    ):
        self.rule_type = rule_type
        self.entity_a = entity_a
        self.entity_b = entity_b
        self.raw_text = raw_text

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        result = {
            "type": self.rule_type,
            "entity": self.entity_a,
        }
        if self.entity_b:
            result["target_entity"] = self.entity_b
        if self.raw_text:
            result["raw_text"] = self.raw_text
        return result


class WorkflowDeclaration:
    """Representa um workflow/conversão parseado."""

    def __init__(
        self,
        source_entity: str,
        target_entity: str,
        action: str = "convert",
    ):
        self.source_entity = source_entity
        self.target_entity = target_entity
        self.action = action

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "source": self.source_entity,
            "target": self.target_entity,
            "action": self.action,
            "endpoint": f"/api/{self.source_entity}/{{id}}/convert-to-{self.target_entity}",
        }


def extract_rules_block(text: str) -> Tuple[str, str]:
    """Extrai bloco de regras do texto.

    Procura por "Regras:" ou "regras:" e retorna o texto antes e depois.

    Returns:
        Tuple de (texto_entidades, texto_regras)
    """
    # Normalizar case
    lower_text = text.lower()

    # Procurar por variações de "Regras:"
    regras_markers = ["regras:", "regras :", "rules:", "rules :"]

    for marker in regras_markers:
        if marker in lower_text:
            idx = lower_text.index(marker)
            entities_text = text[:idx].strip()
            rules_text = text[idx + len(marker):].strip()
            return entities_text, rules_text

    # Se não encontrou bloco de regras, retornar texto original e vazio
    return text, ""


def parse_rules(rules_text: str, entity_names: Set[str]) -> List[RuleDeclaration]:
    """Parseia regras do bloco de regras.

    Args:
        rules_text: Texto do bloco de regras
        entity_names: Nomes de entidades conhecidas para validação

    Returns:
        Lista de RuleDeclaration
    """
    rules: List[RuleDeclaration] = []
    seen_rules: Set[Tuple[str, str, Optional[str]]] = set()

    if not rules_text:
        return rules

    # Normalizar texto
    normalized = normalize_text(rules_text)

    # Tentar cada padrão
    for pattern, rule_type in RULE_PATTERNS:
        for match in re.finditer(pattern, normalized):
            entity_a = singularize(match.group(1))
            entity_a = to_snake_case(entity_a)

            entity_b = None
            if match.lastindex >= 2:
                entity_b = singularize(match.group(2))
                entity_b = to_snake_case(entity_b)

            # Verificar se entidades existem (opcional, apenas warning)
            rule_key = (rule_type, entity_a, entity_b)
            if rule_key not in seen_rules:
                seen_rules.add(rule_key)
                rules.append(RuleDeclaration(
                    rule_type=RULE_TYPES.get(rule_type, rule_type.lower()),
                    entity_a=entity_a,
                    entity_b=entity_b,
                    raw_text=match.group(0),
                ))

    return rules


def extract_workflows_from_rules(
    rules: List[RuleDeclaration],
) -> List[WorkflowDeclaration]:
    """Extrai workflows de regras de conversão.

    Args:
        rules: Lista de RuleDeclaration

    Returns:
        Lista de WorkflowDeclaration
    """
    workflows: List[WorkflowDeclaration] = []

    for rule in rules:
        if rule.rule_type == "conversion" and rule.entity_b:
            workflows.append(WorkflowDeclaration(
                source_entity=rule.entity_a,
                target_entity=rule.entity_b,
                action="convert",
            ))

    return workflows


# ==================== FK OPCIONAL v2 ====================


def is_optional_fk(field_text: str) -> bool:
    """Verifica se campo é FK opcional.

    Ex.: "veterinario opcional" -> True
    """
    lower_text = field_text.lower()
    lower_text = remove_accents(lower_text)

    for marker in OPTIONAL_FK_MARKERS:
        if marker in lower_text:
            return True

    return False


def parse_field_with_optionality(field_text: str) -> Tuple[str, bool]:
    """Parseia campo extraindo optionalidade.

    Ex.: "veterinario opcional" -> ("veterinario", True)
    Ex.: "tutor" -> ("tutor", False)

    Returns:
        Tuple de (nome_campo, is_optional)
    """
    lower_text = field_text.lower()
    lower_text = remove_accents(lower_text)

    is_optional = False

    # Verificar marcadores de opcionalidade
    for marker in OPTIONAL_FK_MARKERS:
        if marker in lower_text:
            is_optional = True
            # Remover marcador do nome
            lower_text = lower_text.replace(marker, "").strip()
            break

    # Limpar e retornar
    clean_name = to_snake_case(lower_text.strip())
    return clean_name, is_optional


# ==================== RELAÇÕES ====================


def extract_relations_from_fields(
    entities: List[EntityDeclaration],
) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]], Dict[str, Dict[str, bool]]]:
    """Extrai relações quando campo tem nome de outra entidade.

    Ex.: pet tem campo "tutor" -> cria tutor_id + relation
    Ex.: agendamento tem campo "veterinario opcional" -> cria veterinario_id (nullable) + relation

    Returns:
        Tuple de (relations, updated_fields_by_entity, optional_fields_map)
        optional_fields_map: {entity_name: {field_name: is_optional}}
    """
    relations: List[Dict[str, Any]] = []
    entity_names = {e.name for e in entities}
    updated_fields: Dict[str, List[str]] = {}
    optional_fields: Dict[str, Dict[str, bool]] = {}

    for entity in entities:
        new_fields: List[str] = []
        entity_optional_fields: Dict[str, bool] = {}

        for field in entity.fields:
            # Verificar opcionalidade
            field_name, is_optional = parse_field_with_optionality(field)

            # Verificar se campo é nome de outra entidade
            field_singular = singularize(field_name)

            if field_singular in entity_names and field_singular != entity.name:
                # Campo é referência a outra entidade
                # Criar relation e substituir por <entity>_id
                fk_field = f"{field_singular}_id"
                new_fields.append(fk_field)
                entity_optional_fields[fk_field] = is_optional

                relations.append({
                    "from": entity.name,
                    "to": field_singular,
                    "type": "many_to_one",
                    "field": fk_field,
                    "optional": is_optional,
                })
            else:
                new_fields.append(field_name)
                if is_optional:
                    entity_optional_fields[field_name] = is_optional

        updated_fields[entity.name] = new_fields
        optional_fields[entity.name] = entity_optional_fields

    return relations, updated_fields, optional_fields


def extract_relations_from_text(
    text: str, entity_names: Set[str]
) -> List[Dict[str, Any]]:
    """Extrai relações de padrões textuais.

    Ex.: "pet pertence a tutor" -> relation
    """
    relations: List[Dict[str, Any]] = []
    normalized = normalize_text(text)

    for pattern, rel_type in RELATION_PATTERNS:
        for match in re.finditer(pattern, normalized):
            entity_a = singularize(match.group(1))
            entity_b = singularize(match.group(2))

            # Só criar se ambas existem
            if entity_a in entity_names and entity_b in entity_names:
                if rel_type == "one_to_many":
                    # "X tem Y" significa Y pertence a X
                    relations.append({
                        "from": entity_b,
                        "to": entity_a,
                        "type": "many_to_one",
                        "field": f"{entity_a}_id",
                    })
                else:
                    relations.append({
                        "from": entity_a,
                        "to": entity_b,
                        "type": rel_type,
                        "field": f"{entity_b}_id",
                    })

    return relations


# ==================== GERAÇÃO DE ESTRUTURAS ====================


def build_field_structure(
    field_name: str,
    is_fk: bool = False,
    is_optional: bool = False,
) -> Dict[str, Any]:
    """Constrói estrutura de campo para SRS/IR.

    Args:
        field_name: Nome do campo
        is_fk: Se é FK (foreign key)
        is_optional: Se o campo é opcional (nullable)
    """
    if is_fk or field_name.endswith("_id"):
        return {
            "name": field_name,
            "type": "uuid",
            "required": not is_optional,
            "unique": False,
            "nullable": is_optional,
        }

    field_type, required, unique = infer_field_type(field_name)

    # Se marcado como opcional, override required
    if is_optional:
        required = False

    result = {
        "name": field_name,
        "type": field_type,
        "required": required,
    }

    if unique:
        result["unique"] = True

    if is_optional:
        result["nullable"] = True

    return result


def build_data_requirements(
    entities: List[EntityDeclaration],
    updated_fields: Dict[str, List[str]],
    optional_fields: Dict[str, Dict[str, bool]],
    original_text: str,
) -> List[Dict[str, Any]]:
    """Constrói data_requirements para SRS.

    Args:
        entities: Lista de entidades parseadas
        updated_fields: Campos atualizados por entidade
        optional_fields: Mapa de campos opcionais por entidade
        original_text: Texto original de entrada
    """
    data_reqs: List[Dict[str, Any]] = []

    for entity in entities:
        fields = updated_fields.get(entity.name, entity.fields)
        entity_optional = optional_fields.get(entity.name, {})

        # Se não tem campos (Forma D), verificar se "nome" aparece no texto
        if not fields:
            # Não criar campo "nome" automaticamente
            # Apenas id será adicionado pelo DomainModeler
            field_structs = []
        else:
            field_structs = [
                build_field_structure(
                    f,
                    is_fk=f.endswith("_id"),
                    is_optional=entity_optional.get(f, False),
                )
                for f in fields
            ]

        data_reqs.append({
            "entity": entity.name,
            "fields": field_structs,
        })

    return data_reqs


# ==================== CLASSE PRINCIPAL ====================


class RequirementsAnalyst:
    """Analisa e extrai requisitos de entrada usando mini-gramática determinística.

    Implementa 4 formas de parsing (A, B, C, D) para extrair:
    - Entidades com campos
    - Relações entre entidades
    - Requisitos funcionais básicos
    """

    def __init__(
        self,
        max_questions_per_round: int = 7,
        llm_enabled: bool = False,
    ) -> None:
        self.max_questions_per_round = max_questions_per_round
        self.llm_enabled = llm_enabled

    def _extract_summary(self, text: str) -> str:
        """Extrai summary simples do texto."""
        first_sentence = text.split(".")[0] if "." in text else text
        summary = first_sentence[:200].strip()
        if len(first_sentence) > 200:
            summary += "..."
        return summary if summary else "Sistema a ser especificado"

    def _generate_requirements(
        self, entities: List[EntityDeclaration]
    ) -> List[Dict[str, Any]]:
        """Gera requisitos funcionais CRUD para cada entidade."""
        requirements: List[Dict[str, Any]] = []
        req_count = 0

        for entity in entities:
            # CRUD básico para cada entidade
            operations = [
                ("cadastrar", "high"),
                ("listar", "medium"),
                ("visualizar", "medium"),
                ("editar", "medium"),
                ("excluir", "low"),
            ]

            for op, priority in operations:
                req_count += 1
                requirements.append({
                    "id": f"FR-{req_count:03d}",
                    "description": f"O sistema deve permitir {op} {entity.name}",
                    "priority": priority,
                    "type": "functional",
                })

        return requirements

    def _generate_open_questions(self, text: str) -> List[str]:
        """Gera perguntas abertas baseadas no que falta no texto."""
        questions = []
        text_lower = text.lower()

        has_auth = any(
            w in text_lower
            for w in ["login", "autenticação", "autenticacao", "senha", "auth"]
        )
        has_profiles = any(
            w in text_lower
            for w in ["perfil", "admin", "usuário", "usuario", "papel", "role"]
        )

        if not has_auth:
            questions.append(DEFAULT_OPEN_QUESTIONS[0])
        if not has_profiles:
            questions.append(DEFAULT_OPEN_QUESTIONS[1])

        # Adicionar perguntas padrão se lista pequena
        while len(questions) < 3:
            for q in DEFAULT_OPEN_QUESTIONS[2:]:
                if q not in questions:
                    questions.append(q)
                    break
            else:
                break

        return questions

    def analyze(self, normalized_input: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa entrada e extrai requisitos.

        Args:
            normalized_input: Resultado do Normalizer

        Returns:
            Dicionário com análise
        """
        text = normalized_input.get("normalized", "")

        # Parsear entidades
        entities, warnings = parse_entities(text)

        return {
            "summary": self._extract_summary(text),
            "actors": [
                {
                    "id": "admin",
                    "name": "Administrador",
                    "description": "Usuário administrador do sistema",
                }
            ],
            "entities": [e.name for e in entities],
            "requirements": self._generate_requirements(entities),
            "open_questions": self._generate_open_questions(text),
            "warnings": warnings,
            "mode": "MINIGRAMMAR",
        }

    def generate_srs(
        self,
        normalized_input: Dict[str, Any],
        project_title: str = "Sistema",
    ) -> Dict[str, Any]:
        """Gera documento SRS compatível com schema.

        Args:
            normalized_input: Resultado do Normalizer
            project_title: Título do projeto

        Returns:
            Documento SRS
        """
        text = normalized_input.get("normalized", "")

        # V2: Extrair bloco de regras separadamente
        entities_text, rules_text = extract_rules_block(text)

        # Parsear entidades (do texto de entidades)
        entities, warnings = parse_entities(entities_text)

        # Extrair relações de campos (com suporte a FK opcional)
        relations_from_fields, updated_fields, optional_fields = extract_relations_from_fields(
            entities
        )

        # Extrair relações de texto
        entity_names = {e.name for e in entities}
        relations_from_text = extract_relations_from_text(entities_text, entity_names)

        # Combinar relações (sem duplicatas)
        all_relations = relations_from_fields.copy()
        seen_relations = {
            (r["from"], r["to"], r["type"]) for r in all_relations
        }
        for rel in relations_from_text:
            key = (rel["from"], rel["to"], rel["type"])
            if key not in seen_relations:
                seen_relations.add(key)
                all_relations.append(rel)

        # V2: Parsear regras
        rules = parse_rules(rules_text, entity_names)

        # V2: Extrair workflows de regras de conversão
        workflows = extract_workflows_from_rules(rules)

        # Construir data_requirements
        data_requirements = build_data_requirements(
            entities, updated_fields, optional_fields, entities_text
        )

        # Gerar requisitos
        requirements = self._generate_requirements(entities)

        # V2: Adicionar requisitos para workflows
        for workflow in workflows:
            requirements.append({
                "id": f"FR-WF-{len(requirements)+1:03d}",
                "description": f"O sistema deve permitir converter {workflow.source_entity} em {workflow.target_entity}",
                "priority": "medium",
                "type": "functional",
            })

        srs = {
            "id": f"srs-{uuid.uuid4().hex[:8]}",
            "title": project_title,
            "version": "1.0.0",
            "requirements": requirements,
            "meta": {
                "project_name": project_title,
            },
            "data_requirements": data_requirements,
            "relations": all_relations,
            "business_rules": [r.to_dict() for r in rules],  # V2: regras
            "workflows": [w.to_dict() for w in workflows],   # V2: workflows
            "non_functional_requirements": {
                "security": {
                    "auth_required": True,
                    "audit_log_required": False,
                }
            },
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "language": normalized_input.get("language", "pt-BR"),
                "actors": [
                    {
                        "id": "admin",
                        "name": "Administrador",
                        "description": "Usuário administrador do sistema",
                    }
                ],
                "summary": self._extract_summary(entities_text),
                "open_questions": self._generate_open_questions(entities_text),
                "warnings": warnings,
                "generation_mode": "MINIGRAMMAR_V2",
            },
        }

        return srs

    def generate_clarification_questions(
        self, analysis: Dict[str, Any]
    ) -> List[str]:
        """Gera perguntas de clarificação."""
        questions = analysis.get("open_questions", [])
        return questions[: self.max_questions_per_round]


# ==================== FUNÇÕES DE CONVENIÊNCIA ====================


def parse_requirements(text: str) -> Dict[str, Any]:
    """Função de conveniência para parsear requisitos.

    Args:
        text: Texto de entrada

    Returns:
        Dicionário com entities, relations, rules, workflows, warnings
    """
    # V2: Extrair bloco de regras
    entities_text, rules_text = extract_rules_block(text)

    entities, warnings = parse_entities(entities_text)

    # Extrair relações (com suporte a FK opcional)
    relations, updated_fields, optional_fields = extract_relations_from_fields(entities)
    entity_names = {e.name for e in entities}
    text_relations = extract_relations_from_text(entities_text, entity_names)

    # Combinar
    all_relations = relations + [
        r for r in text_relations
        if (r["from"], r["to"], r["type"]) not in {
            (rel["from"], rel["to"], rel["type"]) for rel in relations
        }
    ]

    # V2: Parsear regras
    rules = parse_rules(rules_text, entity_names)

    # V2: Extrair workflows
    workflows = extract_workflows_from_rules(rules)

    return {
        "entities": [
            {
                "name": e.name,
                "fields": updated_fields.get(e.name, e.fields),
                "optional_fields": optional_fields.get(e.name, {}),
                "source_form": e.source_form,
            }
            for e in entities
        ],
        "relations": all_relations,
        "rules": [r.to_dict() for r in rules],
        "workflows": [w.to_dict() for w in workflows],
        "warnings": warnings,
    }
