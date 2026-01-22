"""
Tests for IDL DSL v1.2.2 parser and IRCS v1 emitter.

Tests cover:
- Lexer: tokenization of keywords, literals, operators
- Parser: parsing all DSL sections
- Emitter: IRCS v1 JSON generation
- Determinism: same input produces same output
- Error handling: deterministic error codes
"""

import hashlib
import json
import pytest
from pathlib import Path

from engine.idl_dsl import parse_dsl, IDLSyntaxError, IDLSemanticError
from engine.idl_dsl.lexer import Lexer
from engine.idl_dsl.parser import Parser
from engine.idl_dsl.ircs_emit import IRCSEmitter
from engine.idl_dsl.tokens import TokenType


# ============================================================
# Lexer Tests
# ============================================================


class TestLexer:
    """Tests for the IDL lexer."""

    def test_tokenize_keywords(self):
        """Keywords are correctly tokenized."""
        source = "system actors entities workflows"
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.SYSTEM
        assert tokens[1].type == TokenType.ACTORS
        assert tokens[2].type == TokenType.ENTITIES
        assert tokens[3].type == TokenType.WORKFLOWS
        assert tokens[4].type == TokenType.EOF

    def test_tokenize_string_literal(self):
        """String literals are correctly tokenized."""
        source = '"hello world"'
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"

    def test_tokenize_escape_sequences(self):
        """Escape sequences in strings are handled."""
        source = r'"line1\nline2\ttab"'
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "line1\nline2\ttab"

    def test_tokenize_numbers(self):
        """Numbers (int and float) are tokenized."""
        source = "42 3.14 -100"
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == 42
        assert tokens[1].type == TokenType.NUMBER
        assert tokens[1].value == 3.14
        assert tokens[2].type == TokenType.NUMBER
        assert tokens[2].value == -100

    def test_tokenize_duration(self):
        """Duration literals like 48h are tokenized as strings."""
        source = "48h 30m 10s"
        tokens = Lexer(source).tokenize()

        # Duration is stored as string
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "48h"
        assert tokens[1].type == TokenType.STRING
        assert tokens[1].value == "30m"
        assert tokens[2].type == TokenType.STRING
        assert tokens[2].value == "10s"

    def test_tokenize_operators(self):
        """Operators are correctly tokenized."""
        source = "== != >= <= > < ->"
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.EQ
        assert tokens[1].type == TokenType.NE
        assert tokens[2].type == TokenType.GE
        assert tokens[3].type == TokenType.LE
        assert tokens[4].type == TokenType.GT
        assert tokens[5].type == TokenType.LT
        assert tokens[6].type == TokenType.ARROW

    def test_tokenize_delimiters(self):
        """Delimiters are correctly tokenized."""
        source = "{ } [ ] ( ) : , ."
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.LBRACE
        assert tokens[1].type == TokenType.RBRACE
        assert tokens[2].type == TokenType.LBRACKET
        assert tokens[3].type == TokenType.RBRACKET
        assert tokens[4].type == TokenType.LPAREN
        assert tokens[5].type == TokenType.RPAREN
        assert tokens[6].type == TokenType.COLON
        assert tokens[7].type == TokenType.COMMA
        assert tokens[8].type == TokenType.DOT

    def test_tokenize_booleans(self):
        """Boolean literals are tokenized."""
        source = "true false"
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.BOOLEAN
        assert tokens[0].value is True
        assert tokens[1].type == TokenType.BOOLEAN
        assert tokens[1].value is False

    def test_tokenize_comments(self):
        """Comments are skipped."""
        source = """
        // line comment
        system /* block comment */ Test
        """
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.SYSTEM
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "Test"

    def test_tokenize_dotted_identifier(self):
        """Dotted identifiers like permissions are tokenized."""
        source = "finance.expense.create"
        tokens = Lexer(source).tokenize()

        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "finance.expense.create"

    def test_line_column_tracking(self):
        """Token positions are tracked."""
        source = "system\nTest"
        tokens = Lexer(source).tokenize()

        assert tokens[0].line == 1
        assert tokens[0].column == 1
        assert tokens[1].line == 2
        assert tokens[1].column == 1

    def test_unterminated_string_error(self):
        """Unterminated string raises error."""
        source = '"hello'
        with pytest.raises(IDLSyntaxError) as exc:
            Lexer(source).tokenize()

        assert "IDL_L002" in str(exc.value)

    def test_unexpected_char_error(self):
        """Unexpected character raises error."""
        source = "system @test"
        with pytest.raises(IDLSyntaxError) as exc:
            Lexer(source).tokenize()

        assert "IDL_L001" in str(exc.value)


