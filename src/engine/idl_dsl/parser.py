"""
Recursive descent parser for IDL DSL v1.2.2.

Parses token stream into typed AST.
"""

from typing import Optional, Any
from .tokens import Token, TokenType, PRIMITIVE_TYPE_TOKENS
from .ast_nodes import (
    DocumentNode,
    SystemNode,
    ActorNode,
    ActorKind,
    AuthMethod,
    EntityNode,
    FieldNode,
    FieldModifier,
    StorageNode,
    PolicyContextNode,
    ContextFieldNode,
    InvariantNode,
    SodRuleNode,
    ForbidExpr,
    WorkflowNode,
    StateNode,
    TransitionNode,
    ApprovalsNode,
    EffectNode,
    OperationsNode,
    ApiSection,
    EndpointNode,
    BindSpec,
    BindKind,
    HttpMethod,
    ScopeType,
    IdempotencyMode,
    Severity,
    TenancyMode,
    ExprNode,
    AlwaysExpr,
    LiteralValue,
    RefPath,
    HistoryRef,
    CompareExpr,
    AndExpr,
    OrExpr,
    NotExpr,
)
from .errors import (
    IDLSyntaxError,
    IDLSemanticError,
    ErrorCode,
    SourceLocation,
    make_context_snippet,
)


