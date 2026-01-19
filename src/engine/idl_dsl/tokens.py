"""
Token types for IDL DSL v1.2.2 lexer.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any


class TokenType(Enum):
    """Token types for IDL DSL v1.2.2."""

    # Literals
    IDENTIFIER = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()

    # Section keywords
    SYSTEM = auto()
    ACTORS = auto()
    ENTITIES = auto()
    POLICY_CONTEXT = auto()
    INVARIANTS = auto()
    SEPARATION_OF_DUTIES = auto()
    WORKFLOWS = auto()
    OPERATIONS = auto()

    # Actor types
    HUMAN = auto()
    # SYSTEM is already defined (reused)
    EXTERNAL = auto()

    # Entity keywords
    ENTITY = auto()
    FIELD = auto()
    STORAGE = auto()

    # Field modifiers
    REQUIRED = auto()
    UNIQUE = auto()
    INDEXED = auto()
    DEFAULT = auto()
    MIN = auto()
    MAX = auto()

    # Primitive types
    TYPE_STRING = auto()
    TYPE_TEXT = auto()
    TYPE_INT = auto()
    TYPE_FLOAT = auto()
    TYPE_DECIMAL = auto()
    TYPE_BOOL = auto()
    TYPE_DATETIME = auto()
    TYPE_UUID = auto()
    TYPE_VOID = auto()
    TYPE_ANY = auto()

    # Invariant/SoD keywords
    INVARIANT = auto()
    APPLIES_TO = auto()
    WHEN = auto()
    ASSERT = auto()
    SEVERITY = auto()
    MESSAGE = auto()
    RULE = auto()
    ON = auto()
    FORBID = auto()

    # Severity levels
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()

    # Workflow keywords
    WORKFLOW = auto()
    STATE = auto()
    TRANSITION = auto()
    INITIAL = auto()
    TERMINAL = auto()
    GUARD = auto()
    APPROVALS = auto()
    EFFECTS = auto()
    QUORUM = auto()
    ROLES = auto()
    DISTINCT_ACTORS = auto()
    EXPIRES_IN = auto()

    # Operations keywords
    API = auto()
    ENDPOINT = auto()
    METHOD = auto()
    PATH = auto()
    REQUEST = auto()
    RESPONSE = auto()
    PERMISSION = auto()
    SCOPE = auto()
    IDEMPOTENCY = auto()
    ERRORS = auto()
    BIND = auto()
    KIND = auto()
    DECISION = auto()

    # HTTP methods
    GET = auto()
    POST = auto()
    PUT = auto()
    PATCH = auto()
    DELETE = auto()

    # Scope types
    OWN = auto()
    TENANT = auto()
    DEPARTMENT = auto()
    ALL = auto()

    # Bind kinds
    CREATE = auto()
    READ = auto()
    UPDATE = auto()
    # DELETE already defined
    # TRANSITION already defined
    APPROVAL = auto()

    # Auth methods
    AUTHENTICATION = auto()
    NONE = auto()
    BASIC = auto()
    TOKEN = auto()
    OAUTH2 = auto()
    CERTIFICATE = auto()

    # Other keywords
    NAME = auto()
    DESCRIPTION = auto()
    VERSION = auto()
    DOMAIN = auto()
    OWNER = auto()
    CONTACT = auto()
    TENANCY = auto()
    SINGLE = auto()
    MULTI = auto()
    PERMISSIONS = auto()
    TENANT_FIELD = auto()
    VERSION_FIELD = auto()

    # Expression keywords
    ALWAYS = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    IN = auto()
    TRUE = auto()
    FALSE = auto()

    # history() function (v1.2.2)
    HISTORY = auto()

    # Operators
    EQ = auto()  # ==
    NE = auto()  # !=
    GT = auto()  # >
    GE = auto()  # >=
    LT = auto()  # <
    LE = auto()  # <=

    # Delimiters
    LBRACE = auto()  # {
    RBRACE = auto()  # }
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    COLON = auto()  # :
    COMMA = auto()  # ,
    DOT = auto()  # .
    ARROW = auto()  # ->

    # Special
    EOF = auto()
    NEWLINE = auto()


@dataclass
class Token:
    """A token produced by the lexer."""

    type: TokenType
    value: Any
    line: int
    column: int
    end_line: int
    end_column: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"


# Keyword mappings
KEYWORDS: dict[str, TokenType] = {
    # Sections
    "system": TokenType.SYSTEM,
    "actors": TokenType.ACTORS,
    "entities": TokenType.ENTITIES,
    "policy_context": TokenType.POLICY_CONTEXT,
    "invariants": TokenType.INVARIANTS,
    "separation_of_duties": TokenType.SEPARATION_OF_DUTIES,
    "workflows": TokenType.WORKFLOWS,
    "operations": TokenType.OPERATIONS,
    # Actor types
    "human": TokenType.HUMAN,
    "external": TokenType.EXTERNAL,
    # Entity keywords
    "entity": TokenType.ENTITY,
    "field": TokenType.FIELD,
    "storage": TokenType.STORAGE,
    # Field modifiers
    "required": TokenType.REQUIRED,
    "unique": TokenType.UNIQUE,
    "indexed": TokenType.INDEXED,
    "default": TokenType.DEFAULT,
    "min": TokenType.MIN,
    "max": TokenType.MAX,
    # Primitive types
    "string": TokenType.TYPE_STRING,
    "text": TokenType.TYPE_TEXT,
    "int": TokenType.TYPE_INT,
    "float": TokenType.TYPE_FLOAT,
    "decimal": TokenType.TYPE_DECIMAL,
    "bool": TokenType.TYPE_BOOL,
    "datetime": TokenType.TYPE_DATETIME,
    "uuid": TokenType.TYPE_UUID,
    "void": TokenType.TYPE_VOID,
    "any": TokenType.TYPE_ANY,
    # Invariant/SoD
    "invariant": TokenType.INVARIANT,
    "applies_to": TokenType.APPLIES_TO,
    "when": TokenType.WHEN,
    "assert": TokenType.ASSERT,
    "severity": TokenType.SEVERITY,
    "message": TokenType.MESSAGE,
    "rule": TokenType.RULE,
    "on": TokenType.ON,
    "forbid": TokenType.FORBID,
    # Severity levels
    "low": TokenType.LOW,
    "medium": TokenType.MEDIUM,
    "high": TokenType.HIGH,
    "critical": TokenType.CRITICAL,
    # Workflow
    "workflow": TokenType.WORKFLOW,
    "state": TokenType.STATE,
    "transition": TokenType.TRANSITION,
    "initial": TokenType.INITIAL,
    "terminal": TokenType.TERMINAL,
    "guard": TokenType.GUARD,
    "approvals": TokenType.APPROVALS,
    "effects": TokenType.EFFECTS,
    "quorum": TokenType.QUORUM,
    "roles": TokenType.ROLES,
    "distinct_actors": TokenType.DISTINCT_ACTORS,
    "expires_in": TokenType.EXPIRES_IN,
    # Operations
    "api": TokenType.API,
    "endpoint": TokenType.ENDPOINT,
    "method": TokenType.METHOD,
    "path": TokenType.PATH,
    "request": TokenType.REQUEST,
    "response": TokenType.RESPONSE,
    "permission": TokenType.PERMISSION,
    "scope": TokenType.SCOPE,
    "idempotency": TokenType.IDEMPOTENCY,
    "errors": TokenType.ERRORS,
    "bind": TokenType.BIND,
    "kind": TokenType.KIND,
    "decision": TokenType.DECISION,
    # HTTP methods
    "GET": TokenType.GET,
    "POST": TokenType.POST,
    "PUT": TokenType.PUT,
    "PATCH": TokenType.PATCH,
    "DELETE": TokenType.DELETE,
    # Scope types
    "own": TokenType.OWN,
    "tenant": TokenType.TENANT,
    "department": TokenType.DEPARTMENT,
    "all": TokenType.ALL,
    # Bind kinds
    "create": TokenType.CREATE,
    "read": TokenType.READ,
    "update": TokenType.UPDATE,
    "delete": TokenType.DELETE,
    "approval": TokenType.APPROVAL,
    # Auth methods
    "authentication": TokenType.AUTHENTICATION,
    "none": TokenType.NONE,
    "basic": TokenType.BASIC,
    "token": TokenType.TOKEN,
    "oauth2": TokenType.OAUTH2,
    "certificate": TokenType.CERTIFICATE,
    # Other keywords
    "name": TokenType.NAME,
    "description": TokenType.DESCRIPTION,
    "version": TokenType.VERSION,
    "domain": TokenType.DOMAIN,
    "owner": TokenType.OWNER,
    "contact": TokenType.CONTACT,
    "tenancy": TokenType.TENANCY,
    "single": TokenType.SINGLE,
    "multi": TokenType.MULTI,
    "permissions": TokenType.PERMISSIONS,
    "tenant_field": TokenType.TENANT_FIELD,
    "version_field": TokenType.VERSION_FIELD,
    # Expression keywords
    "always": TokenType.ALWAYS,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "in": TokenType.IN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    # history() function
    "history": TokenType.HISTORY,
}

# Primitive type tokens for lookup
PRIMITIVE_TYPE_TOKENS: set[TokenType] = {
    TokenType.TYPE_STRING,
    TokenType.TYPE_TEXT,
    TokenType.TYPE_INT,
    TokenType.TYPE_FLOAT,
    TokenType.TYPE_DECIMAL,
    TokenType.TYPE_BOOL,
    TokenType.TYPE_DATETIME,
    TokenType.TYPE_UUID,
}

# Type reference tokens (includes void and any)
TYPE_REF_TOKENS: set[TokenType] = PRIMITIVE_TYPE_TOKENS | {
    TokenType.TYPE_VOID,
    TokenType.TYPE_ANY,
    TokenType.IDENTIFIER,
}
