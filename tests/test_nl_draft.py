"""Tests for NL Draft Generation (Fase 5.6)."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.draft_generator import generate_draft
from engine.nl.schemas.sir_v1 import SIRv1


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_sir():
    """Create a sample SIR for testing."""
    extractor = DeterministicExtractor()
    text = """
    Managers must approve all expenses created by analysts.
    Users cannot approve their own expenses.
    Expenses must be at least $0.01 and cannot exceed $1,000,000.
    """
    return extractor.extract(text)


class TestDraftGenerator:
    """Tests for draft IDL generation."""

    def test_generate_draft_has_rbac(self, sample_sir):
        """Draft should contain RBAC section."""
        draft = generate_draft(sample_sir)

        assert "rbac" in draft
        assert "roles" in draft["rbac"]
        assert len(draft["rbac"]["roles"]) > 0

    def test_generate_draft_has_approvals(self, sample_sir):
        """Draft should contain Approvals section."""
        draft = generate_draft(sample_sir)

        assert "approvals" in draft
        assert "rules" in draft["approvals"]

    def test_generate_draft_has_sod(self, sample_sir):
        """Draft should contain SoD section."""
        draft = generate_draft(sample_sir)

        assert "sod" in draft
        assert "rules" in draft["sod"]

    def test_generate_draft_roles_sorted(self, sample_sir):
        """RBAC roles should be sorted by name."""
        draft = generate_draft(sample_sir)

        roles = draft["rbac"]["roles"]
        role_names = [r["name"] for r in roles]
        assert role_names == sorted(role_names)

    def test_generate_draft_permissions_sorted(self, sample_sir):
        """Role permissions should be sorted."""
        draft = generate_draft(sample_sir)

        for role in draft["rbac"]["roles"]:
            permissions = role["permissions"]
            assert permissions == sorted(permissions)

    def test_generate_draft_approval_rules_sorted(self, sample_sir):
        """Approval rules should be sorted by rule_name."""
        draft = generate_draft(sample_sir)

        rules = draft["approvals"]["rules"]
        rule_names = [r["rule_name"] for r in rules]
        assert rule_names == sorted(rule_names)

    def test_generate_draft_no_policies_raises_error(self):
        """Should raise error if SIR has no policies."""
        sir = SIRv1()  # Empty SIR
        with pytest.raises(ValueError, match="No policies"):
            generate_draft(sir)

    def test_generate_draft_deterministic(self, sample_sir):
        """Draft generation should be deterministic."""
        draft1 = generate_draft(sample_sir)
        draft2 = generate_draft(sample_sir)

        import json
        json1 = json.dumps(draft1, sort_keys=True)
        json2 = json.dumps(draft2, sort_keys=True)
        assert json1 == json2


class TestCompileDraftEndpoint:
    """Tests for POST /nl/compile/draft endpoint."""

    def test_compile_draft_success(self, client):
        """Should compile SIR to draft."""
        # First get SIR
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses created by analysts."},
        )
        sir = sir_response.json()["sir"]

        # Then compile to draft
        response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )

        assert response.status_code == 200
        data = response.json()
        assert "draft" in data
        assert "rbac" in data["draft"]

    def test_compile_draft_invalid_sir(self, client):
        """Invalid SIR should return error."""
        response = client.post(
            "/nl/compile/draft",
            json={"sir": {"invalid": "structure"}},
        )

        # Should still work but with empty extraction
        # The error will be NL_NO_POLICIES since there are no policies
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "NL_NO_POLICIES"

    def test_compile_draft_empty_sir(self, client):
        """Empty SIR should return error."""
        response = client.post(
            "/nl/compile/draft",
            json={"sir": {"version": "1.0", "source": {"language": "en"}, "extraction": {}}},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "NL_NO_POLICIES"


class TestDraftContent:
    """Tests for draft content correctness."""

    def test_draft_manager_has_approve_permission(self, sample_sir):
        """Manager role should have approve permission."""
        draft = generate_draft(sample_sir)

        manager_role = None
        for role in draft["rbac"]["roles"]:
            if role["name"] == "manager":
                manager_role = role
                break

        assert manager_role is not None
        assert any("approve" in p for p in manager_role["permissions"])

    def test_draft_analyst_has_create_permission(self, sample_sir):
        """Analyst role should have create permission."""
        draft = generate_draft(sample_sir)

        analyst_role = None
        for role in draft["rbac"]["roles"]:
            if role["name"] == "analyst":
                analyst_role = role
                break

        assert analyst_role is not None
        assert any("create" in p for p in analyst_role["permissions"])

    def test_draft_approval_has_quorum(self, sample_sir):
        """Approval rules should have quorum."""
        draft = generate_draft(sample_sir)

        for rule in draft["approvals"]["rules"]:
            assert "quorum" in rule
            assert rule["quorum"] >= 1

    def test_draft_sod_has_constraint(self, sample_sir):
        """SoD rules should have constraint."""
        draft = generate_draft(sample_sir)

        for rule in draft["sod"]["rules"]:
            assert "constraint" in rule
