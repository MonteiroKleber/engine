"""IDL Draft v1 - Linguagem intermediaria pre-canonica.

IDL Draft e uma estrutura permissiva usada para capturar entradas humanas
(texto solto ou wizard) antes da compilacao para IDL v1 canonico.

REGRAS FUNDAMENTAIS:
- Draft NUNCA e hashado
- Draft NUNCA passa pelo Contract Gate
- Draft NUNCA entra no motor
- Draft pode conter "unknown" e campos incompletos
- Draft pode conter assumptions e open_questions

Schema Version: idl_draft.v1
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


# ============================================
# SCHEMA VERSION
# ============================================

IDL_DRAFT_SCHEMA_VERSION = "idl_draft.v1"


# ============================================
# SPECIAL VALUES
# ============================================

UNKNOWN = "unknown"
TBD = "TBD"

# Valores que indicam campo nao resolvido
UNRESOLVED_VALUES = {UNKNOWN, TBD, "tbd", "Unknown", "UNKNOWN"}


def is_unknown(value: Any) -> bool:
    """Verifica se valor e unknown/TBD."""
    if value is None:
        return True
    if isinstance(value, str):
        return value in UNRESOLVED_VALUES or value.strip() == ""
    return False


# ============================================
# ENUMS
# ============================================

class DraftSource(str, Enum):
    """Origem do Draft."""
    NATURAL_TEXT = "natural_text"
    WIZARD = "wizard"
    IMPORTED = "imported"


class DraftIntegrationType(str, Enum):
    """Tipos de integracao no Draft."""
    API = "api"
    DB = "db"
    QUEUE = "queue"
    UNKNOWN = "unknown"


# ============================================
# DATA CLASSES - DRAFT STRUCTURES
# ============================================

@dataclass
class DraftActorField:
    """Campo de permissao de ator no Draft."""
    value: str


@dataclass
class DraftActor:
    """Ator no Draft - pode ter campos unknown."""
    id: str
    role: str = UNKNOWN
    permissions: List[str] = field(default_factory=list)

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        return is_unknown(self.role)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "id": self.id,
            "role": self.role,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftActor":
        """Cria a partir de dicionario."""
        return cls(
            id=data.get("id", ""),
            role=data.get("role", UNKNOWN),
            permissions=data.get("permissions", []),
        )


@dataclass
class DraftField:
    """Campo de entidade no Draft - pode ter tipo unknown."""
    name: str
    type: str = UNKNOWN
    required: Union[bool, str] = UNKNOWN  # Pode ser bool ou "unknown"

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        return is_unknown(self.type) or is_unknown(self.required)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftField":
        """Cria a partir de dicionario."""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", UNKNOWN),
            required=data.get("required", UNKNOWN),
        )


@dataclass
class DraftEntity:
    """Entidade no Draft - pode ter campos incompletos."""
    id: str
    fields: List[DraftField] = field(default_factory=list)

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        return any(f.has_unresolved() for f in self.fields)

    def get_unresolved_fields(self) -> List[str]:
        """Retorna lista de campos nao resolvidos."""
        unresolved = []
        for f in self.fields:
            if is_unknown(f.type):
                unresolved.append(f"fields.{f.name}.type")
            if is_unknown(f.required):
                unresolved.append(f"fields.{f.name}.required")
        return unresolved

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "id": self.id,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftEntity":
        """Cria a partir de dicionario."""
        fields = [DraftField.from_dict(f) for f in data.get("fields", [])]
        return cls(
            id=data.get("id", ""),
            fields=fields,
        )


@dataclass
class DraftFlowStep:
    """Passo de fluxo no Draft."""
    step: int
    action: str

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "step": self.step,
            "action": self.action,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftFlowStep":
        """Cria a partir de dicionario."""
        return cls(
            step=data.get("step", 0),
            action=data.get("action", ""),
        )


@dataclass
class DraftUseCase:
    """Caso de uso no Draft."""
    id: str
    actor: str = UNKNOWN
    flow: List[DraftFlowStep] = field(default_factory=list)

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        return is_unknown(self.actor)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "id": self.id,
            "actor": self.actor,
            "flow": [s.to_dict() for s in self.flow],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftUseCase":
        """Cria a partir de dicionario."""
        flow = [DraftFlowStep.from_dict(s) for s in data.get("flow", [])]
        return cls(
            id=data.get("id", ""),
            actor=data.get("actor", UNKNOWN),
            flow=flow,
        )


@dataclass
class DraftIntegration:
    """Integracao no Draft."""
    system: str
    type: str = UNKNOWN

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        return is_unknown(self.type)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "system": self.system,
            "type": self.type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftIntegration":
        """Cria a partir de dicionario."""
        return cls(
            system=data.get("system", ""),
            type=data.get("type", UNKNOWN),
        )


@dataclass
class DraftNonFunctional:
    """Requisitos nao-funcionais no Draft."""
    performance: str = UNKNOWN
    security: str = UNKNOWN

    def has_unresolved(self) -> bool:
        """Verifica se tem campos nao resolvidos."""
        # NFRs podem ser unknown no draft - nao bloqueia compilacao
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "performance": self.performance,
            "security": self.security,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftNonFunctional":
        """Cria a partir de dicionario."""
        return cls(
            performance=data.get("performance", UNKNOWN),
            security=data.get("security", UNKNOWN),
        )


# ============================================
# IDL DRAFT DOCUMENT
# ============================================

@dataclass
class IDLDraftV1:
    """Documento IDL Draft v1 completo.

    Este documento representa uma especificacao pre-canonica que pode
    conter campos incompletos, assumptions e open_questions.

    NUNCA deve ser hashado ou passar pelo Contract Gate.
    """
    project: str
    source: DraftSource = DraftSource.NATURAL_TEXT
    actors: List[DraftActor] = field(default_factory=list)
    entities: List[DraftEntity] = field(default_factory=list)
    use_cases: List[DraftUseCase] = field(default_factory=list)
    integrations: List[DraftIntegration] = field(default_factory=list)
    non_functional: Optional[DraftNonFunctional] = None
    assumptions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def has_open_questions(self) -> bool:
        """Verifica se tem open_questions."""
        return len(self.open_questions) > 0

    def has_assumptions(self) -> bool:
        """Verifica se tem assumptions."""
        return len(self.assumptions) > 0

    def get_all_unresolved(self) -> List[str]:
        """Retorna todas as localizacoes de campos nao resolvidos."""
        unresolved = []

        # Actors
        for i, actor in enumerate(self.actors):
            if is_unknown(actor.role):
                unresolved.append(f"actors.{actor.id}.role")

        # Entities
        for entity in self.entities:
            for field_path in entity.get_unresolved_fields():
                unresolved.append(f"entities.{entity.id}.{field_path}")

        # Use Cases
        for uc in self.use_cases:
            if is_unknown(uc.actor):
                unresolved.append(f"use_cases.{uc.id}.actor")

        # Integrations
        for integ in self.integrations:
            if is_unknown(integ.type):
                unresolved.append(f"integrations.{integ.system}.type")

        return unresolved

    def is_compileable(self) -> bool:
        """Verifica se o Draft pode ser compilado para IDL v1.

        Retorna False se:
        - Existem open_questions nao resolvidas
        - Existem campos unknown em locais obrigatorios
        """
        if self.has_open_questions():
            return False

        if len(self.get_all_unresolved()) > 0:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        result: Dict[str, Any] = {
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "source": self.source.value,
            "project": self.project,
            "actors": [a.to_dict() for a in self.actors],
            "entities": [e.to_dict() for e in self.entities],
            "use_cases": [u.to_dict() for u in self.use_cases],
            "integrations": [i.to_dict() for i in self.integrations],
        }

        if self.non_functional:
            result["non_functional"] = self.non_functional.to_dict()

        if self.assumptions:
            result["assumptions"] = self.assumptions

        if self.open_questions:
            result["open_questions"] = self.open_questions

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IDLDraftV1":
        """Cria a partir de dicionario."""
        source_str = data.get("source", "natural_text")
        try:
            source = DraftSource(source_str)
        except ValueError:
            source = DraftSource.NATURAL_TEXT

        actors = [DraftActor.from_dict(a) for a in data.get("actors", [])]
        entities = [DraftEntity.from_dict(e) for e in data.get("entities", [])]
        use_cases = [DraftUseCase.from_dict(u) for u in data.get("use_cases", [])]
        integrations = [DraftIntegration.from_dict(i) for i in data.get("integrations", [])]

        nf_data = data.get("non_functional")
        non_functional = DraftNonFunctional.from_dict(nf_data) if nf_data else None

        return cls(
            project=data.get("project", ""),
            source=source,
            actors=actors,
            entities=entities,
            use_cases=use_cases,
            integrations=integrations,
            non_functional=non_functional,
            assumptions=data.get("assumptions", []),
            open_questions=data.get("open_questions", []),
        )
