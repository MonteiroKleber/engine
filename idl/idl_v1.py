"""IDL v1 - Institutional Definition Language.

Parser, canonizacao e contrato para linguagem IDL.

Schema Version: idl.v1

Este modulo implementa:
- Parser para linguagem IDL
- Canonizacao deterministica
- Hash SHA256 para integridade
- Contract Gate para validacao
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================
# SCHEMA VERSION
# ============================================

IDL_SCHEMA_VERSION = "idl.v1"


# ============================================
# HASHABLE FIELDS (para Contract Gate)
# ============================================

HASHABLE_FIELDS = [
    "schema_version",
    "system",
    "actors",
    "entities",
    "usecases",
    "integrations",
    "nonfunctional",
]

# Campos volateis (nao entram no hash)
VOLATILE_FIELDS = [
    "content_hash_sha256",
    "timestamp",
    "parser_version",
    "contract_notes",
]


# ============================================
# ENUMS
# ============================================

class ActorType(str, Enum):
    HUMAN = "human"
    SYSTEM = "system"
    EXTERNAL = "external"


class AuthMethod(str, Enum):
    NONE = "none"
    BASIC = "basic"
    TOKEN = "token"
    OAUTH2 = "oauth2"
    CERTIFICATE = "certificate"


class RelationType(str, Enum):
    HAS_ONE = "has_one"
    HAS_MANY = "has_many"
    BELONGS_TO = "belongs_to"
    MANY_TO_MANY = "many_to_many"


class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComplexityLevel(str, Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class IntegrationType(str, Enum):
    REST_API = "rest_api"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    SOAP = "soap"
    MESSAGE_QUEUE = "message_queue"
    WEBHOOK = "webhook"
    DATABASE = "database"
    FILE_SYSTEM = "file_system"


class ProtocolType(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    WS = "ws"
    WSS = "wss"
    AMQP = "amqp"
    MQTT = "mqtt"
    TCP = "tcp"
    UDP = "udp"


class NFRType(str, Enum):
    PERFORMANCE = "performance"
    SECURITY = "security"
    AVAILABILITY = "availability"
    SCALABILITY = "scalability"
    MAINTAINABILITY = "maintainability"
    USABILITY = "usability"
    COMPLIANCE = "compliance"


class PrimitiveType(str, Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATETIME = "datetime"
    UUID = "uuid"
    TEXT = "text"
    DECIMAL = "decimal"


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class SystemDefinition:
    """Definicao do sistema."""
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    domain: str = ""
    owner: str = ""
    contact: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "domain": self.domain,
            "owner": self.owner,
            "contact": self.contact,
        }


@dataclass
class ActorDefinition:
    """Definicao de ator."""
    id: str
    actor_type: ActorType
    name: str
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    authentication: AuthMethod = AuthMethod.NONE

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "actor_type": self.actor_type.value,
            "name": self.name,
            "description": self.description,
            "permissions": sorted(self.permissions),
            "authentication": self.authentication.value,
        }


@dataclass
class FieldDefinition:
    """Definicao de campo de entidade."""
    id: str
    field_type: str
    required: bool = False
    unique: bool = False
    indexed: bool = False
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        result = {
            "id": self.id,
            "field_type": self.field_type,
            "required": self.required,
            "unique": self.unique,
            "indexed": self.indexed,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        if self.pattern is not None:
            result["pattern"] = self.pattern
        return result


@dataclass
class RelationDefinition:
    """Definicao de relacao entre entidades."""
    id: str
    relation_type: RelationType
    target_entity: str
    cascade_delete: bool = False
    nullable: bool = False
    through: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        result = {
            "id": self.id,
            "relation_type": self.relation_type.value,
            "target_entity": self.target_entity,
            "cascade_delete": self.cascade_delete,
            "nullable": self.nullable,
        }
        if self.through is not None:
            result["through"] = self.through
        return result


@dataclass
class ConstraintDefinition:
    """Definicao de constraint de entidade."""
    id: str
    expression: str

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "expression": self.expression,
        }


@dataclass
class IndexDefinition:
    """Definicao de indice de entidade."""
    id: str
    fields: List[str]
    unique: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "fields": self.fields,  # Mantém ordem definida
            "unique": self.unique,
        }


@dataclass
class EntityDefinition:
    """Definicao de entidade."""
    id: str
    fields: List[FieldDefinition] = field(default_factory=list)
    relations: List[RelationDefinition] = field(default_factory=list)
    constraints: List[ConstraintDefinition] = field(default_factory=list)
    indexes: List[IndexDefinition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "fields": [f.to_dict() for f in sorted(self.fields, key=lambda x: x.id)],
            "relations": [r.to_dict() for r in sorted(self.relations, key=lambda x: x.id)],
            "constraints": [c.to_dict() for c in sorted(self.constraints, key=lambda x: x.id)],
            "indexes": [i.to_dict() for i in sorted(self.indexes, key=lambda x: x.id)],
        }


@dataclass
class FlowStep:
    """Passo de fluxo de caso de uso."""
    number: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "number": self.number,
            "description": self.description,
        }


@dataclass
class NamedFlow:
    """Fluxo nomeado (alternativo ou de excecao)."""
    id: str
    steps: List[FlowStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "steps": [s.to_dict() for s in sorted(self.steps, key=lambda x: x.number)],
        }


@dataclass
class UseCaseDefinition:
    """Definicao de caso de uso."""
    id: str
    name: str
    description: str = ""
    actors: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    main_flow: List[FlowStep] = field(default_factory=list)
    alternative_flows: List[NamedFlow] = field(default_factory=list)
    exception_flows: List[NamedFlow] = field(default_factory=list)
    priority: PriorityLevel = PriorityLevel.MEDIUM
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "actors": sorted(self.actors),
            "preconditions": self.preconditions,  # Mantém ordem
            "postconditions": self.postconditions,  # Mantém ordem
            "main_flow": [s.to_dict() for s in sorted(self.main_flow, key=lambda x: x.number)],
            "alternative_flows": [f.to_dict() for f in sorted(self.alternative_flows, key=lambda x: x.id)],
            "exception_flows": [f.to_dict() for f in sorted(self.exception_flows, key=lambda x: x.id)],
            "priority": self.priority.value,
            "complexity": self.complexity.value,
        }


@dataclass
class OperationDefinition:
    """Definicao de operacao de integracao."""
    id: str
    method: str = "GET"
    path: str = ""
    request_type: str = "void"
    response_type: str = "void"
    error_codes: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "method": self.method,
            "path": self.path,
            "request_type": self.request_type,
            "response_type": self.response_type,
            "error_codes": sorted(self.error_codes),
        }


@dataclass
class RetryConfig:
    """Configuracao de retry."""
    max_attempts: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    multiplier: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "max_attempts": self.max_attempts,
            "initial_delay_ms": self.initial_delay_ms,
            "max_delay_ms": self.max_delay_ms,
            "multiplier": self.multiplier,
        }


@dataclass
class CircuitBreakerConfig:
    """Configuracao de circuit breaker."""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_ms: int = 30000

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout_ms": self.timeout_ms,
        }


@dataclass
class AuthConfig:
    """Configuracao de autenticacao de integracao."""
    method: AuthMethod = AuthMethod.NONE
    credentials: str = ""
    token_url: str = ""
    scope: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        result = {
            "method": self.method.value,
        }
        if self.credentials:
            result["credentials"] = self.credentials
        if self.token_url:
            result["token_url"] = self.token_url
        if self.scope:
            result["scope"] = self.scope
        return result


@dataclass
class IntegrationDefinition:
    """Definicao de integracao."""
    id: str
    name: str
    description: str = ""
    integration_type: IntegrationType = IntegrationType.REST_API
    protocol: ProtocolType = ProtocolType.HTTPS
    endpoint: str = ""
    authentication: Optional[AuthConfig] = None
    operations: List[OperationDefinition] = field(default_factory=list)
    retry_policy: Optional[RetryConfig] = None
    timeout_ms: int = 30000
    circuit_breaker: Optional[CircuitBreakerConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "integration_type": self.integration_type.value,
            "protocol": self.protocol.value,
            "endpoint": self.endpoint,
            "timeout_ms": self.timeout_ms,
            "operations": [o.to_dict() for o in sorted(self.operations, key=lambda x: x.id)],
        }
        if self.authentication:
            result["authentication"] = self.authentication.to_dict()
        if self.retry_policy:
            result["retry_policy"] = self.retry_policy.to_dict()
        if self.circuit_breaker:
            result["circuit_breaker"] = self.circuit_breaker.to_dict()
        return result


@dataclass
class NFRDefinition:
    """Definicao de requisito nao-funcional."""
    id: str
    nfr_type: NFRType
    name: str
    description: str = ""
    metric: str = ""
    target: str = ""
    measurement: str = ""
    priority: PriorityLevel = PriorityLevel.MEDIUM
    verification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario canonico."""
        return {
            "id": self.id,
            "nfr_type": self.nfr_type.value,
            "name": self.name,
            "description": self.description,
            "metric": self.metric,
            "target": self.target,
            "measurement": self.measurement,
            "priority": self.priority.value,
            "verification": self.verification,
        }


