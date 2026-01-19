"""
Lexer for IDL DSL v1.2.2.

Tokenizes textual IDL input into a stream of tokens.
"""

from typing import Iterator
from .tokens import Token, TokenType, KEYWORDS
from .errors import IDLSyntaxError, ErrorCode, SourceLocation, make_context_snippet


class Lexer:
    """Lexer for IDL DSL v1.2.2."""

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return list of tokens."""
        self.tokens = []
        while not self._at_end():
            self._skip_whitespace_and_comments()
            if self._at_end():
                break
            token = self._next_token()
            if token:
                self.tokens.append(token)

        # Add EOF token
        self.tokens.append(
            Token(TokenType.EOF, None, self.line, self.column, self.line, self.column)
        )
        return self.tokens

    def _at_end(self) -> bool:
        return self.pos >= len(self.source)

    def _peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        if pos >= len(self.source):
            return "\0"
        return self.source[pos]

    def _advance(self) -> str:
        char = self._peek()
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _skip_whitespace_and_comments(self) -> None:
        """Skip whitespace and comments."""
        while not self._at_end():
            char = self._peek()

            # Whitespace
            if char in " \t\r\n":
                self._advance()
                continue

            # Line comment
            if char == "/" and self._peek(1) == "/":
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
                continue

            # Block comment
            if char == "/" and self._peek(1) == "*":
                self._advance()  # /
                self._advance()  # *
                while not self._at_end():
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._advance()  # *
                        self._advance()  # /
                        break
                    self._advance()
                continue

            break

    def _next_token(self) -> Token | None:
        """Read the next token."""
        start_line = self.line
        start_column = self.column
        char = self._peek()

        # String literal
        if char == '"':
            return self._read_string(start_line, start_column)

        # Number
        if char.isdigit() or (char == "-" and self._peek(1).isdigit()):
            return self._read_number(start_line, start_column)

        # Identifier or keyword
        if char.isalpha() or char == "_":
            return self._read_identifier(start_line, start_column)

        # Operators and delimiters
        return self._read_operator(start_line, start_column)

    def _read_string(self, start_line: int, start_column: int) -> Token:
        """Read a string literal."""
        self._advance()  # opening quote
        value_chars: list[str] = []

        while not self._at_end() and self._peek() != '"':
            char = self._peek()
            if char == "\n":
                raise IDLSyntaxError(
                    ErrorCode.IDL_L002_UNTERMINATED_STRING,
                    "Unterminated string literal",
                    SourceLocation(start_line, start_column),
                    make_context_snippet(self.source, start_line, start_column),
                )
            if char == "\\":
                self._advance()
                escape_char = self._peek()
                if escape_char == "n":
                    value_chars.append("\n")
                elif escape_char == "t":
                    value_chars.append("\t")
                elif escape_char == "r":
                    value_chars.append("\r")
                elif escape_char == '"':
                    value_chars.append('"')
                elif escape_char == "\\":
                    value_chars.append("\\")
                else:
                    raise IDLSyntaxError(
                        ErrorCode.IDL_L004_INVALID_ESCAPE,
                        f"Invalid escape sequence: \\{escape_char}",
                        SourceLocation(self.line, self.column),
                        make_context_snippet(self.source, self.line, self.column),
                    )
                self._advance()
            else:
                value_chars.append(char)
                self._advance()

        if self._at_end():
            raise IDLSyntaxError(
                ErrorCode.IDL_L002_UNTERMINATED_STRING,
                "Unterminated string literal",
                SourceLocation(start_line, start_column),
                make_context_snippet(self.source, start_line, start_column),
            )

        self._advance()  # closing quote
        return Token(
            TokenType.STRING,
            "".join(value_chars),
            start_line,
            start_column,
            self.line,
            self.column,
        )

    def _read_number(self, start_line: int, start_column: int) -> Token:
        """Read a number literal (int or float/decimal)."""
        chars: list[str] = []

        # Optional negative sign
        if self._peek() == "-":
            chars.append(self._advance())

        # Integer part
        while not self._at_end() and self._peek().isdigit():
            chars.append(self._advance())

        # Decimal part
        if self._peek() == "." and self._peek(1).isdigit():
            chars.append(self._advance())  # .
            while not self._at_end() and self._peek().isdigit():
                chars.append(self._advance())

        # Duration suffix (s, m, h, d) - store as string for duration literals
        value_str = "".join(chars)
        next_char = self._peek()
        if next_char in "smhd" and not self._peek(1).isalnum():
            suffix = self._advance()
            value_str += suffix
            return Token(
                TokenType.STRING,  # Duration stored as string
                value_str,
                start_line,
                start_column,
                self.line,
                self.column,
            )

        # Convert to number
        try:
            if "." in value_str:
                value = float(value_str)
            else:
                value = int(value_str)
        except ValueError:
            raise IDLSyntaxError(
                ErrorCode.IDL_L003_INVALID_NUMBER,
                f"Invalid number: {value_str}",
                SourceLocation(start_line, start_column),
                make_context_snippet(self.source, start_line, start_column),
            )

        return Token(
            TokenType.NUMBER,
            value,
            start_line,
            start_column,
            self.line,
            self.column,
        )

    def _read_identifier(self, start_line: int, start_column: int) -> Token:
        """Read an identifier or keyword."""
        chars: list[str] = []

        while not self._at_end():
            char = self._peek()
            if char.isalnum() or char == "_" or char == ".":
                # Handle dotted identifiers like "finance.expense.create"
                # But stop at dot if followed by non-alpha (for ref paths handled in parser)
                if char == ".":
                    # Check if next char continues an identifier
                    next_char = self._peek(1)
                    if not (next_char.isalpha() or next_char == "_"):
                        break
                chars.append(self._advance())
            else:
                break

        value = "".join(chars)

        # Check for keywords (case-sensitive)
        token_type = KEYWORDS.get(value)
        if token_type:
            # Handle boolean keywords
            if token_type == TokenType.TRUE:
                return Token(
                    TokenType.BOOLEAN,
                    True,
                    start_line,
                    start_column,
                    self.line,
                    self.column,
                )
            if token_type == TokenType.FALSE:
                return Token(
                    TokenType.BOOLEAN,
                    False,
                    start_line,
                    start_column,
                    self.line,
                    self.column,
                )
            return Token(
                token_type, value, start_line, start_column, self.line, self.column
            )

        # Regular identifier
        return Token(
            TokenType.IDENTIFIER,
            value,
            start_line,
            start_column,
            self.line,
            self.column,
        )

    def _read_operator(self, start_line: int, start_column: int) -> Token:
        """Read an operator or delimiter."""
        char = self._advance()

        # Two-character operators
        if char == "=" and self._peek() == "=":
            self._advance()
            return Token(
                TokenType.EQ, "==", start_line, start_column, self.line, self.column
            )
        if char == "!" and self._peek() == "=":
            self._advance()
            return Token(
                TokenType.NE, "!=", start_line, start_column, self.line, self.column
            )
        if char == ">" and self._peek() == "=":
            self._advance()
            return Token(
                TokenType.GE, ">=", start_line, start_column, self.line, self.column
            )
        if char == "<" and self._peek() == "=":
            self._advance()
            return Token(
                TokenType.LE, "<=", start_line, start_column, self.line, self.column
            )
        if char == "-" and self._peek() == ">":
            self._advance()
            return Token(
                TokenType.ARROW, "->", start_line, start_column, self.line, self.column
            )

        # Single-character operators
        single_char_tokens = {
            ">": TokenType.GT,
            "<": TokenType.LT,
            "{": TokenType.LBRACE,
            "}": TokenType.RBRACE,
            "[": TokenType.LBRACKET,
            "]": TokenType.RBRACKET,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            ":": TokenType.COLON,
            ",": TokenType.COMMA,
            ".": TokenType.DOT,
        }

        if char in single_char_tokens:
            return Token(
                single_char_tokens[char],
                char,
                start_line,
                start_column,
                self.line,
                self.column,
            )

        raise IDLSyntaxError(
            ErrorCode.IDL_L001_UNEXPECTED_CHAR,
            f"Unexpected character: {char!r}",
            SourceLocation(start_line, start_column),
            make_context_snippet(self.source, start_line, start_column),
        )