class Parser:
    """Recursive descent parser for IDL DSL v1.2.2."""

    def __init__(self, tokens: list[Token], source: str):
        self.tokens = tokens
        self.source = source
        self.pos = 0

    def parse(self) -> DocumentNode:
        """Parse the token stream into a DocumentNode AST."""
        doc = DocumentNode()
        seen_sections: set[str] = set()

        while not self._at_end():
            section_name = self._parse_section(doc, seen_sections)
            if section_name:
                seen_sections.add(section_name)

        # CHANGE-1: Semantic validation pass
        self._validate_semantic(doc)

        return doc

    def _validate_semantic(self, doc: DocumentNode) -> None:
        """Validate semantic references in the document.

        CHANGE-1: Second pass validation to check that all references
        are valid (entities, fields, workflows, transitions, actors).
        """
        # Build lookup tables
        entity_names = {e.name for e in doc.entities}
        entity_fields: dict[str, set[str]] = {
            e.name: {f.name for f in e.fields} for e in doc.entities
        }
        actor_ids = {a.id for a in doc.actors}
        workflow_names = {w.name for w in doc.workflows}
        workflow_transitions: dict[str, set[str]] = {
            w.name: {t.name for t in w.transitions} for w in doc.workflows
        }

        # Validate invariants
        for inv in doc.invariants:
            if inv.applies_to and inv.applies_to not in entity_names:
                raise IDLSemanticError(
                    ErrorCode.IDL_S001_UNDEFINED_ENTITY,
                    f"Undefined entity '{inv.applies_to}'. Hint: Defined entities are: {', '.join(sorted(entity_names)) or 'none'}",
                    SourceLocation(inv.line, inv.column),
                )
            # Validate field references in expressions
            self._validate_expr_refs(inv.assert_expr, entity_names, entity_fields)
            if inv.when_expr:
                self._validate_expr_refs(inv.when_expr, entity_names, entity_fields)

        # Validate SoD rules
        for rule in doc.separation_of_duties:
            if rule.on_entity and rule.on_entity not in entity_names:
                raise IDLSemanticError(
                    ErrorCode.IDL_S001_UNDEFINED_ENTITY,
                    f"Undefined entity '{rule.on_entity}'. Hint: Defined entities are: {', '.join(sorted(entity_names)) or 'none'}",
                    SourceLocation(rule.line, rule.column),
                )
            # Validate forbid expression
            if rule.forbid and rule.forbid.when_expr:
                self._validate_expr_refs(rule.forbid.when_expr, entity_names, entity_fields)

        # Validate workflows
        for wf in doc.workflows:
            if wf.on_entity and wf.on_entity not in entity_names:
                raise IDLSemanticError(
                    ErrorCode.IDL_S001_UNDEFINED_ENTITY,
                    f"Undefined entity '{wf.on_entity}'. Hint: Defined entities are: {', '.join(sorted(entity_names)) or 'none'}",
                    SourceLocation(wf.line, wf.column),
                )
            # Validate roles in approvals
            for trans in wf.transitions:
                if trans.approvals:
                    for role in trans.approvals.roles:
                        if role not in actor_ids:
                            raise IDLSemanticError(
                                ErrorCode.IDL_S002_UNDEFINED_ACTOR,
                                f"Undefined actor '{role}'. Hint: Defined actors are: {', '.join(sorted(actor_ids)) or 'none'}",
                                SourceLocation(trans.line, trans.column),
                            )
                # Validate guard expression
                if trans.guard:
                    self._validate_expr_refs(trans.guard, entity_names, entity_fields)

        # Validate operations
        if doc.operations and doc.operations.api:
            for ep in doc.operations.api.endpoints:
                if ep.bind:
                    # Validate entity reference
                    if ep.bind.entity and ep.bind.entity not in entity_names:
                        raise IDLSemanticError(
                            ErrorCode.IDL_S001_UNDEFINED_ENTITY,
                            f"Undefined entity '{ep.bind.entity}'. Hint: Defined entities are: {', '.join(sorted(entity_names)) or 'none'}",
                            SourceLocation(ep.line, ep.column),
                        )
                    # Validate workflow reference
                    if ep.bind.workflow and ep.bind.workflow not in workflow_names:
                        raise IDLSemanticError(
                            ErrorCode.IDL_S003_UNDEFINED_WORKFLOW,
                            f"Undefined workflow '{ep.bind.workflow}'. Hint: Defined workflows are: {', '.join(sorted(workflow_names)) or 'none'}",
                            SourceLocation(ep.line, ep.column),
                        )
                    # Validate transition reference
                    if ep.bind.transition and ep.bind.workflow:
                        wf_transitions = workflow_transitions.get(ep.bind.workflow, set())
                        if ep.bind.transition not in wf_transitions:
                            raise IDLSemanticError(
                                ErrorCode.IDL_S004_UNDEFINED_TRANSITION,
                                f"Undefined transition '{ep.bind.transition}' in workflow '{ep.bind.workflow}'. Hint: Defined transitions are: {', '.join(sorted(wf_transitions)) or 'none'}",
                                SourceLocation(ep.line, ep.column),
                            )

    def _validate_expr_refs(
        self,
        expr: Optional[ExprNode],
        entity_names: set[str],
        entity_fields: dict[str, set[str]],
    ) -> None:
        """Validate entity and field references in expressions."""
        if expr is None:
            return

        if isinstance(expr, RefPath):
            # Parse reference path like "Entity.field"
            parts = expr.path.split(".")
            if len(parts) >= 2:
                entity_name = parts[0]
                # Only validate entity references (not actor.id or context.var)
                if entity_name not in {"actor", "context"} and entity_name in entity_names:
                    field_name = parts[1]
                    if field_name not in entity_fields.get(entity_name, set()):
                        raise IDLSemanticError(
                            ErrorCode.IDL_S006_UNDEFINED_FIELD,
                            f"Undefined field '{field_name}' in entity '{entity_name}'. Hint: Defined fields are: {', '.join(sorted(entity_fields.get(entity_name, set()))) or 'none'}",
                            SourceLocation(expr.line, expr.column),
                        )
                elif entity_name not in {"actor", "context"} and entity_name not in entity_names:
                    # Check if it looks like an entity reference
                    if entity_name[0].isupper():
                        raise IDLSemanticError(
                            ErrorCode.IDL_S001_UNDEFINED_ENTITY,
                            f"Undefined entity '{entity_name}'. Hint: Defined entities are: {', '.join(sorted(entity_names)) or 'none'}",
                            SourceLocation(expr.line, expr.column),
                        )

        elif isinstance(expr, CompareExpr):
            self._validate_expr_refs(expr.lhs, entity_names, entity_fields)
            self._validate_expr_refs(expr.rhs, entity_names, entity_fields)

        elif isinstance(expr, AndExpr):
            for e in expr.exprs:
                self._validate_expr_refs(e, entity_names, entity_fields)

        elif isinstance(expr, OrExpr):
            for e in expr.exprs:
                self._validate_expr_refs(e, entity_names, entity_fields)

        elif isinstance(expr, NotExpr):
            self._validate_expr_refs(expr.expr, entity_names, entity_fields)

    def _at_end(self) -> bool:
        return self._peek().type == TokenType.EOF

    def _peek(self, offset: int = 0) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[pos]

    def _advance(self) -> Token:
        token = self._peek()
        if not self._at_end():
            self.pos += 1
        return token

    def _check(self, *types: TokenType) -> bool:
        return self._peek().type in types

    def _match(self, *types: TokenType) -> Token | None:
        if self._check(*types):
            return self._advance()
        return None

    def _expect_identifier_or_keyword(self) -> Token:
        """Accept identifier or keyword that can be used as identifier (e.g., 'version')."""
        token = self._peek()
        # Accept both identifiers and keywords that can serve as field names
        if token.type == TokenType.IDENTIFIER:
            return self._advance()
        # Accept keywords that are commonly used as field/variable names
        keyword_as_identifier = {
            TokenType.VERSION,
            TokenType.STATE,
            TokenType.NAME,
            TokenType.DESCRIPTION,
            TokenType.DOMAIN,
            TokenType.OWNER,
            TokenType.CONTACT,
            TokenType.MESSAGE,
            TokenType.KIND,
            TokenType.SCOPE,
            TokenType.TRANSITION,
            TokenType.APPROVAL,
            TokenType.WORKFLOW,
        }
        if token.type in keyword_as_identifier:
            self._advance()
            return Token(
                TokenType.IDENTIFIER,
                token.value,
                token.line,
                token.column,
                token.end_line,
                token.end_column,
            )
        raise self._error(
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            f"Expected identifier, got {token.type.name}",
        )

    def _expect(self, token_type: TokenType, error_code: ErrorCode, message: str) -> Token:
        token = self._match(token_type)
        if token is None:
            current = self._peek()
            raise IDLSyntaxError(
                error_code,
                message,
                SourceLocation(current.line, current.column),
                make_context_snippet(self.source, current.line, current.column),
            )
        return token

    def _error(self, code: ErrorCode, message: str, token: Token | None = None) -> IDLSyntaxError:
        if token is None:
            token = self._peek()
        return IDLSyntaxError(
            code,
            message,
            SourceLocation(token.line, token.column),
            make_context_snippet(self.source, token.line, token.column),
        )

    # ============================================================
    # Section Parsing
    # ============================================================

    def _parse_section(self, doc: DocumentNode, seen: set[str]) -> str | None:
        """Parse a top-level section and update the document."""
        token = self._peek()

        if token.type == TokenType.SYSTEM:
            if "system" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'system' section")
            doc.system = self._parse_system_section()
            return "system"

        if token.type == TokenType.ACTORS:
            if "actors" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'actors' section")
            doc.actors = self._parse_actors_section()
            return "actors"

        if token.type == TokenType.ENTITIES:
            if "entities" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'entities' section")
            doc.entities = self._parse_entities_section()
            return "entities"

        if token.type == TokenType.POLICY_CONTEXT:
            if "policy_context" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'policy_context' section")
            doc.policy_context = self._parse_policy_context_section()
            return "policy_context"

        if token.type == TokenType.INVARIANTS:
            if "invariants" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'invariants' section")
            doc.invariants = self._parse_invariants_section()
            return "invariants"

        if token.type == TokenType.SEPARATION_OF_DUTIES:
            if "separation_of_duties" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'separation_of_duties' section")
            doc.separation_of_duties = self._parse_sod_section()
            return "separation_of_duties"

        if token.type == TokenType.WORKFLOWS:
            if "workflows" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'workflows' section")
            doc.workflows = self._parse_workflows_section()
            return "workflows"

        if token.type == TokenType.OPERATIONS:
            if "operations" in seen:
                raise self._error(ErrorCode.IDL_P010_DUPLICATE_SECTION, "Duplicate 'operations' section")
            doc.operations = self._parse_operations_section()
            return "operations"

        if token.type == TokenType.EOF:
            return None

        raise self._error(
            ErrorCode.IDL_P009_EXPECTED_SECTION,
            f"Expected section keyword, got {token.type.name}",
        )

    # ============================================================
    # System Section
    # ============================================================

    def _parse_system_section(self) -> SystemNode:
        """Parse: system Identifier { properties }"""
        self._advance()  # 'system'
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected system identifier",
        )
        node = SystemNode(id=id_token.value, line=id_token.line, column=id_token.column)

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            self._parse_system_property(node)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_system_property(self, node: SystemNode) -> None:
        """Parse a single system property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.NAME:
            node.name = self._parse_string_value()
        elif token.type == TokenType.DESCRIPTION:
            node.description = self._parse_string_value()
        elif token.type == TokenType.VERSION:
            node.version = self._parse_version_string()
        elif token.type == TokenType.DOMAIN:
            node.domain = self._parse_string_value()
        elif token.type == TokenType.OWNER:
            node.owner = self._parse_string_value()
        elif token.type == TokenType.CONTACT:
            node.contact = self._parse_string_value()
        elif token.type == TokenType.TENANCY:
            node.tenancy = self._parse_tenancy_mode()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected system property: {token.value}",
                token,
            )

    def _parse_string_value(self) -> str:
        """Parse a string literal value."""
        token = self._expect(
            TokenType.STRING,
            ErrorCode.IDL_P003_EXPECTED_STRING,
            "Expected string literal",
        )
        return token.value

    def _parse_version_string(self) -> str:
        """Parse version (can be NUMBER.NUMBER.NUMBER or identifier)."""
        parts = []
        # First part
        if self._check(TokenType.NUMBER):
            parts.append(str(int(self._advance().value)))
        elif self._check(TokenType.IDENTIFIER):
            return self._advance().value
        else:
            raise self._error(ErrorCode.IDL_P004_EXPECTED_NUMBER, "Expected version number")

        # Additional parts separated by dots
        while self._match(TokenType.DOT):
            if self._check(TokenType.NUMBER):
                parts.append(str(int(self._advance().value)))
            else:
                raise self._error(ErrorCode.IDL_P004_EXPECTED_NUMBER, "Expected version number")

        return ".".join(parts)

    def _parse_tenancy_mode(self) -> TenancyMode:
        """Parse tenancy mode (single/multi)."""
        if self._match(TokenType.SINGLE):
            return TenancyMode.SINGLE
        if self._match(TokenType.MULTI):
            return TenancyMode.MULTI
        raise self._error(
            ErrorCode.IDL_P025_INVALID_TENANCY,
            f"Invalid tenancy mode. Hint: Valid values are: single, multi",
        )

    # ============================================================
    # Actors Section
    # ============================================================

    def _parse_actors_section(self) -> list[ActorNode]:
        """Parse: actors { actor_definitions }"""
        self._advance()  # 'actors'
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        actors = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            actors.append(self._parse_actor_definition())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return actors

    def _parse_actor_definition(self) -> ActorNode:
        """Parse: actor_type Identifier { properties }"""
        kind = self._parse_actor_kind()
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected actor identifier",
        )
        node = ActorNode(id=id_token.value, kind=kind, line=id_token.line, column=id_token.column)

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            self._parse_actor_property(node)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_actor_kind(self) -> ActorKind:
        """Parse actor type keyword."""
        if self._match(TokenType.HUMAN):
            return ActorKind.HUMAN
        if self._match(TokenType.SYSTEM):
            return ActorKind.SYSTEM
        if self._match(TokenType.EXTERNAL):
            return ActorKind.EXTERNAL
        raise self._error(
            ErrorCode.IDL_P017_INVALID_ACTOR_TYPE,
            f"Invalid actor type. Hint: Valid types are: human, system, external",
        )

    def _parse_actor_property(self, node: ActorNode) -> None:
        """Parse a single actor property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.NAME:
            node.name = self._parse_string_value()
        elif token.type == TokenType.DESCRIPTION:
            node.description = self._parse_string_value()
        elif token.type == TokenType.AUTHENTICATION:
            node.auth = self._parse_auth_method()
        elif token.type == TokenType.PERMISSIONS:
            node.permissions = self._parse_identifier_list()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected actor property: {token.value}",
                token,
            )

    def _parse_auth_method(self) -> AuthMethod:
        """Parse authentication method."""
        if self._match(TokenType.NONE):
            return AuthMethod.NONE
        if self._match(TokenType.BASIC):
            return AuthMethod.BASIC
        if self._match(TokenType.TOKEN):
            return AuthMethod.TOKEN
        if self._match(TokenType.OAUTH2):
            return AuthMethod.OAUTH2
        if self._match(TokenType.CERTIFICATE):
            return AuthMethod.CERTIFICATE
        raise self._error(
            ErrorCode.IDL_P018_INVALID_AUTH_METHOD,
            f"Invalid authentication method. Hint: Valid values are: none, basic, token, oauth2, certificate",
        )

    def _parse_identifier_list(self) -> list[str]:
        """Parse: [ identifier, identifier, ... ]"""
        self._expect(TokenType.LBRACKET, ErrorCode.IDL_P014_EXPECTED_LBRACKET, "Expected '['")
        items = []

        if not self._check(TokenType.RBRACKET):
            items.append(self._parse_dotted_identifier())
            while self._match(TokenType.COMMA):
                items.append(self._parse_dotted_identifier())

        self._expect(TokenType.RBRACKET, ErrorCode.IDL_P015_EXPECTED_RBRACKET, "Expected ']'")
        return items

    def _parse_dotted_identifier(self) -> str:
        """Parse potentially dotted identifier like 'finance.expense.create'."""
        token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected identifier",
        )
        # The lexer already handles dotted identifiers
        return token.value

    # ============================================================
    # Entities Section
    # ============================================================

    def _parse_entities_section(self) -> list[EntityNode]:
        """Parse: entities { entity_definitions }"""
        self._advance()  # 'entities'
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        entities = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            entities.append(self._parse_entity_definition())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return entities

    def _parse_entity_definition(self) -> EntityNode:
        """Parse: entity Identifier { members }"""
        self._expect(TokenType.ENTITY, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'entity'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected entity name",
        )
        node = EntityNode(name=id_token.value, line=id_token.line, column=id_token.column)

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.STORAGE):
                node.storage = self._parse_storage_definition()
            elif self._check(TokenType.FIELD):
                node.fields.append(self._parse_field_definition())
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    "Expected 'field' or 'storage'",
                )

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_storage_definition(self) -> StorageNode:
        """Parse: storage { properties }"""
        self._advance()  # 'storage'
        node = StorageNode()
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            token = self._advance()
            self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

            if token.type == TokenType.TENANT_FIELD:
                id_tok = self._expect_identifier_or_keyword()
                node.tenant_field = id_tok.value
            elif token.type == TokenType.VERSION_FIELD:
                id_tok = self._expect_identifier_or_keyword()
                node.version_field = id_tok.value
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    f"Unexpected storage property: {token.value}",
                    token,
                )

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_field_definition(self) -> FieldNode:
        """Parse: field Identifier : Type modifiers"""
        self._advance()  # 'field'
        id_token = self._expect_identifier_or_keyword()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")
        type_name = self._parse_field_type()

        node = FieldNode(
            name=id_token.value,
            type_name=type_name,
            line=id_token.line,
            column=id_token.column,
        )

        # Parse modifiers until next field/storage/rbrace
        while self._check(
            TokenType.REQUIRED,
            TokenType.UNIQUE,
            TokenType.INDEXED,
            TokenType.DEFAULT,
            TokenType.MIN,
            TokenType.MAX,
        ):
            node.modifiers.append(self._parse_field_modifier())

        return node

    def _parse_field_type(self) -> str:
        """Parse field type (primitive or identifier)."""
        token = self._peek()

        if token.type in PRIMITIVE_TYPE_TOKENS:
            self._advance()
            # Map token type to string
            type_map = {
                TokenType.TYPE_STRING: "string",
                TokenType.TYPE_TEXT: "text",
                TokenType.TYPE_INT: "int",
                TokenType.TYPE_FLOAT: "float",
                TokenType.TYPE_DECIMAL: "decimal",
                TokenType.TYPE_BOOL: "bool",
                TokenType.TYPE_DATETIME: "datetime",
                TokenType.TYPE_UUID: "uuid",
            }
            return type_map[token.type]

        if token.type == TokenType.IDENTIFIER:
            self._advance()
            return token.value

        raise self._error(
            ErrorCode.IDL_P016_EXPECTED_FIELD_TYPE,
            f"Expected field type, got {token.type.name}. Hint: Valid types are: string, text, int, float, decimal, bool, datetime, uuid, or an entity name",
        )

    def _parse_field_modifier(self) -> FieldModifier:
        """Parse a field modifier."""
        token = self._advance()

        if token.type == TokenType.REQUIRED:
            return FieldModifier(kind="required", line=token.line, column=token.column)
        if token.type == TokenType.UNIQUE:
            return FieldModifier(kind="unique", line=token.line, column=token.column)
        if token.type == TokenType.INDEXED:
            return FieldModifier(kind="indexed", line=token.line, column=token.column)
        if token.type == TokenType.DEFAULT:
            self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")
            value = self._parse_literal_value()
            self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
            return FieldModifier(kind="default", value=value, line=token.line, column=token.column)
        if token.type == TokenType.MIN:
            self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")
            value = self._parse_number_value()
            self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
            return FieldModifier(kind="min", value=value, line=token.line, column=token.column)
        if token.type == TokenType.MAX:
            self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")
            value = self._parse_number_value()
            self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
            return FieldModifier(kind="max", value=value, line=token.line, column=token.column)

        raise self._error(
            ErrorCode.IDL_P024_EXPECTED_KEYWORD,
            f"Unexpected modifier: {token.value}",
            token,
        )

    def _parse_literal_value(self) -> Any:
        """Parse any literal value (string, number, boolean)."""
        if self._check(TokenType.STRING):
            return self._advance().value
        if self._check(TokenType.NUMBER):
            return self._advance().value
        if self._check(TokenType.BOOLEAN):
            return self._advance().value
        raise self._error(ErrorCode.IDL_P008_EXPECTED_EXPRESSION, "Expected literal value")

    def _parse_number_value(self) -> float | int:
        """Parse a number value."""
        token = self._expect(
            TokenType.NUMBER,
            ErrorCode.IDL_P004_EXPECTED_NUMBER,
            "Expected number",
        )
        return token.value

    # ============================================================
    # Policy Context Section
    # ============================================================

    def _parse_policy_context_section(self) -> PolicyContextNode:
        """Parse: policy_context { fields }"""
        self._advance()  # 'policy_context'
        node = PolicyContextNode()
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            node.fields.append(self._parse_context_field())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_context_field(self) -> ContextFieldNode:
        """Parse: field Identifier : Type [required] [default(value)]"""
        self._expect(TokenType.FIELD, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'field'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected field name",
        )
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")
        type_name = self._parse_field_type()

        node = ContextFieldNode(
            name=id_token.value,
            type_name=type_name,
            line=id_token.line,
            column=id_token.column,
        )

        # Optional modifiers
        if self._match(TokenType.REQUIRED):
            node.required = True
        if self._match(TokenType.DEFAULT):
            self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")
            node.default_value = self._parse_literal_value()
            self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")

        return node

    # ============================================================
    # Invariants Section
    # ============================================================

    def _parse_invariants_section(self) -> list[InvariantNode]:
        """Parse: invariants { invariant_definitions }"""
        self._advance()  # 'invariants'
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        invariants = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            invariants.append(self._parse_invariant_definition())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return invariants

    def _parse_invariant_definition(self) -> InvariantNode:
        """Parse: invariant Identifier { properties }"""
        self._expect(TokenType.INVARIANT, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'invariant'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected invariant name",
        )

        node = InvariantNode(
            name=id_token.value,
            applies_to="",
            when_expr=AlwaysExpr(),
            assert_expr=AlwaysExpr(),
            line=id_token.line,
            column=id_token.column,
        )

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            self._parse_invariant_property(node)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_invariant_property(self, node: InvariantNode) -> None:
        """Parse an invariant property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.APPLIES_TO:
            id_tok = self._expect(
                TokenType.IDENTIFIER,
                ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                "Expected entity name",
            )
            node.applies_to = id_tok.value
        elif token.type == TokenType.WHEN:
            node.when_expr = self._parse_predicate_expr()
        elif token.type == TokenType.ASSERT:
            node.assert_expr = self._parse_predicate_expr()
        elif token.type == TokenType.SEVERITY:
            node.severity = self._parse_severity()
        elif token.type == TokenType.MESSAGE:
            node.message = self._parse_string_value()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected invariant property: {token.value}",
                token,
            )

    def _parse_severity(self) -> Severity:
        """Parse severity level."""
        if self._match(TokenType.LOW):
            return Severity.LOW
        if self._match(TokenType.MEDIUM):
            return Severity.MEDIUM
        if self._match(TokenType.HIGH):
            return Severity.HIGH
        if self._match(TokenType.CRITICAL):
            return Severity.CRITICAL
        raise self._error(
            ErrorCode.IDL_P019_INVALID_SEVERITY,
            f"Invalid severity level. Hint: Valid values are: low, medium, high, critical",
        )

    # ============================================================
    # Separation of Duties Section
    # ============================================================

    def _parse_sod_section(self) -> list[SodRuleNode]:
        """Parse: separation_of_duties { rules }"""
        self._advance()  # 'separation_of_duties'
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        rules = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            rules.append(self._parse_sod_rule())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return rules

    def _parse_sod_rule(self) -> SodRuleNode:
        """Parse: rule Identifier { properties }"""
        self._expect(TokenType.RULE, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'rule'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected rule name",
        )

        node = SodRuleNode(
            name=id_token.value,
            on_entity="",
            forbid=ForbidExpr(action="", when_expr=AlwaysExpr()),
            line=id_token.line,
            column=id_token.column,
        )

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            self._parse_sod_property(node)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_sod_property(self, node: SodRuleNode) -> None:
        """Parse a SoD rule property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.ON:
            id_tok = self._expect(
                TokenType.IDENTIFIER,
                ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                "Expected entity name",
            )
            node.on_entity = id_tok.value
        elif token.type == TokenType.FORBID:
            node.forbid = self._parse_forbid_expr()
        elif token.type == TokenType.SEVERITY:
            node.severity = self._parse_severity()
        elif token.type == TokenType.MESSAGE:
            node.message = self._parse_string_value()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected SoD property: {token.value}",
                token,
            )

    def _parse_forbid_expr(self) -> ForbidExpr:
        """Parse: Action when predicate"""
        action_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected action name",
        )
        self._expect(TokenType.WHEN, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'when'")
        when_expr = self._parse_predicate_expr()

        return ForbidExpr(
            action=action_token.value,
            when_expr=when_expr,
            line=action_token.line,
            column=action_token.column,
        )

    # ============================================================
    # Workflows Section
    # ============================================================

    def _parse_workflows_section(self) -> list[WorkflowNode]:
        """Parse: workflows { workflow_definitions }"""
        self._advance()  # 'workflows'
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        workflows = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            workflows.append(self._parse_workflow_definition())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return workflows

    def _parse_workflow_definition(self) -> WorkflowNode:
        """Parse: workflow Identifier on Entity { members }"""
        self._expect(TokenType.WORKFLOW, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'workflow'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected workflow name",
        )
        self._expect(TokenType.ON, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'on'")
        entity_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected entity name",
        )

        node = WorkflowNode(
            name=id_token.value,
            on_entity=entity_token.value,
            line=id_token.line,
            column=id_token.column,
        )

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.STATE):
                node.states.append(self._parse_workflow_state())
            elif self._check(TokenType.TRANSITION):
                node.transitions.append(self._parse_workflow_transition())
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    "Expected 'state' or 'transition'",
                )

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_workflow_state(self) -> StateNode:
        """Parse: state Identifier [{ properties }]"""
        self._advance()  # 'state'
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected state name",
        )
        node = StateNode(name=id_token.value, line=id_token.line, column=id_token.column)

        # Optional block
        if self._match(TokenType.LBRACE):
            while not self._check(TokenType.RBRACE, TokenType.EOF):
                self._parse_state_property(node)
            self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")

        return node

    def _parse_state_property(self, node: StateNode) -> None:
        """Parse state property (initial/terminal)."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.INITIAL:
            node.initial = self._parse_boolean_value()
        elif token.type == TokenType.TERMINAL:
            node.terminal = self._parse_boolean_value()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected state property: {token.value}",
                token,
            )

    def _parse_boolean_value(self) -> bool:
        """Parse boolean value."""
        token = self._expect(
            TokenType.BOOLEAN,
            ErrorCode.IDL_P027_EXPECTED_BOOLEAN,
            "Expected 'true' or 'false'",
        )
        return token.value

    def _parse_workflow_transition(self) -> TransitionNode:
        """Parse: transition Identifier : From -> To [{ properties }]"""
        self._advance()  # 'transition'
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected transition name",
        )
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")
        from_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected from state",
        )
        self._expect(TokenType.ARROW, ErrorCode.IDL_P011_EXPECTED_ARROW, "Expected '->'")
        to_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected to state",
        )

        node = TransitionNode(
            name=id_token.value,
            from_state=from_token.value,
            to_state=to_token.value,
            line=id_token.line,
            column=id_token.column,
        )

        # Optional block
        if self._match(TokenType.LBRACE):
            while not self._check(TokenType.RBRACE, TokenType.EOF):
                self._parse_transition_property(node)
            self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")

        return node

    def _parse_transition_property(self, node: TransitionNode) -> None:
        """Parse transition property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.GUARD:
            node.guard = self._parse_predicate_expr()
        elif token.type == TokenType.APPROVALS:
            node.approvals = self._parse_approvals_block()
        elif token.type == TokenType.EFFECTS:
            node.effects = self._parse_effects_block()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected transition property: {token.value}",
                token,
            )

    def _parse_approvals_block(self) -> ApprovalsNode:
        """Parse: { quorum, roles, ... }"""
        node = ApprovalsNode()
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            token = self._advance()
            self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

            if token.type == TokenType.QUORUM:
                node.quorum = int(self._parse_number_value())
            elif token.type == TokenType.ROLES:
                node.roles = self._parse_identifier_list()
            elif token.type == TokenType.DISTINCT_ACTORS:
                node.distinct_actors = self._parse_boolean_value()
            elif token.type == TokenType.EXPIRES_IN:
                node.expires_in = self._parse_duration_value()
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    f"Unexpected approvals property: {token.value}",
                    token,
                )

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_duration_value(self) -> str:
        """Parse duration like 48h."""
        # Duration is tokenized as STRING (number + suffix)
        token = self._peek()
        if token.type == TokenType.STRING:
            self._advance()
            return token.value
        if token.type == TokenType.NUMBER:
            # Number followed by identifier for unit
            num = self._advance().value
            unit_token = self._peek()
            if unit_token.type == TokenType.IDENTIFIER and unit_token.value in ("s", "m", "h", "d"):
                self._advance()
                return f"{num}{unit_token.value}"
            return str(num)
        raise self._error(ErrorCode.IDL_P028_EXPECTED_DURATION, "Expected duration (e.g., 48h)")

    def _parse_effects_block(self) -> list[EffectNode]:
        """Parse: [ effect(...), effect(...) ]"""
        self._expect(TokenType.LBRACKET, ErrorCode.IDL_P014_EXPECTED_LBRACKET, "Expected '['")
        effects = []

        if not self._check(TokenType.RBRACKET):
            effects.append(self._parse_effect_step())
            while self._match(TokenType.COMMA):
                effects.append(self._parse_effect_step())

        self._expect(TokenType.RBRACKET, ErrorCode.IDL_P015_EXPECTED_RBRACKET, "Expected ']'")
        return effects

    def _parse_effect_step(self) -> EffectNode:
        """Parse: effect_name(args)"""
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected effect name",
        )
        node = EffectNode(name=id_token.value, line=id_token.line, column=id_token.column)

        self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")

        if not self._check(TokenType.RPAREN):
            node.args.append(self._parse_literal_value())
            while self._match(TokenType.COMMA):
                node.args.append(self._parse_literal_value())

        self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
        return node

    # ============================================================
    # Operations Section
    # ============================================================

    def _parse_operations_section(self) -> OperationsNode:
        """Parse: operations { api { ... } }"""
        self._advance()  # 'operations'
        node = OperationsNode()
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.API):
                node.api = self._parse_api_section()
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    "Expected 'api'",
                )

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_api_section(self) -> ApiSection:
        """Parse: api { endpoints }"""
        self._advance()  # 'api'
        node = ApiSection()
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            node.endpoints.append(self._parse_endpoint_definition())

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_endpoint_definition(self) -> EndpointNode:
        """Parse: endpoint Identifier { properties }"""
        self._expect(TokenType.ENDPOINT, ErrorCode.IDL_P024_EXPECTED_KEYWORD, "Expected 'endpoint'")
        id_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
            "Expected endpoint name",
        )

        node = EndpointNode(id=id_token.value, line=id_token.line, column=id_token.column)

        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            self._parse_endpoint_property(node)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")
        return node

    def _parse_endpoint_property(self, node: EndpointNode) -> None:
        """Parse endpoint property."""
        token = self._advance()
        self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

        if token.type == TokenType.METHOD:
            node.method = self._parse_http_method()
        elif token.type == TokenType.PATH:
            node.path = self._parse_string_value()
            # CHANGE-5: Validate and extract path parameters
            node.path_params = self._validate_path_template(node.path, token)
        elif token.type == TokenType.REQUEST:
            node.request_type = self._parse_type_ref()
        elif token.type == TokenType.RESPONSE:
            node.response_type = self._parse_type_ref()
        elif token.type == TokenType.PERMISSION:
            node.permission = self._parse_dotted_identifier()
        elif token.type == TokenType.SCOPE:
            node.scope = self._parse_scope_type()
        elif token.type == TokenType.IDEMPOTENCY:
            node.idempotency = self._parse_idempotency_mode()
        elif token.type == TokenType.ERRORS:
            node.errors = self._parse_error_list()
        elif token.type == TokenType.BIND:
            node.bind = self._parse_bind_spec()
        else:
            raise self._error(
                ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                f"Unexpected endpoint property: {token.value}",
                token,
            )

    def _parse_http_method(self) -> HttpMethod:
        """Parse HTTP method."""
        if self._match(TokenType.GET):
            return HttpMethod.GET
        if self._match(TokenType.POST):
            return HttpMethod.POST
        if self._match(TokenType.PUT):
            return HttpMethod.PUT
        if self._match(TokenType.PATCH):
            return HttpMethod.PATCH
        if self._match(TokenType.DELETE):
            return HttpMethod.DELETE
        raise self._error(
            ErrorCode.IDL_P020_INVALID_HTTP_METHOD,
            f"Invalid HTTP method. Hint: Valid values are: GET, POST, PUT, PATCH, DELETE",
        )

    def _parse_type_ref(self) -> str:
        """Parse type reference (identifier, void, any)."""
        if self._match(TokenType.TYPE_VOID):
            return "void"
        if self._match(TokenType.TYPE_ANY):
            return "any"
        if self._check(TokenType.IDENTIFIER):
            return self._advance().value
        raise self._error(
            ErrorCode.IDL_P016_EXPECTED_FIELD_TYPE,
            "Expected type reference",
        )

    def _parse_scope_type(self) -> ScopeType:
        """Parse scope type."""
        if self._match(TokenType.OWN):
            return ScopeType.OWN
        if self._match(TokenType.TENANT):
            return ScopeType.TENANT
        if self._match(TokenType.DEPARTMENT):
            return ScopeType.DEPARTMENT
        if self._match(TokenType.ALL):
            return ScopeType.ALL
        raise self._error(
            ErrorCode.IDL_P021_INVALID_SCOPE,
            f"Invalid scope type. Hint: Valid values are: own, tenant, department, all",
        )

    def _parse_idempotency_mode(self) -> IdempotencyMode:
        """Parse idempotency mode."""
        if self._match(TokenType.REQUIRED):
            return IdempotencyMode.REQUIRED
        if self._check(TokenType.IDENTIFIER) and self._peek().value == "optional":
            self._advance()
            return IdempotencyMode.OPTIONAL
        if self._match(TokenType.NONE):
            return IdempotencyMode.NONE
        raise self._error(
            ErrorCode.IDL_P026_INVALID_IDEMPOTENCY,
            f"Invalid idempotency mode. Hint: Valid values are: required, optional, none",
        )

    def _parse_error_list(self) -> list[int]:
        """Parse: [ 400, 401, 403 ]"""
        self._expect(TokenType.LBRACKET, ErrorCode.IDL_P014_EXPECTED_LBRACKET, "Expected '['")
        errors = []

        if not self._check(TokenType.RBRACKET):
            errors.append(int(self._parse_number_value()))
            while self._match(TokenType.COMMA):
                errors.append(int(self._parse_number_value()))

        self._expect(TokenType.RBRACKET, ErrorCode.IDL_P015_EXPECTED_RBRACKET, "Expected ']'")
        return errors

    def _parse_bind_spec(self) -> BindSpec:
        """Parse: { entity: X, kind: Y, ... }"""
        self._expect(TokenType.LBRACE, ErrorCode.IDL_P005_EXPECTED_LBRACE, "Expected '{'")

        entity = ""
        kind = BindKind.READ
        workflow = None
        transition = None
        decision = None

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            token = self._advance()
            self._expect(TokenType.COLON, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected ':'")

            if token.type == TokenType.ENTITY:
                entity = self._expect(
                    TokenType.IDENTIFIER,
                    ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                    "Expected entity name",
                ).value
            elif token.type == TokenType.KIND:
                kind = self._parse_bind_kind()
            elif token.type == TokenType.WORKFLOW:
                workflow = self._expect(
                    TokenType.IDENTIFIER,
                    ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                    "Expected workflow name",
                ).value
            elif token.type == TokenType.TRANSITION:
                transition = self._expect(
                    TokenType.IDENTIFIER,
                    ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                    "Expected transition name",
                ).value
            elif token.type == TokenType.DECISION:
                decision = self._parse_string_value()
            else:
                raise self._error(
                    ErrorCode.IDL_P024_EXPECTED_KEYWORD,
                    f"Unexpected bind property: {token.value}",
                    token,
                )

            # Optional comma
            self._match(TokenType.COMMA)

        self._expect(TokenType.RBRACE, ErrorCode.IDL_P006_EXPECTED_RBRACE, "Expected '}'")

        return BindSpec(
            entity=entity,
            kind=kind,
            workflow=workflow,
            transition=transition,
            decision=decision,
        )

    def _parse_bind_kind(self) -> BindKind:
        """Parse bind kind."""
        if self._match(TokenType.CREATE):
            return BindKind.CREATE
        if self._match(TokenType.READ):
            return BindKind.READ
        if self._match(TokenType.UPDATE):
            return BindKind.UPDATE
        if self._match(TokenType.DELETE):
            return BindKind.DELETE
        if self._match(TokenType.TRANSITION):
            return BindKind.TRANSITION
        if self._match(TokenType.APPROVAL):
            return BindKind.APPROVAL
        raise self._error(
            ErrorCode.IDL_P022_INVALID_BIND_KIND,
            f"Invalid bind kind. Hint: Valid values are: create, read, update, delete, transition, approval",
        )

    def _validate_path_template(self, path: str, token: Token) -> list[str]:
        """Validate path template and extract path parameters.

        CHANGE-5: Path parameters must match pattern {param_name} where
        param_name is lowercase with underscores only.
        """
        import re
        params = []
        # Find all {param} patterns
        pattern = r'\{([^}]+)\}'
        for match in re.finditer(pattern, path):
            param = match.group(1)
            # Validate parameter name: must be lowercase with underscores only
            if not re.match(r'^[a-z][a-z0-9_]*$', param):
                raise self._error(
                    ErrorCode.IDL_P029_INVALID_PATH_TEMPLATE,
                    f"Invalid path parameter '{{{param}}}'. Hint: Path parameters must match pattern {{param_name}} where param_name is lowercase letters, digits, and underscores (starting with a letter)",
                    token,
                )
            params.append(param)
        return params

    # ============================================================
    # Expression Parsing (Predicate AST)
    # ============================================================

    def _parse_predicate_expr(self) -> ExprNode:
        """Parse a predicate expression."""
        if self._match(TokenType.ALWAYS):
            return AlwaysExpr(line=self._peek(-1).line, column=self._peek(-1).column)
        return self._parse_or_expr()

    def _peek_behind(self, offset: int = 1) -> Token:
        """Peek at a previous token."""
        pos = self.pos - offset
        if pos < 0:
            return self.tokens[0]
        return self.tokens[pos]

    def _parse_or_expr(self) -> ExprNode:
        """Parse: and_expr { 'or' and_expr }"""
        left = self._parse_and_expr()

        while self._match(TokenType.OR):
            right = self._parse_and_expr()
            if isinstance(left, OrExpr):
                left.exprs.append(right)
            else:
                left = OrExpr(exprs=[left, right], line=left.line, column=left.column)

        return left

    def _parse_and_expr(self) -> ExprNode:
        """Parse: not_expr { 'and' not_expr }"""
        left = self._parse_not_expr()

        while self._match(TokenType.AND):
            right = self._parse_not_expr()
            if isinstance(left, AndExpr):
                left.exprs.append(right)
            else:
                left = AndExpr(exprs=[left, right], line=left.line, column=left.column)

        return left

    def _parse_not_expr(self) -> ExprNode:
        """Parse: ['not'] atom_expr"""
        if self._match(TokenType.NOT):
            token = self._peek_behind()
            expr = self._parse_atom_expr()
            return NotExpr(expr=expr, line=token.line, column=token.column)
        return self._parse_atom_expr()

    def _parse_atom_expr(self) -> ExprNode:
        """Parse: comparison | '(' predicate_expr ')'"""
        if self._match(TokenType.LPAREN):
            expr = self._parse_predicate_expr()
            self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
            return expr

        return self._parse_comparison()

    def _parse_comparison(self) -> ExprNode:
        """Parse: value_ref comparator value_ref"""
        lhs = self._parse_value_ref()

        # Check for comparison operator
        op = None
        if self._match(TokenType.EQ):
            op = "=="
        elif self._match(TokenType.NE):
            op = "!="
        elif self._match(TokenType.GT):
            op = ">"
        elif self._match(TokenType.GE):
            op = ">="
        elif self._match(TokenType.LT):
            op = "<"
        elif self._match(TokenType.LE):
            op = "<="
        elif self._match(TokenType.IN):
            op = "in"

        if op is None:
            # Just a value reference (might be used as boolean)
            return lhs

        rhs = self._parse_value_ref()
        return CompareExpr(op=op, lhs=lhs, rhs=rhs, line=lhs.line, column=lhs.column)

    def _parse_value_ref(self) -> ExprNode:
        """Parse: number | boolean | string | ref_path | history_ref"""
        token = self._peek()

        # Number literal
        if token.type == TokenType.NUMBER:
            self._advance()
            value = token.value
            type_name = "decimal" if isinstance(value, float) else "int"
            return LiteralValue(value=value, type_name=type_name, line=token.line, column=token.column)

        # Boolean literal
        if token.type == TokenType.BOOLEAN:
            self._advance()
            return LiteralValue(value=token.value, type_name="bool", line=token.line, column=token.column)

        # String literal
        if token.type == TokenType.STRING:
            self._advance()
            return LiteralValue(value=token.value, type_name="string", line=token.line, column=token.column)

        # history() function
        if token.type == TokenType.HISTORY:
            return self._parse_history_ref()

        # Reference path (entity.field, actor.id, context.var)
        if token.type == TokenType.IDENTIFIER:
            return self._parse_ref_path()

        raise self._error(
            ErrorCode.IDL_P008_EXPECTED_EXPRESSION,
            f"Expected value expression, got {token.type.name}",
        )

    def _parse_history_ref(self) -> HistoryRef:
        """Parse: history("Step").attr"""
        token = self._advance()  # 'history'
        self._expect(TokenType.LPAREN, ErrorCode.IDL_P012_EXPECTED_LPAREN, "Expected '('")
        step_token = self._expect(TokenType.STRING, ErrorCode.IDL_P003_EXPECTED_STRING, "Expected step name string")
        self._expect(TokenType.RPAREN, ErrorCode.IDL_P013_EXPECTED_RPAREN, "Expected ')'")
        self._expect(TokenType.DOT, ErrorCode.IDL_P007_EXPECTED_COLON, "Expected '.'")

        # Parse history attribute - can be identifier or 'actors' keyword
        attr_token = self._peek()
        if attr_token.type == TokenType.IDENTIFIER:
            self._advance()
        elif attr_token.type == TokenType.ACTORS:
            # 'actors' is a keyword but also a valid history attribute
            self._advance()
            attr_token = Token(
                TokenType.IDENTIFIER,
                "actors",
                attr_token.line,
                attr_token.column,
                attr_token.end_line,
                attr_token.end_column,
            )
        else:
            raise self._error(
                ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                "Expected history attribute",
            )

        valid_attrs = {"actors", "count", "last_actor", "last_at"}
        if attr_token.value not in valid_attrs:
            raise self._error(
                ErrorCode.IDL_P023_INVALID_HISTORY_ATTR,
                f"Invalid history attribute: {attr_token.value}. Hint: Valid values are: actors, count, last_actor, last_at",
                attr_token,
            )

        # Infer type based on attribute
        type_map = {
            "actors": "set<uuid>",
            "count": "int",
            "last_actor": "uuid",
            "last_at": "datetime",
        }

        return HistoryRef(
            step_name=step_token.value,
            attr=attr_token.value,
            type_name=type_map[attr_token.value],
            line=token.line,
            column=token.column,
        )

    def _parse_ref_path(self) -> RefPath:
        """Parse: identifier.identifier..."""
        parts = []
        token = self._advance()  # first identifier
        parts.append(token.value)

        while self._match(TokenType.DOT):
            id_token = self._expect(
                TokenType.IDENTIFIER,
                ErrorCode.IDL_P002_EXPECTED_IDENTIFIER,
                "Expected identifier after '.'",
            )
            parts.append(id_token.value)

        return RefPath(path=".".join(parts), line=token.line, column=token.column)