# ============================================
# IDL DOCUMENT
# ============================================

@dataclass
class IDLDocument:
    """Documento IDL completo."""
    system: Optional[SystemDefinition] = None
    actors: List[ActorDefinition] = field(default_factory=list)
    entities: List[EntityDefinition] = field(default_factory=list)
    usecases: List[UseCaseDefinition] = field(default_factory=list)
    integrations: List[IntegrationDefinition] = field(default_factory=list)
    nonfunctional: List[NFRDefinition] = field(default_factory=list)
    contract_notes: Optional[str] = None

    def to_hashable_dict(self) -> Dict[str, Any]:
        """Retorna dicionario com campos hashable (para calculo de hash)."""
        result: Dict[str, Any] = {
            "schema_version": IDL_SCHEMA_VERSION,
        }

        if self.system:
            result["system"] = self.system.to_dict()
        else:
            result["system"] = None

        result["actors"] = [a.to_dict() for a in sorted(self.actors, key=lambda x: x.id)]
        result["entities"] = [e.to_dict() for e in sorted(self.entities, key=lambda x: x.id)]
        result["usecases"] = [u.to_dict() for u in sorted(self.usecases, key=lambda x: x.id)]
        result["integrations"] = [i.to_dict() for i in sorted(self.integrations, key=lambda x: x.id)]
        result["nonfunctional"] = [n.to_dict() for n in sorted(self.nonfunctional, key=lambda x: x.id)]

        return result

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Retorna dicionario canonico completo (com hash e metadados)."""
        hashable = self.to_hashable_dict()
        content_hash = compute_content_hash_sha256(hashable)

        result = {
            "schema_version": IDL_SCHEMA_VERSION,
            "content_hash_sha256": content_hash,
            "timestamp": datetime.now().isoformat(),
            "parser_version": "1.0.0",
        }

        # Adiciona campos hashable
        if self.system:
            result["system"] = self.system.to_dict()
        else:
            result["system"] = None

        result["actors"] = hashable["actors"]
        result["entities"] = hashable["entities"]
        result["usecases"] = hashable["usecases"]
        result["integrations"] = hashable["integrations"]
        result["nonfunctional"] = hashable["nonfunctional"]

        # Campo opcional fora do hash
        if self.contract_notes:
            result["contract_notes"] = self.contract_notes

        return result

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Serializa para JSON canonico."""
        canonical = self.to_canonical_dict()
        return json.dumps(
            canonical,
            sort_keys=True,
            separators=(',', ': ') if indent else (',', ':'),
            ensure_ascii=False,
            indent=indent,
        )

    def to_markdown(self) -> str:
        """Gera representacao Markdown do documento."""
        canonical = self.to_canonical_dict()
        lines = []

        # Header com contrato
        lines.append("# IDL Document")
        lines.append("")
        lines.append(f"SCHEMA VERSION: {IDL_SCHEMA_VERSION}")
        lines.append(f"CONTENT HASH: {canonical['content_hash_sha256']}")
        lines.append("")

        # System
        if self.system:
            lines.append("## System")
            lines.append("")
            lines.append(f"- **ID:** {self.system.id}")
            lines.append(f"- **Name:** {self.system.name}")
            if self.system.description:
                lines.append(f"- **Description:** {self.system.description}")
            lines.append(f"- **Version:** {self.system.version}")
            if self.system.domain:
                lines.append(f"- **Domain:** {self.system.domain}")
            if self.system.owner:
                lines.append(f"- **Owner:** {self.system.owner}")
            if self.system.contact:
                lines.append(f"- **Contact:** {self.system.contact}")
            lines.append("")

        # Actors
        if self.actors:
            lines.append("## Actors")
            lines.append("")
            for actor in sorted(self.actors, key=lambda x: x.id):
                lines.append(f"### {actor.id} ({actor.actor_type.value})")
                lines.append("")
                lines.append(f"- **Name:** {actor.name}")
                if actor.description:
                    lines.append(f"- **Description:** {actor.description}")
                if actor.permissions:
                    lines.append(f"- **Permissions:** {', '.join(sorted(actor.permissions))}")
                lines.append(f"- **Authentication:** {actor.authentication.value}")
                lines.append("")

        # Entities
        if self.entities:
            lines.append("## Entities")
            lines.append("")
            for entity in sorted(self.entities, key=lambda x: x.id):
                lines.append(f"### {entity.id}")
                lines.append("")
                if entity.fields:
                    lines.append("**Fields:**")
                    for field_def in sorted(entity.fields, key=lambda x: x.id):
                        modifiers = []
                        if field_def.required:
                            modifiers.append("required")
                        if field_def.unique:
                            modifiers.append("unique")
                        if field_def.indexed:
                            modifiers.append("indexed")
                        mod_str = f" [{', '.join(modifiers)}]" if modifiers else ""
                        lines.append(f"- `{field_def.id}`: {field_def.field_type}{mod_str}")
                    lines.append("")
                if entity.relations:
                    lines.append("**Relations:**")
                    for rel in sorted(entity.relations, key=lambda x: x.id):
                        lines.append(f"- `{rel.id}` -> {rel.target_entity} ({rel.relation_type.value})")
                    lines.append("")
                if entity.constraints:
                    lines.append("**Constraints:**")
                    for constraint in sorted(entity.constraints, key=lambda x: x.id):
                        lines.append(f"- `{constraint.id}`: {constraint.expression}")
                    lines.append("")
                if entity.indexes:
                    lines.append("**Indexes:**")
                    for idx in sorted(entity.indexes, key=lambda x: x.id):
                        unique_str = " (unique)" if idx.unique else ""
                        lines.append(f"- `{idx.id}` on ({', '.join(idx.fields)}){unique_str}")
                    lines.append("")

        # Use Cases
        if self.usecases:
            lines.append("## Use Cases")
            lines.append("")
            for uc in sorted(self.usecases, key=lambda x: x.id):
                lines.append(f"### {uc.id}: {uc.name}")
                lines.append("")
                if uc.description:
                    lines.append(f"{uc.description}")
                    lines.append("")
                lines.append(f"- **Actors:** {', '.join(sorted(uc.actors))}")
                lines.append(f"- **Priority:** {uc.priority.value}")
                lines.append(f"- **Complexity:** {uc.complexity.value}")
                if uc.preconditions:
                    lines.append("")
                    lines.append("**Preconditions:**")
                    for pre in uc.preconditions:
                        lines.append(f"- {pre}")
                if uc.main_flow:
                    lines.append("")
                    lines.append("**Main Flow:**")
                    for step in sorted(uc.main_flow, key=lambda x: x.number):
                        lines.append(f"{step.number}. {step.description}")
                if uc.postconditions:
                    lines.append("")
                    lines.append("**Postconditions:**")
                    for post in uc.postconditions:
                        lines.append(f"- {post}")
                lines.append("")

        # Integrations
        if self.integrations:
            lines.append("## Integrations")
            lines.append("")
            for integ in sorted(self.integrations, key=lambda x: x.id):
                lines.append(f"### {integ.id}: {integ.name}")
                lines.append("")
                if integ.description:
                    lines.append(f"{integ.description}")
                    lines.append("")
                lines.append(f"- **Type:** {integ.integration_type.value}")
                lines.append(f"- **Protocol:** {integ.protocol.value}")
                if integ.endpoint:
                    lines.append(f"- **Endpoint:** {integ.endpoint}")
                lines.append(f"- **Timeout:** {integ.timeout_ms}ms")
                if integ.operations:
                    lines.append("")
                    lines.append("**Operations:**")
                    for op in sorted(integ.operations, key=lambda x: x.id):
                        lines.append(f"- `{op.id}`: {op.method} {op.path}")
                lines.append("")

        # Non-Functional Requirements
        if self.nonfunctional:
            lines.append("## Non-Functional Requirements")
            lines.append("")
            for nfr in sorted(self.nonfunctional, key=lambda x: x.id):
                lines.append(f"### {nfr.id}: {nfr.name} ({nfr.nfr_type.value})")
                lines.append("")
                if nfr.description:
                    lines.append(f"{nfr.description}")
                    lines.append("")
                lines.append(f"- **Priority:** {nfr.priority.value}")
                if nfr.metric:
                    lines.append(f"- **Metric:** {nfr.metric}")
                if nfr.target:
                    lines.append(f"- **Target:** {nfr.target}")
                if nfr.measurement:
                    lines.append(f"- **Measurement:** {nfr.measurement}")
                if nfr.verification:
                    lines.append(f"- **Verification:** {nfr.verification}")
                lines.append("")

        return '\n'.join(lines)


