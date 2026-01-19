"""
IDL DSL v1.2.2 Parser and IRCS v1 Emitter

This package provides:
- Lexer: Tokenizes IDL DSL v1.2.2 textual input
- Parser: Recursive descent parser producing typed AST
- IR Emitter: Converts AST to IRCS v1 canonical JSON

Usage:
    from engine.idl_dsl import parse_dsl, emit_ircs

    ir_json = parse_dsl(dsl_text)
    # or step-by-step:
    from engine.idl_dsl.lexer import Lexer
    from engine.idl_dsl.parser import Parser
    from engine.idl_dsl.ircs_emit import IRCSEmitter

    tokens = Lexer(source).tokenize()
    ast = Parser(tokens, source).parse()
    ir = IRCSEmitter(ast, source).emit()
"""

from .errors import IDLError, IDLSyntaxError, IDLSemanticError
from .lexer import Lexer
from .parser import Parser
from .ircs_emit import IRCSEmitter


def parse_dsl(source: str) -> dict:
    """
    Parse IDL DSL v1.2.2 text and return IRCS v1 JSON.

    Args:
        source: IDL DSL v1.2.2 source text (UTF-8)

    Returns:
        IRCS v1 JSON dict

    Raises:
        IDLSyntaxError: On syntax errors
        IDLSemanticError: On semantic validation errors
    """
    tokens = Lexer(source).tokenize()
    ast = Parser(tokens, source).parse()
    return IRCSEmitter(ast, source).emit()


__all__ = [
    "parse_dsl",
    "Lexer",
    "Parser",
    "IRCSEmitter",
    "IDLError",
    "IDLSyntaxError",
    "IDLSemanticError",
]
