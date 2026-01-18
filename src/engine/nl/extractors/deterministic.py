"""Deterministic keyword-based extractor."""

import re
from typing import Optional, List, Dict, Set, Tuple, Any, Union

from engine.nl.schemas.sir_v1 import (
    SIRv1,
    Source,
    Segment,
    Extraction,
    Actor,
    Entity,
    Policy,
    RuntimePolicy,
    Workflow,
    WorkflowStep,
)
from engine.nl.canonical import normalize_key, normalize_roles
from .base import BaseExtractor


# =============================================================================
# Runtime Policy v1.1 Constants (must match ISE emit/policies_emit.py)
# =============================================================================
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
})

ALLOWED_PHASES = frozenset({"pre", "post"})

ALLOWED_RULE_TYPES = frozenset({
    "numeric_max",
    "numeric_min",
    "string_max_len",
    "required_field",
    "enum_allowlist",
})

# Regex pattern for POLICY marker extraction
# Format: POLICY: <policy_id> <phase> <endpoint_sig> <rule_type> <field_path> [value] [message]
# Example: POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100
_POLICY_MARKER_PATTERN = re.compile(
    r"POLICY:\s*"
    r"(\S+)\s+"                     # policy_id (no spaces)
    r"(pre|post)\s+"                # phase
    r"(GET|POST|PUT|DELETE|PATCH)\s+"  # HTTP method
    r"(/\S+)\s+"                    # path
    r"(\S+)\s+"                     # rule_type
    r"(\S+)"                        # field_path
    r"(?:\s+(.+))?",                # optional value and message
    re.IGNORECASE
)

# Pattern for dept-prefixed policies
# Format: POLICY[dept_id]: <policy_id> <phase> <endpoint_sig> <rule_type> <field_path> [value]
_DEPT_POLICY_MARKER_PATTERN = re.compile(
    r"POLICY\[(\S+?)\]:\s*"         # dept_id in brackets
    r"(\S+)\s+"                     # policy_id
    r"(pre|post)\s+"                # phase
    r"(GET|POST|PUT|DELETE|PATCH)\s+"  # HTTP method
    r"(/\S+)\s+"                    # path
    r"(\S+)\s+"                     # rule_type
    r"(\S+)"                        # field_path
    r"(?:\s+(.+))?",                # optional value and message
    re.IGNORECASE
)


# Keywords for language detection and extraction
KEYWORDS = {
    "en": {
        "roles": [
            "manager", "analyst", "admin", "administrator", "user",
            "approver", "reviewer", "auditor", "supervisor", "employee",
            "director", "cfo", "ceo", "owner", "viewer",
        ],
        "actions": [
            "approve", "reject", "create", "read", "update", "delete",
            "submit", "review", "sign", "authorize", "validate",
        ],
        "entities": [
            "expense", "invoice", "payment", "order", "request",
            "document", "report", "budget", "transaction", "contract",
        ],
        "policy_indicators": {
            "approval": ["must be approved", "requires approval", "needs approval", "approval required", "approved by", "must approve"],
            "sod": ["cannot approve their own", "self-approval", "segregation", "different person", "another person", "cannot approve your own", "their own"],
            "rbac": ["can only", "must have", "permission", "role", "authorized to"],
            "invariant": ["must be", "cannot exceed", "maximum", "minimum", "limit", "at least", "at most"],
        },
        "workflow_indicators": ["then", "after", "before", "first", "next", "finally", "step"],
    },
    "pt": {
        "roles": [
            "gerente", "analista", "admin", "administrador", "usuario", "usuário",
            "aprovador", "revisor", "auditor", "supervisor", "funcionario", "funcionário",
            "diretor", "cfo", "ceo", "dono", "visualizador",
        ],
        "actions": [
            "aprovar", "rejeitar", "criar", "ler", "atualizar", "deletar", "excluir",
            "submeter", "revisar", "assinar", "autorizar", "validar",
        ],
        "entities": [
            "despesa", "fatura", "pagamento", "pedido", "solicitacao", "solicitação",
            "documento", "relatorio", "relatório", "orcamento", "orçamento", "transacao", "transação", "contrato",
        ],
        "policy_indicators": {
            "approval": ["deve ser aprovado", "requer aprovacao", "requer aprovação", "precisa de aprovacao", "precisa de aprovação", "aprovado por", "devem aprovar", "deve aprovar"],
            "sod": ["nao pode aprovar sua propria", "não pode aprovar sua própria", "auto-aprovacao", "auto-aprovação", "segregacao", "segregação", "pessoa diferente", "outra pessoa", "suas proprias", "suas próprias", "não podem aprovar"],
            "rbac": ["so pode", "só pode", "deve ter", "permissao", "permissão", "papel", "autorizado a"],
            "invariant": ["deve ser", "nao pode exceder", "não pode exceder", "maximo", "máximo", "minimo", "mínimo", "limite", "pelo menos", "no maximo", "no máximo"],
        },
        "workflow_indicators": ["entao", "então", "depois", "antes", "primeiro", "proximo", "próximo", "finalmente", "passo", "etapa"],
    },
}