# ============================================
# HASH FUNCTIONS
# ============================================

def compute_content_hash_sha256(hashable_payload: Dict[str, Any]) -> str:
    """Calcula hash SHA256 do payload hashable.

    Usa serializacao canonica JSON (sort_keys=True, separators minimos).
    """
    canonical_json = json.dumps(
        hashable_payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def extract_hashable_payload_from_canonical(canonical_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai campos hashable de um dicionario canonico.

    Usado pelo Contract Gate para recalcular o hash.
    """
    return {field: canonical_dict[field] for field in HASHABLE_FIELDS if field in canonical_dict}


# ============================================
# PARSER
# ============================================

class IDLParseError(Exception):
    """Erro de parsing do IDL."""
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.line = line
        self.column = column
        super().__init__(f"Line {line}, Column {column}: {message}")


class IDLLexer:
    """Lexer para tokenizacao do IDL."""

    KEYWORDS = {
        # Sections
        'system', 'actors', 'entities', 'usecases', 'integrations', 'nonfunctional',
        # Actor types
        'human', 'system', 'external',
        # Entity members
        'entity', 'field', 'has_one', 'has_many', 'belongs_to', 'many_to_many',
        'constraint', 'index', 'on',
        # Field modifiers
        'required', 'unique', 'indexed', 'default', 'min', 'max', 'pattern',
        # Relation modifiers
        'cascade_delete', 'nullable', 'through',
        # Use case
        'usecase', 'actor', 'preconditions', 'postconditions',
        'main_flow', 'alternative_flows', 'exception_flows',
        'priority', 'complexity',
        # Priority/complexity values
        'critical', 'high', 'medium', 'low',
        'trivial', 'simple', 'complex', 'very_complex',
        # Integration
        'integration', 'type', 'protocol', 'endpoint', 'authentication',
        'operations', 'retry_policy', 'timeout_ms', 'circuit_breaker',
        'method', 'path', 'request', 'response', 'errors',
        'max_attempts', 'initial_delay_ms', 'max_delay_ms', 'multiplier',
        'failure_threshold', 'success_threshold',
        'credentials', 'token_url', 'scope',
        # Integration types
        'rest_api', 'graphql', 'grpc', 'soap', 'message_queue', 'webhook', 'database', 'file_system',
        # Protocol types
        'http', 'https', 'ws', 'wss', 'amqp', 'mqtt', 'tcp', 'udp',
        # Auth methods
        'none', 'basic', 'token', 'oauth2', 'certificate',
        # NFR types
        'performance', 'security', 'availability', 'scalability',
        'maintainability', 'usability', 'compliance',
        # NFR properties
        'metric', 'target', 'measurement', 'verification',
        # Primitive types
        'string', 'int', 'float', 'bool', 'datetime', 'uuid', 'text', 'decimal',
        # Collection types
        'list', 'set', 'map',
        # HTTP methods
        'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS',
        # Special
        'void', 'any', 'true', 'false', 'null',
        # Common properties
        'name', 'description', 'version', 'domain', 'owner', 'contact', 'permissions',
    }

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Tuple[str, Any, int, int]] = []

    def tokenize(self) -> List[Tuple[str, Any, int, int]]:
        """Tokeniza o fonte IDL."""
        while self.pos < len(self.source):
            self._skip_whitespace_and_comments()
            if self.pos >= len(self.source):
                break

            ch = self.source[self.pos]
            start_line, start_col = self.line, self.column

            if ch == '"':
                token = self._read_string()
                self.tokens.append(('STRING', token, start_line, start_col))
            elif ch in '{}[]():,.<>-':
                self._advance()
                if ch == '-' and self.pos < len(self.source) and self.source[self.pos] == '>':
                    self._advance()
                    self.tokens.append(('ARROW', '->', start_line, start_col))
                else:
                    self.tokens.append((ch, ch, start_line, start_col))
            elif ch.isdigit() or (ch == '-' and self.pos + 1 < len(self.source) and self.source[self.pos + 1].isdigit()):
                token = self._read_number()
                self.tokens.append(('NUMBER', token, start_line, start_col))
            elif ch.isalpha() or ch == '_':
                token = self._read_identifier()
                if token in self.KEYWORDS:
                    self.tokens.append(('KEYWORD', token, start_line, start_col))
                else:
                    self.tokens.append(('IDENTIFIER', token, start_line, start_col))
            else:
                raise IDLParseError(f"Unexpected character: {ch}", self.line, self.column)

        self.tokens.append(('EOF', None, self.line, self.column))
        return self.tokens

    def _advance(self) -> str:
        """Avanca uma posicao no fonte."""
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _skip_whitespace_and_comments(self):
        """Pula whitespace e comentarios."""
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\n\r':
                self._advance()
            elif ch == '/' and self.pos + 1 < len(self.source):
                if self.source[self.pos + 1] == '/':
                    self._skip_line_comment()
                elif self.source[self.pos + 1] == '*':
                    self._skip_block_comment()
                else:
                    break
            else:
                break

    def _skip_line_comment(self):
        """Pula comentario de linha."""
        while self.pos < len(self.source) and self.source[self.pos] != '\n':
            self._advance()
        if self.pos < len(self.source):
            self._advance()  # Pula o \n

    def _skip_block_comment(self):
        """Pula comentario de bloco."""
        self._advance()  # /
        self._advance()  # *
        while self.pos < len(self.source) - 1:
            if self.source[self.pos] == '*' and self.source[self.pos + 1] == '/':
                self._advance()
                self._advance()
                return
            self._advance()
        raise IDLParseError("Unterminated block comment", self.line, self.column)

    def _read_string(self) -> str:
        """Le uma string literal."""
        self._advance()  # Pula "
        result = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == '"':
                self._advance()
                return ''.join(result)
            elif ch == '\\':
                self._advance()
                if self.pos < len(self.source):
                    escape_ch = self.source[self.pos]
                    if escape_ch == 'n':
                        result.append('\n')
                    elif escape_ch == 'r':
                        result.append('\r')
                    elif escape_ch == 't':
                        result.append('\t')
                    elif escape_ch == '"':
                        result.append('"')
                    elif escape_ch == '\\':
                        result.append('\\')
                    else:
                        result.append(escape_ch)
                    self._advance()
            elif ch == '\n':
                raise IDLParseError("Unterminated string", self.line, self.column)
            else:
                result.append(ch)
                self._advance()
        raise IDLParseError("Unterminated string", self.line, self.column)

    def _read_number(self) -> Union[int, float]:
        """Le um numero."""
        result = []
        if self.source[self.pos] == '-':
            result.append(self._advance())
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            result.append(self._advance())
        # Only consume '.' if followed by a digit (for decimals like 1.5)
        # Don't consume '.' if followed by space/string (for flow steps like "1. description")
        if (self.pos < len(self.source) and
            self.source[self.pos] == '.' and
            self.pos + 1 < len(self.source) and
            self.source[self.pos + 1].isdigit()):
            result.append(self._advance())
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                result.append(self._advance())
            return float(''.join(result))
        return int(''.join(result))

    def _read_identifier(self) -> str:
        """Le um identificador."""
        result = []
        while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
            result.append(self._advance())
        return ''.join(result)


class IDLParser:
    """Parser para linguagem IDL."""

    def __init__(self):
        self.tokens: List[Tuple[str, Any, int, int]] = []
        self.pos = 0

    def parse(self, source: str) -> IDLDocument:
        """Faz parsing do fonte IDL e retorna um IDLDocument."""
        lexer = IDLLexer(source)
        self.tokens = lexer.tokenize()
        self.pos = 0

        doc = IDLDocument()

        while not self._is_at_end():
            section_type, section_value, _, _ = self._current()

            if section_type == 'KEYWORD':
                if section_value == 'system':
                    doc.system = self._parse_system()
                elif section_value == 'actors':
                    doc.actors = self._parse_actors()
                elif section_value == 'entities':
                    doc.entities = self._parse_entities()
                elif section_value == 'usecases':
                    doc.usecases = self._parse_usecases()
                elif section_value == 'integrations':
                    doc.integrations = self._parse_integrations()
                elif section_value == 'nonfunctional':
                    doc.nonfunctional = self._parse_nonfunctional()
                else:
                    self._error(f"Unexpected keyword: {section_value}")
            else:
                self._error(f"Expected section keyword, got {section_type}")

        return doc

    def _current(self) -> Tuple[str, Any, int, int]:
        """Retorna token atual."""
        return self.tokens[self.pos]

    def _is_at_end(self) -> bool:
        """Verifica se chegou ao fim."""
        return self.tokens[self.pos][0] == 'EOF'

    def _advance(self) -> Tuple[str, Any, int, int]:
        """Avanca para proximo token."""
        token = self.tokens[self.pos]
        if not self._is_at_end():
            self.pos += 1
        return token

    def _expect(self, expected_type: str, expected_value: Any = None) -> Tuple[str, Any, int, int]:
        """Espera um token especifico."""
        token_type, token_value, line, col = self._current()
        if token_type != expected_type:
            self._error(f"Expected {expected_type}, got {token_type}")
        if expected_value is not None and token_value != expected_value:
            self._error(f"Expected {expected_value}, got {token_value}")
        return self._advance()

    def _match(self, token_type: str, token_value: Any = None) -> bool:
        """Verifica se token atual casa com esperado."""
        current_type, current_value, _, _ = self._current()
        if current_type != token_type:
            return False
        if token_value is not None and current_value != token_value:
            return False
        return True

    def _error(self, message: str):
        """Levanta erro de parsing."""
        _, _, line, col = self._current()
        raise IDLParseError(message, line, col)

    def _expect_identifier_or_keyword(self) -> str:
        """Espera um identificador ou keyword (para permitir keywords como nomes)."""
        token_type, token_value, _, _ = self._current()
        if token_type not in ('IDENTIFIER', 'KEYWORD'):
            self._error(f"Expected identifier, got {token_type}")
        self._advance()
        return token_value

    # ================== SYSTEM ==================

    def _parse_system(self) -> SystemDefinition:
        """Faz parsing de system section."""
        self._expect('KEYWORD', 'system')
        _, system_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        system = SystemDefinition(id=system_id, name=system_id)

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')
            _, prop_value, _, _ = self._expect('STRING')

            if prop_name == 'name':
                system.name = prop_value
            elif prop_name == 'description':
                system.description = prop_value
            elif prop_name == 'version':
                system.version = prop_value
            elif prop_name == 'domain':
                system.domain = prop_value
            elif prop_name == 'owner':
                system.owner = prop_value
            elif prop_name == 'contact':
                system.contact = prop_value

        self._expect('}', '}')
        return system

    # ================== ACTORS ==================

    def _parse_actors(self) -> List[ActorDefinition]:
        """Faz parsing de actors section."""
        self._expect('KEYWORD', 'actors')
        self._expect('{', '{')

        actors = []
        while not self._match('}', '}'):
            actors.append(self._parse_actor())

        self._expect('}', '}')
        return actors

    def _parse_actor(self) -> ActorDefinition:
        """Faz parsing de uma definicao de ator."""
        _, actor_type_str, _, _ = self._expect('KEYWORD')
        actor_type = ActorType(actor_type_str)
        _, actor_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        actor = ActorDefinition(id=actor_id, actor_type=actor_type, name=actor_id)

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')

            if prop_name == 'name':
                _, value, _, _ = self._expect('STRING')
                actor.name = value
            elif prop_name == 'description':
                _, value, _, _ = self._expect('STRING')
                actor.description = value
            elif prop_name == 'permissions':
                actor.permissions = self._parse_identifier_list()
            elif prop_name == 'authentication':
                _, value, _, _ = self._expect('KEYWORD')
                actor.authentication = AuthMethod(value)

        self._expect('}', '}')
        return actor

    # ================== ENTITIES ==================

    def _parse_entities(self) -> List[EntityDefinition]:
        """Faz parsing de entities section."""
        self._expect('KEYWORD', 'entities')
        self._expect('{', '{')

        entities = []
        while not self._match('}', '}'):
            entities.append(self._parse_entity())

        self._expect('}', '}')
        return entities

    def _parse_entity(self) -> EntityDefinition:
        """Faz parsing de uma definicao de entidade."""
        self._expect('KEYWORD', 'entity')
        _, entity_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        entity = EntityDefinition(id=entity_id)

        while not self._match('}', '}'):
            token_type, keyword, _, _ = self._current()

            if token_type == 'KEYWORD':
                if keyword == 'field':
                    entity.fields.append(self._parse_field())
                elif keyword in ('has_one', 'has_many', 'belongs_to', 'many_to_many'):
                    entity.relations.append(self._parse_relation())
                elif keyword == 'constraint':
                    entity.constraints.append(self._parse_constraint())
                elif keyword == 'index':
                    entity.indexes.append(self._parse_index())
                else:
                    self._error(f"Unexpected entity member: {keyword}")
            else:
                self._error(f"Expected entity member, got {token_type}")

        self._expect('}', '}')
        return entity

    def _parse_field(self) -> FieldDefinition:
        """Faz parsing de uma definicao de campo."""
        self._expect('KEYWORD', 'field')
        field_id = self._expect_identifier_or_keyword()
        self._expect(':', ':')

        field_type = self._parse_type()

        field_def = FieldDefinition(id=field_id, field_type=field_type)

        # Parse modifiers
        while self._match('KEYWORD'):
            _, mod, _, _ = self._current()
            if mod == 'required':
                self._advance()
                field_def.required = True
            elif mod == 'unique':
                self._advance()
                field_def.unique = True
            elif mod == 'indexed':
                self._advance()
                field_def.indexed = True
            elif mod == 'default':
                self._advance()
                self._expect('(', '(')
                field_def.default = self._parse_literal()
                self._expect(')', ')')
            elif mod == 'min':
                self._advance()
                self._expect('(', '(')
                _, value, _, _ = self._expect('NUMBER')
                field_def.min_value = value
                self._expect(')', ')')
            elif mod == 'max':
                self._advance()
                self._expect('(', '(')
                _, value, _, _ = self._expect('NUMBER')
                field_def.max_value = value
                self._expect(')', ')')
            elif mod == 'pattern':
                self._advance()
                self._expect('(', '(')
                _, value, _, _ = self._expect('STRING')
                field_def.pattern = value
                self._expect(')', ')')
            else:
                break

        return field_def

    def _parse_type(self) -> str:
        """Faz parsing de um tipo."""
        token_type, token_value, _, _ = self._current()

        if token_type == 'KEYWORD' and token_value in ('list', 'set', 'map'):
            collection_type = token_value
            self._advance()
            self._expect('<', '<')
            inner_type = self._parse_type()
            if collection_type == 'map':
                self._expect(',', ',')
                value_type = self._parse_type()
                self._expect('>', '>')
                return f"map<{inner_type},{value_type}>"
            self._expect('>', '>')
            return f"{collection_type}<{inner_type}>"
        elif token_type == 'KEYWORD':
            self._advance()
            return token_value
        elif token_type == 'IDENTIFIER':
            self._advance()
            return token_value
        else:
            self._error(f"Expected type, got {token_type}")
            return ""  # Never reached

    def _parse_literal(self) -> Any:
        """Faz parsing de um literal."""
        token_type, token_value, _, _ = self._current()

        if token_type == 'STRING':
            self._advance()
            return token_value
        elif token_type == 'NUMBER':
            self._advance()
            return token_value
        elif token_type == 'KEYWORD' and token_value in ('true', 'false', 'null'):
            self._advance()
            if token_value == 'true':
                return True
            elif token_value == 'false':
                return False
            else:
                return None
        else:
            self._error(f"Expected literal, got {token_type}")
            return None  # Never reached

    def _parse_relation(self) -> RelationDefinition:
        """Faz parsing de uma definicao de relacao."""
        _, rel_type_str, _, _ = self._expect('KEYWORD')
        rel_type = RelationType(rel_type_str)
        rel_id = self._expect_identifier_or_keyword()
        self._expect('ARROW', '->')
        target = self._expect_identifier_or_keyword()

        rel = RelationDefinition(id=rel_id, relation_type=rel_type, target_entity=target)

        # Parse modifiers
        while self._match('KEYWORD'):
            _, mod, _, _ = self._current()
            if mod == 'cascade_delete':
                self._advance()
                rel.cascade_delete = True
            elif mod == 'nullable':
                self._advance()
                rel.nullable = True
            elif mod == 'through':
                self._advance()
                self._expect('(', '(')
                _, through_entity, _, _ = self._expect('IDENTIFIER')
                rel.through = through_entity
                self._expect(')', ')')
            else:
                break

        return rel

    def _parse_constraint(self) -> ConstraintDefinition:
        """Faz parsing de uma definicao de constraint."""
        self._expect('KEYWORD', 'constraint')
        _, constraint_id, _, _ = self._expect('IDENTIFIER')
        self._expect(':', ':')
        _, expr, _, _ = self._expect('STRING')

        return ConstraintDefinition(id=constraint_id, expression=expr)

    def _parse_index(self) -> IndexDefinition:
        """Faz parsing de uma definicao de indice."""
        self._expect('KEYWORD', 'index')
        index_id = self._expect_identifier_or_keyword()
        self._expect('KEYWORD', 'on')
        self._expect('(', '(')

        fields = []
        first_field = self._expect_identifier_or_keyword()
        fields.append(first_field)

        while self._match(',', ','):
            self._advance()
            next_field = self._expect_identifier_or_keyword()
            fields.append(next_field)

        self._expect(')', ')')

        unique = False
        if self._match('KEYWORD', 'unique'):
            self._advance()
            unique = True

        return IndexDefinition(id=index_id, fields=fields, unique=unique)

    # ================== USECASES ==================

    def _parse_usecases(self) -> List[UseCaseDefinition]:
        """Faz parsing de usecases section."""
        self._expect('KEYWORD', 'usecases')
        self._expect('{', '{')

        usecases = []
        while not self._match('}', '}'):
            usecases.append(self._parse_usecase())

        self._expect('}', '}')
        return usecases

    def _parse_usecase(self) -> UseCaseDefinition:
        """Faz parsing de uma definicao de caso de uso."""
        self._expect('KEYWORD', 'usecase')
        _, uc_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        uc = UseCaseDefinition(id=uc_id, name=uc_id)

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')

            if prop_name == 'name':
                _, value, _, _ = self._expect('STRING')
                uc.name = value
            elif prop_name == 'description':
                _, value, _, _ = self._expect('STRING')
                uc.description = value
            elif prop_name == 'actor':
                _, value, _, _ = self._expect('IDENTIFIER')
                uc.actors = [value]
            elif prop_name == 'actors':
                uc.actors = self._parse_identifier_list()
            elif prop_name == 'preconditions':
                uc.preconditions = self._parse_string_list()
            elif prop_name == 'postconditions':
                uc.postconditions = self._parse_string_list()
            elif prop_name == 'main_flow':
                uc.main_flow = self._parse_flow()
            elif prop_name == 'alternative_flows':
                uc.alternative_flows = self._parse_named_flows()
            elif prop_name == 'exception_flows':
                uc.exception_flows = self._parse_named_flows()
            elif prop_name == 'priority':
                _, value, _, _ = self._expect('KEYWORD')
                uc.priority = PriorityLevel(value)
            elif prop_name == 'complexity':
                _, value, _, _ = self._expect('KEYWORD')
                uc.complexity = ComplexityLevel(value)

        self._expect('}', '}')
        return uc

    def _parse_flow(self) -> List[FlowStep]:
        """Faz parsing de um fluxo."""
        self._expect('[', '[')

        steps = []
        while not self._match(']', ']'):
            _, step_num, _, _ = self._expect('NUMBER')
            self._expect('.', '.')
            _, step_desc, _, _ = self._expect('STRING')
            steps.append(FlowStep(number=int(step_num), description=step_desc))

            if self._match(',', ','):
                self._advance()

        self._expect(']', ']')
        return steps

    def _parse_named_flows(self) -> List[NamedFlow]:
        """Faz parsing de fluxos nomeados."""
        self._expect('[', '[')

        flows = []
        while not self._match(']', ']'):
            _, flow_id, _, _ = self._expect('IDENTIFIER')
            self._expect(':', ':')
            flow_steps = self._parse_flow()
            flows.append(NamedFlow(id=flow_id, steps=flow_steps))

            if self._match(',', ','):
                self._advance()

        self._expect(']', ']')
        return flows

    # ================== INTEGRATIONS ==================

    def _parse_integrations(self) -> List[IntegrationDefinition]:
        """Faz parsing de integrations section."""
        self._expect('KEYWORD', 'integrations')
        self._expect('{', '{')

        integrations = []
        while not self._match('}', '}'):
            integrations.append(self._parse_integration())

        self._expect('}', '}')
        return integrations

    def _parse_integration(self) -> IntegrationDefinition:
        """Faz parsing de uma definicao de integracao."""
        self._expect('KEYWORD', 'integration')
        _, integ_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        integ = IntegrationDefinition(id=integ_id, name=integ_id)

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')

            if prop_name == 'name':
                _, value, _, _ = self._expect('STRING')
                integ.name = value
            elif prop_name == 'description':
                _, value, _, _ = self._expect('STRING')
                integ.description = value
            elif prop_name == 'type':
                _, value, _, _ = self._expect('KEYWORD')
                integ.integration_type = IntegrationType(value)
            elif prop_name == 'protocol':
                _, value, _, _ = self._expect('KEYWORD')
                integ.protocol = ProtocolType(value)
            elif prop_name == 'endpoint':
                _, value, _, _ = self._expect('STRING')
                integ.endpoint = value
            elif prop_name == 'authentication':
                integ.authentication = self._parse_auth_config()
            elif prop_name == 'operations':
                integ.operations = self._parse_operations()
            elif prop_name == 'retry_policy':
                integ.retry_policy = self._parse_retry_config()
            elif prop_name == 'timeout_ms':
                _, value, _, _ = self._expect('NUMBER')
                integ.timeout_ms = int(value)
            elif prop_name == 'circuit_breaker':
                integ.circuit_breaker = self._parse_circuit_config()

        self._expect('}', '}')
        return integ

    def _parse_auth_config(self) -> AuthConfig:
        """Faz parsing de configuracao de autenticacao."""
        self._expect('{', '{')

        auth = AuthConfig()

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')

            if prop_name == 'method':
                _, value, _, _ = self._expect('KEYWORD')
                auth.method = AuthMethod(value)
            elif prop_name == 'credentials':
                _, value, _, _ = self._expect('STRING')
                auth.credentials = value
            elif prop_name == 'token_url':
                _, value, _, _ = self._expect('STRING')
                auth.token_url = value
            elif prop_name == 'scope':
                _, value, _, _ = self._expect('STRING')
                auth.scope = value

        self._expect('}', '}')
        return auth

    def _parse_operations(self) -> List[OperationDefinition]:
        """Faz parsing de lista de operacoes."""
        self._expect('[', '[')

        operations = []
        while not self._match(']', ']'):
            _, op_id, _, _ = self._expect('IDENTIFIER')
            self._expect(':', ':')
            self._expect('{', '{')

            op = OperationDefinition(id=op_id)

            while not self._match('}', '}'):
                _, prop_name, _, _ = self._expect('KEYWORD')
                self._expect(':', ':')

                if prop_name == 'method':
                    _, value, _, _ = self._expect('KEYWORD')
                    op.method = value
                elif prop_name == 'path':
                    _, value, _, _ = self._expect('STRING')
                    op.path = value
                elif prop_name == 'request':
                    _, value, _, _ = self._current()
                    if value in ('void', 'any'):
                        self._advance()
                        op.request_type = value
                    else:
                        _, value, _, _ = self._expect('IDENTIFIER')
                        op.request_type = value
                elif prop_name == 'response':
                    _, value, _, _ = self._current()
                    if value in ('void', 'any'):
                        self._advance()
                        op.response_type = value
                    else:
                        _, value, _, _ = self._expect('IDENTIFIER')
                        op.response_type = value
                elif prop_name == 'errors':
                    op.error_codes = self._parse_number_list()

            self._expect('}', '}')
            operations.append(op)

            if self._match(',', ','):
                self._advance()

        self._expect(']', ']')
        return operations

    def _parse_retry_config(self) -> RetryConfig:
        """Faz parsing de configuracao de retry."""
        self._expect('{', '{')

        retry = RetryConfig()

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')
            _, value, _, _ = self._expect('NUMBER')

            if prop_name == 'max_attempts':
                retry.max_attempts = int(value)
            elif prop_name == 'initial_delay_ms':
                retry.initial_delay_ms = int(value)
            elif prop_name == 'max_delay_ms':
                retry.max_delay_ms = int(value)
            elif prop_name == 'multiplier':
                retry.multiplier = float(value)

        self._expect('}', '}')
        return retry

    def _parse_circuit_config(self) -> CircuitBreakerConfig:
        """Faz parsing de configuracao de circuit breaker."""
        self._expect('{', '{')

        circuit = CircuitBreakerConfig()

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')
            _, value, _, _ = self._expect('NUMBER')

            if prop_name == 'failure_threshold':
                circuit.failure_threshold = int(value)
            elif prop_name == 'success_threshold':
                circuit.success_threshold = int(value)
            elif prop_name == 'timeout_ms':
                circuit.timeout_ms = int(value)

        self._expect('}', '}')
        return circuit

    # ================== NONFUNCTIONAL ==================

    def _parse_nonfunctional(self) -> List[NFRDefinition]:
        """Faz parsing de nonfunctional section."""
        self._expect('KEYWORD', 'nonfunctional')
        self._expect('{', '{')

        nfrs = []
        while not self._match('}', '}'):
            nfrs.append(self._parse_nfr())

        self._expect('}', '}')
        return nfrs

    def _parse_nfr(self) -> NFRDefinition:
        """Faz parsing de uma definicao de requisito nao-funcional."""
        _, nfr_type_str, _, _ = self._expect('KEYWORD')
        nfr_type = NFRType(nfr_type_str)
        _, nfr_id, _, _ = self._expect('IDENTIFIER')
        self._expect('{', '{')

        nfr = NFRDefinition(id=nfr_id, nfr_type=nfr_type, name=nfr_id)

        while not self._match('}', '}'):
            _, prop_name, _, _ = self._expect('KEYWORD')
            self._expect(':', ':')

            if prop_name == 'name':
                _, value, _, _ = self._expect('STRING')
                nfr.name = value
            elif prop_name == 'description':
                _, value, _, _ = self._expect('STRING')
                nfr.description = value
            elif prop_name == 'metric':
                _, value, _, _ = self._expect('STRING')
                nfr.metric = value
            elif prop_name == 'target':
                _, value, _, _ = self._expect('STRING')
                nfr.target = value
            elif prop_name == 'measurement':
                _, value, _, _ = self._expect('STRING')
                nfr.measurement = value
            elif prop_name == 'priority':
                _, value, _, _ = self._expect('KEYWORD')
                nfr.priority = PriorityLevel(value)
            elif prop_name == 'verification':
                _, value, _, _ = self._expect('STRING')
                nfr.verification = value

        self._expect('}', '}')
        return nfr

    # ================== HELPERS ==================

    def _parse_identifier_list(self) -> List[str]:
        """Faz parsing de lista de identificadores."""
        self._expect('[', '[')

        items = []
        if not self._match(']', ']'):
            _, first, _, _ = self._expect('IDENTIFIER')
            items.append(first)

            while self._match(',', ','):
                self._advance()
                _, next_item, _, _ = self._expect('IDENTIFIER')
                items.append(next_item)

        self._expect(']', ']')
        return items

    def _parse_string_list(self) -> List[str]:
        """Faz parsing de lista de strings."""
        self._expect('[', '[')

        items = []
        if not self._match(']', ']'):
            _, first, _, _ = self._expect('STRING')
            items.append(first)

            while self._match(',', ','):
                self._advance()
                _, next_item, _, _ = self._expect('STRING')
                items.append(next_item)

        self._expect(']', ']')
        return items

    def _parse_number_list(self) -> List[int]:
        """Faz parsing de lista de numeros."""
        self._expect('[', '[')

        items = []
        if not self._match(']', ']'):
            _, first, _, _ = self._expect('NUMBER')
            items.append(int(first))

            while self._match(',', ','):
                self._advance()
                _, next_item, _, _ = self._expect('NUMBER')
                items.append(int(next_item))

        self._expect(']', ']')
        return items