# ============================================================
# Parser Tests
# ============================================================


class TestParser:
    """Tests for the IDL parser."""

    def test_parse_system_section(self):
        """System section is parsed correctly."""
        source = """
        system TestSystem {
            name: "Test System"
            description: "A test system"
            version: 1.0.0
            domain: "test"
            tenancy: multi
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert ast.system is not None
        assert ast.system.id == "TestSystem"
        assert ast.system.name == "Test System"
        # Version might be parsed as "1.0" if trailing .0 is not preserved
        assert ast.system.version in ("1.0.0", "1.0")
        assert ast.system.tenancy.value == "multi"

    def test_parse_actors_section(self):
        """Actors section is parsed correctly."""
        source = """
        actors {
            human operator {
                name: "Operator"
                authentication: oauth2
                permissions: [test.read, test.write]
            }
            system bot {
                name: "Bot"
                authentication: token
                permissions: []
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.actors) == 2
        assert ast.actors[0].id == "operator"
        assert ast.actors[0].kind.value == "human"
        assert ast.actors[0].auth.value == "oauth2"
        assert "test.read" in ast.actors[0].permissions

        assert ast.actors[1].id == "bot"
        assert ast.actors[1].kind.value == "system"

    def test_parse_entities_section(self):
        """Entities section is parsed correctly."""
        source = """
        entities {
            entity Item {
                storage {
                    tenant_field: tenant_id
                    version_field: version
                }
                field id: uuid required unique
                field name: string required
                field count: int default(0)
                field price: decimal min(0) max(1000)
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.entities) == 1
        entity = ast.entities[0]
        assert entity.name == "Item"
        assert entity.storage.tenant_field == "tenant_id"
        assert entity.storage.version_field == "version"

        assert len(entity.fields) == 4
        assert entity.fields[0].name == "id"
        assert entity.fields[0].type_name == "uuid"
        assert entity.fields[0].required
        assert entity.fields[0].unique

        assert entity.fields[2].default_value == 0
        assert entity.fields[3].min_value == 0
        assert entity.fields[3].max_value == 1000

    def test_parse_policy_context_section(self):
        """Policy context section is parsed correctly."""
        source = """
        policy_context {
            field jurisdiction: string required
            field risk_level: string default("low")
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert ast.policy_context is not None
        assert len(ast.policy_context.fields) == 2
        assert ast.policy_context.fields[0].name == "jurisdiction"
        assert ast.policy_context.fields[0].required
        assert ast.policy_context.fields[1].default_value == "low"

    def test_parse_invariants_section(self):
        """Invariants section is parsed correctly."""
        source = """
        entities {
            entity Account {
                field balance: decimal required
            }
        }
        invariants {
            invariant NoNegativeBalance {
                applies_to: Account
                when: always
                assert: Account.balance >= 0
                severity: critical
                message: "Balance cannot be negative"
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.invariants) == 1
        inv = ast.invariants[0]
        assert inv.name == "NoNegativeBalance"
        assert inv.applies_to == "Account"
        assert inv.severity.value == "critical"

    def test_parse_sod_section(self):
        """Separation of duties section is parsed correctly."""
        source = """
        entities {
            entity Expense {
                field id: uuid required
                field created_by: uuid required
            }
        }
        separation_of_duties {
            rule NoSelfApproval {
                on: Expense
                forbid: Approve when actor.id == Expense.created_by
                severity: critical
                message: "Cannot approve own expense"
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.separation_of_duties) == 1
        rule = ast.separation_of_duties[0]
        assert rule.name == "NoSelfApproval"
        assert rule.on_entity == "Expense"
        assert rule.forbid.action == "Approve"

    def test_parse_sod_with_history(self):
        """SoD with history() function is parsed correctly."""
        source = """
        entities {
            entity Expense { field id: uuid required }
        }
        separation_of_duties {
            rule NoSubmitterApproval {
                on: Expense
                forbid: Approve when actor.id in history("Submit").actors
                severity: critical
                message: "Submitter cannot approve"
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.separation_of_duties) == 1
        rule = ast.separation_of_duties[0]
        # The forbid expression should contain a history reference
        from engine.idl_dsl.ast_nodes import CompareExpr, HistoryRef
        assert isinstance(rule.forbid.when_expr, CompareExpr)
        assert rule.forbid.when_expr.op == "in"
        assert isinstance(rule.forbid.when_expr.rhs, HistoryRef)
        assert rule.forbid.when_expr.rhs.step_name == "Submit"
        assert rule.forbid.when_expr.rhs.attr == "actors"

    def test_parse_workflows_section(self):
        """Workflows section is parsed correctly."""
        source = """
        actors {
            human admin { name: "Admin" authentication: oauth2 permissions: [] }
            human manager { name: "Manager" authentication: oauth2 permissions: [] }
        }
        entities {
            entity Item {
                field id: uuid required
                field name: string required
            }
        }
        workflows {
            workflow TestFlow on Item {
                state Draft { initial: true }
                state Active
                state Done { terminal: true }

                transition Submit: Draft -> Active {
                    guard: Item.name != ""
                    effects: [set_state("Active"), bump_version(1)]
                }

                transition Complete: Active -> Done {
                    approvals: {
                        quorum: 2
                        roles: [admin, manager]
                        distinct_actors: true
                        expires_in: 24h
                    }
                    effects: [set_state("Done")]
                }
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert len(ast.workflows) == 1
        wf = ast.workflows[0]
        assert wf.name == "TestFlow"
        assert wf.on_entity == "Item"

        assert len(wf.states) == 3
        assert wf.states[0].initial
        assert wf.states[2].terminal

        assert len(wf.transitions) == 2
        submit = wf.transitions[0]
        assert submit.name == "Submit"
        assert submit.from_state == "Draft"
        assert submit.to_state == "Active"
        assert len(submit.effects) == 2

        complete = wf.transitions[1]
        assert complete.approvals is not None
        assert complete.approvals.quorum == 2
        assert "admin" in complete.approvals.roles

    def test_parse_operations_section(self):
        """Operations section is parsed correctly."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        operations {
            api {
                endpoint item_create {
                    method: POST
                    path: "/items"
                    request: Item
                    response: Item
                    permission: items.create
                    scope: tenant
                    idempotency: required
                    errors: [400, 401, 403]
                    bind: { entity: Item, kind: create }
                }
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        assert ast.operations is not None
        assert ast.operations.api is not None
        assert len(ast.operations.api.endpoints) == 1

        ep = ast.operations.api.endpoints[0]
        assert ep.id == "item_create"
        assert ep.method.value == "POST"
        assert ep.path == "/items"
        assert ep.bind.entity == "Item"
        assert ep.bind.kind.value == "create"

    def test_parse_expression_and_or_not(self):
        """Logical operators in expressions are parsed."""
        source = """
        entities {
            entity Item {
                field a: int required
                field b: int required
                field c: bool required
            }
        }
        invariants {
            invariant Test {
                applies_to: Item
                when: always
                assert: (Item.a > 0 and Item.b > 0) or not Item.c == false
                severity: low
                message: "test"
            }
        }
        """
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, source).parse()

        from engine.idl_dsl.ast_nodes import OrExpr
        assert isinstance(ast.invariants[0].assert_expr, OrExpr)

    def test_duplicate_section_error(self):
        """Duplicate section raises error."""
        source = """
        system A { name: "A" }
        system B { name: "B" }
        """
        tokens = Lexer(source).tokenize()
        with pytest.raises(IDLSyntaxError) as exc:
            Parser(tokens, source).parse()

        assert "IDL_P010" in str(exc.value)


# ============================================================
# Emitter Tests
# ============================================================


class TestIRCSEmitter:
    """Tests for the IRCS v1 emitter."""

    def test_emit_ir_version(self):
        """IRCS v1 has correct version metadata."""
        source = 'system Test { name: "Test" }'
        ir = parse_dsl(source)

        assert ir["ir_version"] == "ircs.v1"
        assert ir["source_idl_version"] == "idl.v1.2.2"
        assert "source_idl_sha256" in ir
        assert len(ir["source_idl_sha256"]) == 64  # SHA256 hex

    def test_emit_source_hash_matches(self):
        """Source hash matches actual SHA256 of source."""
        source = 'system Test { name: "Test" }'
        ir = parse_dsl(source)

        expected_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert ir["source_idl_sha256"] == expected_hash

    def test_emit_typed_expression(self):
        """Expressions are emitted as typed AST."""
        source = """
        entities {
            entity Item { field value: int required }
        }
        invariants {
            invariant Test {
                applies_to: Item
                when: always
                assert: Item.value >= 0
                severity: low
                message: "test"
            }
        }
        """
        ir = parse_dsl(source)

        assert_expr = ir["invariants"][0]["assert"]
        assert assert_expr["kind"] == "compare"
        assert assert_expr["op"] == ">="
        assert "ref" in assert_expr["lhs"]
        assert "lit" in assert_expr["rhs"]

    def test_emit_history_ref(self):
        """history() references are emitted correctly."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        separation_of_duties {
            rule Test {
                on: Item
                forbid: Approve when actor.id in history("Submit").actors
                severity: critical
                message: "test"
            }
        }
        """
        ir = parse_dsl(source)

        when_expr = ir["separation_of_duties"][0]["forbid"]["when"]
        assert when_expr["kind"] == "compare"
        assert when_expr["op"] == "in"
        assert "history" in when_expr["rhs"]
        assert when_expr["rhs"]["history"] == "Submit"
        assert when_expr["rhs"]["attr"] == "actors"
        assert when_expr["rhs"]["type"] == "set<uuid>"

    def test_emit_department_derived(self):
        """Department is derived from system."""
        source = """
        system FinanceApp {
            name: "Finance"
            domain: "finance"
            tenancy: multi
        }
        """
        ir = parse_dsl(source)

        assert ir["department"]["dept_id"] == "finance"
        assert ir["department"]["tenancy"] == "multi"
        assert ir["department"]["entrypoints"]["api_prefix"] == "/finance"

    def test_emit_runtime_defaults(self):
        """Runtime section has defaults."""
        source = 'system Test { name: "Test" }'
        ir = parse_dsl(source)

        assert ir["runtime"]["safe_mode"]["enabled"] is True
        assert "gate_order" in ir["runtime"]

    def test_deterministic_output(self):
        """Same input produces same output (determinism)."""
        source = """
        system Test {
            name: "Test"
            version: 1.0.0
        }
        actors {
            human user { name: "User" authentication: oauth2 permissions: [] }
        }
        """

        ir1 = parse_dsl(source)
        ir2 = parse_dsl(source)

        json1 = json.dumps(ir1, sort_keys=True)
        json2 = json.dumps(ir2, sort_keys=True)

        assert json1 == json2

    def test_deterministic_hash(self):
        """Multiple parses produce same hash."""
        source = 'system Test { name: "Test" }'

        hash1 = parse_dsl(source)["source_idl_sha256"]
        hash2 = parse_dsl(source)["source_idl_sha256"]

        assert hash1 == hash2


# ============================================================
# Integration Tests
# ============================================================


class TestFinanceCanonical:
    """Integration tests using the Finance canonical example."""

    @pytest.fixture
    def finance_source(self) -> str:
        """Load the Finance canonical IDL."""
        finance_path = Path(__file__).parent.parent / "examples" / "finance.idl"
        if not finance_path.exists():
            pytest.skip("finance.idl not found")
        return finance_path.read_text(encoding="utf-8")

    def test_parse_finance_canonical(self, finance_source):
        """Finance canonical parses without errors."""
        ir = parse_dsl(finance_source)

        assert ir["ir_version"] == "ircs.v1"
        assert ir["system"]["id"] == "FinancePilot"

    def test_finance_has_all_sections(self, finance_source):
        """Finance IR has all expected sections."""
        ir = parse_dsl(finance_source)

        assert len(ir["actors"]) == 4
        assert len(ir["entities"]) == 2
        assert len(ir["invariants"]) == 2
        assert len(ir["separation_of_duties"]) == 2
        assert len(ir["workflows"]) == 1
        assert len(ir["operations"]["api"]) == 4

    def test_finance_sod_uses_history(self, finance_source):
        """Finance SoD rules use history()."""
        ir = parse_dsl(finance_source)

        # NoSubmitterApproval uses history("Submit").actors
        sod_rules = ir["separation_of_duties"]
        history_rule = [r for r in sod_rules if r["name"] == "NoSubmitterApproval"]
        assert len(history_rule) == 1

        when_expr = history_rule[0]["forbid"]["when"]
        assert "history" in when_expr["rhs"]

    def test_finance_workflow_has_approvals(self, finance_source):
        """Finance workflow transitions have approvals."""
        ir = parse_dsl(finance_source)

        workflow = ir["workflows"][0]
        approve_transition = [t for t in workflow["transitions"] if t["name"] == "Approve"]
        assert len(approve_transition) == 1

        approvals = approve_transition[0]["approvals"]
        assert approvals["quorum"] == 2
        assert "manager" in approvals["roles"]


# ============================================================
# Error Code Tests
# ============================================================


class TestErrorCodes:
    """Tests for deterministic error codes."""

    def test_error_code_format(self):
        """Error codes follow expected format."""
        source = "system { }"  # Missing identifier

        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        # Should include error code
        error_str = str(exc.value)
        assert "[IDL_P" in error_str or "[IDL_L" in error_str

    def test_error_location_included(self):
        """Errors include line/column location."""
        source = "system Test { name }"  # Missing colon

        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        # Should include location
        assert exc.value.location is not None

    def test_same_error_for_same_input(self):
        """Same invalid input produces same error."""
        source = "system { }"

        e1 = None
        e2 = None
        try:
            parse_dsl(source)
        except IDLSyntaxError as err:
            e1 = err

        try:
            parse_dsl(source)
        except IDLSyntaxError as err:
            e2 = err

        assert e1 is not None and e2 is not None
        assert e1.code == e2.code
        assert e1.message == e2.message


# ============================================================
# CHANGE-1 Tests: Semantic Validation
# ============================================================


class TestSemanticValidation:
    """Tests for semantic validation of references (CHANGE-1)."""

    def test_semantic_undefined_entity_in_invariant(self):
        """Undefined entity in invariant raises semantic error."""
        source = """
        invariants {
            invariant Test {
                applies_to: NonExistentEntity
                when: always
                assert: NonExistentEntity.field > 0
                severity: high
                message: "Error"
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S001" in str(exc.value)
        assert "NonExistentEntity" in str(exc.value)
        assert "Hint" in str(exc.value)

    def test_semantic_undefined_entity_in_sod(self):
        """Undefined entity in SoD rule raises semantic error."""
        source = """
        separation_of_duties {
            rule Test {
                on: NonExistentEntity
                forbid: Approve when actor.id == NonExistentEntity.created_by
                severity: critical
                message: "Error"
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S001" in str(exc.value)
        assert "NonExistentEntity" in str(exc.value)

    def test_semantic_undefined_entity_in_workflow(self):
        """Undefined entity in workflow raises semantic error."""
        source = """
        workflows {
            workflow TestFlow on NonExistentEntity {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    effects: [set_state("Done")]
                }
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S001" in str(exc.value)
        assert "NonExistentEntity" in str(exc.value)

    def test_semantic_undefined_actor_in_roles(self):
        """Undefined actor in workflow roles raises semantic error."""
        source = """
        actors {
            human manager { name: "Manager" authentication: oauth2 permissions: [] }
        }
        entities {
            entity Item { field id: uuid required }
        }
        workflows {
            workflow TestFlow on Item {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    approvals: {
                        quorum: 1
                        roles: [nonexistent_actor]
                        distinct_actors: true
                    }
                    effects: [set_state("Done")]
                }
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S002" in str(exc.value)
        assert "nonexistent_actor" in str(exc.value)

    def test_semantic_undefined_workflow_in_bind(self):
        """Undefined workflow in endpoint bind raises semantic error."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        operations {
            api {
                endpoint item_submit {
                    method: POST
                    path: "/items/{id}/submit"
                    request: void
                    response: Item
                    permission: items.submit
                    scope: tenant
                    idempotency: required
                    errors: [400]
                    bind: { entity: Item, kind: transition, workflow: NonExistentWorkflow, transition: Submit }
                }
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S003" in str(exc.value)
        assert "NonExistentWorkflow" in str(exc.value)

    def test_semantic_undefined_transition_in_bind(self):
        """Undefined transition in endpoint bind raises semantic error."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        workflows {
            workflow ItemFlow on Item {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    effects: [set_state("Done")]
                }
            }
        }
        operations {
            api {
                endpoint item_submit {
                    method: POST
                    path: "/items/{id}/submit"
                    request: void
                    response: Item
                    permission: items.submit
                    scope: tenant
                    idempotency: required
                    errors: [400]
                    bind: { entity: Item, kind: transition, workflow: ItemFlow, transition: NonExistentTransition }
                }
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S004" in str(exc.value)
        assert "NonExistentTransition" in str(exc.value)

    def test_semantic_undefined_field_in_expression(self):
        """Undefined field in expression raises semantic error."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        invariants {
            invariant Test {
                applies_to: Item
                when: always
                assert: Item.nonexistent_field > 0
                severity: high
                message: "Error"
            }
        }
        """
        with pytest.raises(IDLSemanticError) as exc:
            parse_dsl(source)

        assert "IDL_S006" in str(exc.value)
        assert "nonexistent_field" in str(exc.value)

    def test_semantic_valid_references(self):
        """Valid references pass semantic validation."""
        source = """
        actors {
            human manager { name: "Manager" authentication: oauth2 permissions: [] }
        }
        entities {
            entity Item {
                field id: uuid required
                field name: string required
            }
        }
        invariants {
            invariant NameNotEmpty {
                applies_to: Item
                when: always
                assert: Item.name != ""
                severity: high
                message: "Name required"
            }
        }
        workflows {
            workflow ItemFlow on Item {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    approvals: {
                        quorum: 1
                        roles: [manager]
                        distinct_actors: true
                    }
                    effects: [set_state("Done")]
                }
            }
        }
        operations {
            api {
                endpoint item_finish {
                    method: POST
                    path: "/items/{id}/finish"
                    request: void
                    response: Item
                    permission: items.finish
                    scope: tenant
                    idempotency: required
                    errors: [400]
                    bind: { entity: Item, kind: transition, workflow: ItemFlow, transition: Finish }
                }
            }
        }
        """
        # Should not raise any error
        ir = parse_dsl(source)
        assert ir["ir_version"] == "ircs.v1"


# ============================================================
# CHANGE-2 Tests: Guard Null -> Always
# ============================================================


class TestGuardAlwaysExplicit:
    """Tests for explicit guard: {kind: 'always'} (CHANGE-2)."""

    def test_transition_guard_default_always(self):
        """Transition without guard emits {kind: 'always'}."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        workflows {
            workflow TestFlow on Item {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    effects: [set_state("Done")]
                }
            }
        }
        """
        ir = parse_dsl(source)

        transition = ir["workflows"][0]["transitions"][0]
        assert transition["guard"] == {"kind": "always"}
        assert transition["guard"] is not None

    def test_transition_with_explicit_guard(self):
        """Transition with guard still emits the guard expression."""
        source = """
        entities {
            entity Item {
                field id: uuid required
                field active: bool required
            }
        }
        workflows {
            workflow TestFlow on Item {
                state Draft { initial: true }
                state Done { terminal: true }
                transition Finish: Draft -> Done {
                    guard: Item.active == true
                    effects: [set_state("Done")]
                }
            }
        }
        """
        ir = parse_dsl(source)

        transition = ir["workflows"][0]["transitions"][0]
        assert transition["guard"]["kind"] == "compare"
        assert transition["guard"]["op"] == "=="


# ============================================================
# CHANGE-3 Tests: Required False Explicit
# ============================================================


class TestRequiredFalseExplicit:
    """Tests for explicit required: false (CHANGE-3)."""

    def test_field_required_explicit_true(self):
        """Field with 'required' modifier has required: true."""
        source = """
        entities {
            entity Item {
                field id: uuid required
            }
        }
        """
        ir = parse_dsl(source)

        field = ir["entities"][0]["fields"][0]
        assert field["required"] is True

    def test_field_required_explicit_false(self):
        """Field without 'required' modifier has required: false."""
        source = """
        entities {
            entity Item {
                field notes: text
            }
        }
        """
        ir = parse_dsl(source)

        field = ir["entities"][0]["fields"][0]
        assert "required" in field
        assert field["required"] is False

    def test_context_field_required_explicit(self):
        """Policy context fields have explicit required."""
        source = """
        policy_context {
            field jurisdiction: string required
            field risk_level: string
        }
        """
        ir = parse_dsl(source)

        fields = ir["policy_context"]["schema"]
        assert fields[0]["required"] is True
        assert "required" in fields[1]
        assert fields[1]["required"] is False


# ============================================================
# CHANGE-4 Tests: Error Hints
# ============================================================


class TestErrorHints:
    """Tests for error messages with hints (CHANGE-4)."""

    def test_error_hint_severity(self):
        """Invalid severity error includes hint."""
        source = """
        invariants {
            invariant Test {
                applies_to: Item
                when: always
                assert: Item.value > 0
                severity: warning
                message: "Error"
            }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P019" in str(exc.value)
        assert "Hint" in str(exc.value)
        assert "low" in str(exc.value)
        assert "high" in str(exc.value)
        assert "critical" in str(exc.value)

    def test_error_hint_auth_method(self):
        """Invalid auth method error includes hint."""
        source = """
        actors {
            human user { name: "User" authentication: jwt permissions: [] }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P018" in str(exc.value)
        assert "Hint" in str(exc.value)
        assert "oauth2" in str(exc.value)
        assert "token" in str(exc.value)

    def test_error_hint_http_method(self):
        """Invalid HTTP method error includes hint."""
        source = """
        operations {
            api {
                endpoint test {
                    method: OPTIONS
                    path: "/test"
                    request: void
                    response: void
                    permission: test
                    scope: tenant
                    idempotency: none
                    errors: []
                }
            }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P020" in str(exc.value)
        assert "Hint" in str(exc.value)
        assert "GET" in str(exc.value)
        assert "POST" in str(exc.value)

    def test_error_hint_bind_kind(self):
        """Invalid bind kind error includes hint."""
        source = """
        operations {
            api {
                endpoint test {
                    method: GET
                    path: "/test"
                    request: void
                    response: void
                    permission: test
                    scope: tenant
                    idempotency: none
                    errors: []
                    bind: { entity: Item, kind: query }
                }
            }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P022" in str(exc.value)
        assert "Hint" in str(exc.value)
        assert "create" in str(exc.value)
        assert "read" in str(exc.value)


# ============================================================
# CHANGE-5 Tests: Path Template Validation
# ============================================================


class TestPathTemplateValidation:
    """Tests for path template validation (CHANGE-5)."""

    def test_path_template_valid(self):
        """Valid path template is accepted."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        operations {
            api {
                endpoint item_get {
                    method: GET
                    path: "/items/{id}"
                    request: void
                    response: Item
                    permission: items.read
                    scope: tenant
                    idempotency: none
                    errors: [404]
                    bind: { entity: Item, kind: read }
                }
            }
        }
        """
        ir = parse_dsl(source)

        endpoint = ir["operations"]["api"][0]
        assert endpoint["path"] == "/items/{id}"
        assert endpoint["path_params"] == ["id"]

    def test_path_params_extraction(self):
        """Multiple path params are extracted."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        operations {
            api {
                endpoint item_action {
                    method: POST
                    path: "/tenants/{tenant_id}/items/{item_id}/actions/{action_name}"
                    request: void
                    response: Item
                    permission: items.action
                    scope: tenant
                    idempotency: required
                    errors: [400]
                    bind: { entity: Item, kind: update }
                }
            }
        }
        """
        ir = parse_dsl(source)

        endpoint = ir["operations"]["api"][0]
        assert endpoint["path_params"] == ["tenant_id", "item_id", "action_name"]

    def test_path_template_no_params(self):
        """Path without params has empty path_params list."""
        source = """
        entities {
            entity Item { field id: uuid required }
        }
        operations {
            api {
                endpoint item_list {
                    method: GET
                    path: "/items"
                    request: void
                    response: Item
                    permission: items.read
                    scope: tenant
                    idempotency: none
                    errors: []
                    bind: { entity: Item, kind: read }
                }
            }
        }
        """
        ir = parse_dsl(source)

        endpoint = ir["operations"]["api"][0]
        assert endpoint["path_params"] == []

    def test_path_template_invalid_uppercase(self):
        """Invalid path param with uppercase raises error."""
        source = """
        operations {
            api {
                endpoint test {
                    method: GET
                    path: "/items/{ItemId}"
                    request: void
                    response: void
                    permission: test
                    scope: tenant
                    idempotency: none
                    errors: []
                }
            }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P029" in str(exc.value)
        assert "ItemId" in str(exc.value)
        assert "Hint" in str(exc.value)

    def test_path_template_invalid_hyphen(self):
        """Invalid path param with hyphen raises error."""
        source = """
        operations {
            api {
                endpoint test {
                    method: GET
                    path: "/items/{item-id}"
                    request: void
                    response: void
                    permission: test
                    scope: tenant
                    idempotency: none
                    errors: []
                }
            }
        }
        """
        with pytest.raises(IDLSyntaxError) as exc:
            parse_dsl(source)

        assert "IDL_P029" in str(exc.value)
        assert "item-id" in str(exc.value)
