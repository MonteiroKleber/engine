"""
Deterministic error codes for IDL DSL v1.2.2 parser.

Error codes follow the pattern:
- IDL_Lxxx: Lexer errors
- IDL_Pxxx: Parser errors
- IDL_Sxxx: Semantic errors
- IRCS_xxx: IRCS v1 validation errors
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCode(Enum):
    """Deterministic error codes."""

    # Lexer errors (L001-L099)
    IDL_L001_UNEXPECTED_CHAR = "IDL_L001"
    IDL_L002_UNTERMINATED_STRING = "IDL_L002"
    IDL_L003_INVALID_NUMBER = "IDL_L003"
    IDL_L004_INVALID_ESCAPE = "IDL_L004"

    # Parser errors (P001-P199)
    IDL_P001_UNEXPECTED_TOKEN = "IDL_P001"
    IDL_P002_EXPECTED_IDENTIFIER = "IDL_P002"
    IDL_P003_EXPECTED_STRING = "IDL_P003"
    IDL_P004_EXPECTED_NUMBER = "IDL_P004"
    IDL_P005_EXPECTED_LBRACE = "IDL_P005"
    IDL_P006_EXPECTED_RBRACE = "IDL_P006"
    IDL_P007_EXPECTED_COLON = "IDL_P007"
    IDL_P008_EXPECTED_EXPRESSION = "IDL_P008"
    IDL_P009_EXPECTED_SECTION = "IDL_P009"
    IDL_P010_DUPLICATE_SECTION = "IDL_P010"
    IDL_P011_EXPECTED_ARROW = "IDL_P011"
    IDL_P012_EXPECTED_LPAREN = "IDL_P012"
    IDL_P013_EXPECTED_RPAREN = "IDL_P013"
    IDL_P014_EXPECTED_LBRACKET = "IDL_P014"
    IDL_P015_EXPECTED_RBRACKET = "IDL_P015"
    IDL_P016_EXPECTED_FIELD_TYPE = "IDL_P016"
    IDL_P017_INVALID_ACTOR_TYPE = "IDL_P017"
    IDL_P018_INVALID_AUTH_METHOD = "IDL_P018"
    IDL_P019_INVALID_SEVERITY = "IDL_P019"
    IDL_P020_INVALID_HTTP_METHOD = "IDL_P020"
    IDL_P021_INVALID_SCOPE = "IDL_P021"
    IDL_P022_INVALID_BIND_KIND = "IDL_P022"
    IDL_P023_INVALID_HISTORY_ATTR = "IDL_P023"
    IDL_P024_EXPECTED_KEYWORD = "IDL_P024"
    IDL_P025_INVALID_TENANCY = "IDL_P025"
    IDL_P026_INVALID_IDEMPOTENCY = "IDL_P026"
    IDL_P027_EXPECTED_BOOLEAN = "IDL_P027"
    IDL_P028_EXPECTED_DURATION = "IDL_P028"

    # Semantic errors (S001-S199)
    IDL_S001_UNDEFINED_ENTITY = "IDL_S001"
    IDL_S002_UNDEFINED_ACTOR = "IDL_S002"
    IDL_S003_UNDEFINED_WORKFLOW = "IDL_S003"
    IDL_S004_UNDEFINED_TRANSITION = "IDL_S004"
    IDL_S005_UNDEFINED_STATE = "IDL_S005"
    IDL_S006_UNDEFINED_FIELD = "IDL_S006"
    IDL_S007_TYPE_MISMATCH = "IDL_S007"
    IDL_S008_DUPLICATE_ENTITY = "IDL_S008"
    IDL_S009_DUPLICATE_ACTOR = "IDL_S009"
    IDL_S010_DUPLICATE_WORKFLOW = "IDL_S010"
    IDL_S011_DUPLICATE_STATE = "IDL_S011"
    IDL_S012_DUPLICATE_TRANSITION = "IDL_S012"
    IDL_S013_DUPLICATE_FIELD = "IDL_S013"
    IDL_S014_DUPLICATE_INVARIANT = "IDL_S014"
    IDL_S015_DUPLICATE_SOD_RULE = "IDL_S015"
    IDL_S016_DUPLICATE_ENDPOINT = "IDL_S016"
    IDL_S017_HISTORY_NOT_ALLOWED = "IDL_S017"
    IDL_S018_INVALID_REF_PATH = "IDL_S018"
    IDL_S019_NO_INITIAL_STATE = "IDL_S019"
    IDL_S020_MULTIPLE_INITIAL_STATES = "IDL_S020"
    IDL_S021_UNREACHABLE_STATE = "IDL_S021"

    # IRCS validation errors (IRCS_xxx)
    IRCS_INVALID_VERSION = "IRCS_INVALID_VERSION"
    IRCS_MISSING_FIELD = "IRCS_MISSING_FIELD"
    IRCS_INVALID_REF = "IRCS_INVALID_REF"
    IRCS_INVALID_TYPE = "IRCS_INVALID_TYPE"
    IRCS_HISTORY_UNKNOWN_ATTR = "IRCS_HISTORY_UNKNOWN_ATTR"
    IRCS_WORKFLOW_INVALID_STATE = "IRCS_WORKFLOW_INVALID_STATE"
    IRCS_SOD_INVALID_ACTION = "IRCS_SOD_INVALID_ACTION"


@dataclass
class SourceLocation:
    """Source location for error reporting."""

    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None

    def __str__(self) -> str:
        if self.end_line and self.end_line != self.line:
            return f"{self.line}:{self.column}-{self.end_line}:{self.end_column}"
        return f"{self.line}:{self.column}"


class IDLError(Exception):
    """Base exception for IDL errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        location: Optional[SourceLocation] = None,
        context: Optional[str] = None,
    ):
        self.code = code
        self.message = message
        self.location = location
        self.context = context
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """Format error message with location and context."""
        parts = [f"[{self.code.value}]"]
        if self.location:
            parts.append(f" at {self.location}")
        parts.append(f": {self.message}")
        if self.context:
            parts.append(f"\n  | {self.context}")
        return "".join(parts)


class IDLSyntaxError(IDLError):
    """Syntax error during lexing or parsing."""

    pass


class IDLSemanticError(IDLError):
    """Semantic error during validation."""

    pass


class IRCSValidationError(IDLError):
    """IRCS v1 validation error."""

    pass


def make_context_snippet(source: str, line: int, column: int, max_width: int = 60) -> str:
    """Extract context snippet from source for error display."""
    lines = source.splitlines()
    if line < 1 or line > len(lines):
        return ""

    line_text = lines[line - 1]

    # Truncate if too long
    if len(line_text) > max_width:
        start = max(0, column - max_width // 2)
        end = min(len(line_text), start + max_width)
        line_text = ("..." if start > 0 else "") + line_text[start:end] + ("..." if end < len(line_text) else "")
        column = column - start + (3 if start > 0 else 0)

    pointer = " " * (column - 1) + "^"
    return f"{line_text}\n  | {pointer}"