# Role translations (PT -> EN)
ROLE_TRANSLATIONS = {
    "gerente": "manager",
    "analista": "analyst",
    "administrador": "admin",
    "usuario": "user",
    "usuário": "user",
    "aprovador": "approver",
    "revisor": "reviewer",
    "auditor": "auditor",
    "supervisor": "supervisor",
    "funcionario": "employee",
    "funcionário": "employee",
    "diretor": "director",
    "dono": "owner",
    "visualizador": "viewer",
}

# Entity translations (PT -> EN)
ENTITY_TRANSLATIONS = {
    "despesa": "expense",
    "fatura": "invoice",
    "pagamento": "payment",
    "pedido": "order",
    "solicitacao": "request",
    "solicitação": "request",
    "documento": "document",
    "relatorio": "report",
    "relatório": "report",
    "orcamento": "budget",
    "orçamento": "budget",
    "transacao": "transaction",
    "transação": "transaction",
    "contrato": "contract",
}


class DeterministicExtractor(BaseExtractor):
    """Deterministic keyword-based extractor for NL text."""

    def detect_language(self, text: str) -> str:
        """Detect language based on keyword frequency.

        Args:
            text: Text to analyze.

        Returns:
            Language code ("en" or "pt").
        """
        text_lower = text.lower()

        en_score = 0
        pt_score = 0

        # Check role keywords
        for role in KEYWORDS["en"]["roles"]:
            if role in text_lower:
                en_score += 1
        for role in KEYWORDS["pt"]["roles"]:
            if role in text_lower:
                pt_score += 1

        # Check action keywords
        for action in KEYWORDS["en"]["actions"]:
            if action in text_lower:
                en_score += 1
        for action in KEYWORDS["pt"]["actions"]:
            if action in text_lower:
                pt_score += 1

        # Check entity keywords
        for entity in KEYWORDS["en"]["entities"]:
            if entity in text_lower:
                en_score += 1
        for entity in KEYWORDS["pt"]["entities"]:
            if entity in text_lower:
                pt_score += 1

        # Default to English if tied or no keywords found
        return "pt" if pt_score > en_score else "en"

    def _split_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """Split text into sentences with positions.

        Returns list of (sentence, start, end) tuples.
        """
        sentences = []
        # Split on period, exclamation, question mark, or newline
        pattern = r'[.!?\n]+'
        parts = re.split(pattern, text)

        pos = 0
        for part in parts:
            part = part.strip()
            if part:
                # Find actual position in original text
                start = text.find(part, pos)
                if start == -1:
                    start = pos
                end = start + len(part)
                sentences.append((part, start, end))
                pos = end

        return sentences

    def _extract_roles(self, text: str, language: str) -> Set[str]:
        """Extract roles from text."""
        text_lower = text.lower()
        roles = set()

        for role in KEYWORDS[language]["roles"]:
            if role in text_lower:
                # Translate to English if Portuguese
                if language == "pt" and role in ROLE_TRANSLATIONS:
                    roles.add(ROLE_TRANSLATIONS[role])
                else:
                    roles.add(role)

        return roles

    def _extract_entities(self, text: str, language: str) -> Set[str]:
        """Extract entity types from text."""
        text_lower = text.lower()
        entities = set()

        for entity in KEYWORDS[language]["entities"]:
            if entity in text_lower:
                # Translate to English if Portuguese
                if language == "pt" and entity in ENTITY_TRANSLATIONS:
                    entities.add(ENTITY_TRANSLATIONS[entity])
                else:
                    entities.add(entity)

        return entities

    def _detect_policy_types(self, text: str, language: str) -> Dict[str, List[str]]:
        """Detect policy types and their indicator matches."""
        text_lower = text.lower()
        detected = {}

        for policy_type, indicators in KEYWORDS[language]["policy_indicators"].items():
            matches = []
            for indicator in indicators:
                if indicator in text_lower:
                    matches.append(indicator)
            if matches:
                detected[policy_type] = matches

        return detected

    def _has_workflow_indicators(self, text: str, language: str) -> bool:
        """Check if text contains workflow indicators."""
        text_lower = text.lower()
        for indicator in KEYWORDS[language]["workflow_indicators"]:
            if indicator in text_lower:
                return True
        return False

    def _parse_policy_value(self, raw_value: Optional[str], rule_type: str) -> Tuple[Optional[Union[int, float, str, List[str]]], Optional[str]]:
        """Parse policy value and optional message from raw string.

        Args:
            raw_value: Raw value string (may include value and message).
            rule_type: The rule type to determine value parsing.

        Returns:
            Tuple of (parsed_value, message).
        """
        if not raw_value:
            return None, None

        raw_value = raw_value.strip()
        if not raw_value:
            return None, None

        # For enum_allowlist, value is a comma-separated list possibly followed by message
        if rule_type == "enum_allowlist":
            # Check if there's a quoted message at the end
            parts = raw_value.split('"')
            if len(parts) >= 3:
                # Has quoted message
                value_part = parts[0].strip()
                message = parts[1].strip()
                return [v.strip() for v in value_part.rstrip(',').split(',') if v.strip()], message
            else:
                # No message, whole thing is value list
                return [v.strip() for v in raw_value.split(',') if v.strip()], None

        # For numeric types, try to parse as number
        if rule_type in ("numeric_max", "numeric_min", "string_max_len"):
            # Value may be followed by optional message
            parts = raw_value.split('"')
            if len(parts) >= 3:
                # Has quoted message
                value_str = parts[0].strip()
                message = parts[1].strip()
            else:
                # Check if there's a space-separated message
                value_parts = raw_value.split(maxsplit=1)
                value_str = value_parts[0]
                message = value_parts[1] if len(value_parts) > 1 else None

            try:
                if '.' in value_str:
                    return float(value_str), message
                return int(value_str), message
            except (ValueError, TypeError):
                return None, None

        # For required_field, no value needed
        if rule_type == "required_field":
            # Entire raw_value could be the message
            return None, raw_value if raw_value else None

        return None, None

    def _extract_runtime_policies(self, text: str) -> Tuple[List[RuntimePolicy], Dict[str, List[RuntimePolicy]]]:
        """Extract runtime policies from explicit POLICY markers.

        IMPORTANT: Only extracts policies with explicit POLICY marker.
        Does NOT infer or generate policies from other text.

        Args:
            text: Source text to extract from.

        Returns:
            Tuple of (runtime_policies for single mode, dept_runtime_policies for multi mode).
        """
        runtime_policies: List[RuntimePolicy] = []
        dept_runtime_policies: Dict[str, List[RuntimePolicy]] = {}

        # Find segments containing "POLICY" or "POLICIES" marker
        lines = text.split('\n')
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Check for dept-prefixed policy first
            dept_match = _DEPT_POLICY_MARKER_PATTERN.search(line)
            if dept_match:
                dept_id = dept_match.group(1)
                policy_id = dept_match.group(2)
                phase = dept_match.group(3).lower()
                method = dept_match.group(4).upper()
                path = dept_match.group(5)
                rule_type = dept_match.group(6).lower()
                field_path = dept_match.group(7)
                raw_value = dept_match.group(8)

                endpoint_sig = f"{method} {path}"
                value, message = self._parse_policy_value(raw_value, rule_type)

                policy = RuntimePolicy(
                    policy_id=policy_id,
                    phase=phase,
                    endpoint_sig=endpoint_sig,
                    rule_type=rule_type,
                    field_path=field_path,
                    value=value,
                    message=message,
                    source_segment=f"line-{line_num}",
                )

                if dept_id not in dept_runtime_policies:
                    dept_runtime_policies[dept_id] = []
                dept_runtime_policies[dept_id].append(policy)
                continue

            # Check for single-mode policy
            match = _POLICY_MARKER_PATTERN.search(line)
            if match:
                policy_id = match.group(1)
                phase = match.group(2).lower()
                method = match.group(3).upper()
                path = match.group(4)
                rule_type = match.group(5).lower()
                field_path = match.group(6)
                raw_value = match.group(7)

                endpoint_sig = f"{method} {path}"
                value, message = self._parse_policy_value(raw_value, rule_type)

                policy = RuntimePolicy(
                    policy_id=policy_id,
                    phase=phase,
                    endpoint_sig=endpoint_sig,
                    rule_type=rule_type,
                    field_path=field_path,
                    value=value,
                    message=message,
                    source_segment=f"line-{line_num}",
                )
                runtime_policies.append(policy)

        return runtime_policies, dept_runtime_policies

    def extract(self, text: str, language: Optional[str] = None) -> SIRv1:
        """Extract structured information from text.

        Args:
            text: Source text to extract from.
            language: Optional language hint.

        Returns:
            SIRv1 with extracted entities.
        """
        if not text or not text.strip():
            raise ValueError("Empty input text")

        # Detect language if not provided
        if language is None:
            language = self.detect_language(text)

        if language not in KEYWORDS:
            raise ValueError(f"Unsupported language: {language}")

        # Split into segments (sentences)
        sentence_data = self._split_sentences(text)
        segments = []
        for i, (sentence, start, end) in enumerate(sentence_data):
            segments.append(Segment(
                segment_key=f"seg-{i:03d}",
                text=sentence,
                start_char=start,
                end_char=end,
            ))

        source = Source(language=language, segments=segments)

        # Extract actors (roles)
        all_roles = self._extract_roles(text, language)
        actors = []
        for i, role in enumerate(sorted(all_roles)):
            actors.append(Actor(
                actor_key=f"actor-{normalize_key(role)}",
                name=role.title(),
                roles=normalize_roles([role]),
            ))

        # Extract entities
        all_entities = self._extract_entities(text, language)
        entities = []
        for i, entity_type in enumerate(sorted(all_entities)):
            entities.append(Entity(
                entity_key=f"entity-{normalize_key(entity_type)}",
                name=entity_type.title(),
                entity_type=entity_type,
            ))

        # Detect policy types
        policy_types = self._detect_policy_types(text, language)
        policies = []

        # Create policies based on detected types
        for policy_type, indicators in sorted(policy_types.items()):
            policy_key = f"policy-{policy_type}-001"

            # Determine actor and entity refs
            actor_refs = [a.actor_key for a in actors]
            entity_refs = [e.entity_key for e in entities]

            policies.append(Policy(
                policy_key=policy_key,
                policy_type=policy_type,
                description=f"Detected {policy_type} policy from: {indicators[0]}",
                actor_refs=actor_refs[:2] if actor_refs else [],  # Limit refs
                entity_refs=entity_refs[:1] if entity_refs else [],
                conditions={"indicators": sorted(indicators)},
            ))

        # Create basic workflow if workflow indicators detected
        workflows = []
        if self._has_workflow_indicators(text, language) and entities:
            entity_key = entities[0].entity_key if entities else None
            steps = []

            # Create basic workflow steps based on detected policies
            step_num = 0
            for policy in policies:
                if policy.policy_type == "rbac":
                    steps.append(WorkflowStep(
                        step_key=f"step-{step_num:03d}",
                        action="authorize",
                        entity_ref=entity_key,
                    ))
                    step_num += 1
                elif policy.policy_type == "approval":
                    steps.append(WorkflowStep(
                        step_key=f"step-{step_num:03d}",
                        action="approve",
                        entity_ref=entity_key,
                        actor_ref=policy.actor_refs[0] if policy.actor_refs else None,
                    ))
                    step_num += 1

            if steps:
                workflows.append(Workflow(
                    workflow_key="workflow-main",
                    name="Main Workflow",
                    steps=steps,
                ))

        # Extract runtime policies from explicit POLICY markers
        runtime_policies, dept_runtime_policies = self._extract_runtime_policies(text)

        extraction = Extraction(
            actors=actors,
            entities=entities,
            policies=policies,
            workflows=workflows,
            runtime_policies=runtime_policies,
            dept_runtime_policies=dept_runtime_policies,
        )

        return SIRv1(
            version="1.0",
            source=source,
            extraction=extraction,
        )
