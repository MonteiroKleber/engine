"""Testes para o policy validator de IR."""

import pytest

from validators.policy_validator import PolicyValidator


@pytest.fixture
def valid_ir():
    """Retorna um IR válido para testes."""
    return {
        "meta": {
            "project_name": "Sistema Teste",
            "version": "1.0.0",
            "created_at": "2024-01-01T00:00:00Z",
        },
        "domain": {
            "entities": [
                {
                    "name": "cliente",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "nome", "type": "string", "required": True},
                    ],
                }
            ],
            "relations": [],
            "workflows": [],
            "rules": [],
        },
        "api_intent": {
            "resources": ["cliente"],
        },
        "ui": {
            "pages": [
                {"path": "/app/cliente/list", "title": "Listar Clientes", "components": ["table"], "actions": ["list"]},
                {"path": "/app/cliente/new", "title": "Novo Cliente", "components": ["form"], "actions": ["create"]},
                {"path": "/app/cliente/:id", "title": "Detalhes Cliente", "components": ["form"], "actions": ["view"]},
            ]
        },
        "nfr": {
            "security": {
                "auth_required": True,
                "audit_log_required": False,
            },
        },
    }


class TestPolicyValidatorBasic:
    """Testes básicos do PolicyValidator."""

    def test_valid_ir_passes_policy(self, valid_ir):
        """IR válido deve passar todas as policies."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True
        assert len(violations) == 0

    def test_policy_validator_returns_tuple(self, valid_ir):
        """Validate deve retornar tuple (bool, list)."""
        validator = PolicyValidator()
        result = validator.validate(valid_ir)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)


class TestEntitiesNotEmptyPolicy:
    """Testes da policy: domain.entities não pode estar vazio."""

    def test_empty_entities_fails_policy(self, valid_ir):
        """IR com entities vazio deve falhar policy."""
        valid_ir["domain"]["entities"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("entities está vazio" in v for v in violations)

    def test_missing_entities_fails_policy(self, valid_ir):
        """IR sem entities deve falhar policy."""
        del valid_ir["domain"]["entities"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("entities está vazio" in v for v in violations)


class TestApiResourcesMatchEntitiesPolicy:
    """Testes da policy: api_intent.resources deve conter todas entidades."""

    def test_missing_resource_fails_policy(self, valid_ir):
        """Entidade sem resource correspondente deve falhar."""
        # Adicionar entidade sem resource
        valid_ir["domain"]["entities"].append({
            "name": "produto",
            "primary_key": "id",
            "fields": [{"name": "id", "type": "uuid", "required": True}],
        })
        # Não adicionar "produto" aos resources

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("produto" in v and "resource" in v for v in violations)

    def test_all_entities_have_resources_passes(self, valid_ir):
        """Todas entidades com resources deve passar."""
        # Adicionar entidade com resource
        valid_ir["domain"]["entities"].append({
            "name": "produto",
            "primary_key": "id",
            "fields": [{"name": "id", "type": "uuid", "required": True}],
        })
        valid_ir["api_intent"]["resources"].append("produto")

        # Adicionar páginas para produto
        valid_ir["ui"]["pages"].extend([
            {"path": "/app/produto/list", "title": "Listar Produtos", "components": ["table"], "actions": ["list"]},
            {"path": "/app/produto/new", "title": "Novo Produto", "components": ["form"], "actions": ["create"]},
            {"path": "/app/produto/:id", "title": "Detalhes Produto", "components": ["form"], "actions": ["view"]},
        ])

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True


class TestUiPagesForEntitiesPolicy:
    """Testes da policy: ui.pages deve existir para cada entidade."""

    def test_missing_list_page_fails_policy(self, valid_ir):
        """Entidade sem página de listagem deve falhar."""
        # Remover página de listagem
        valid_ir["ui"]["pages"] = [
            p for p in valid_ir["ui"]["pages"]
            if "list" not in p["path"]
        ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("listagem" in v for v in violations)

    def test_missing_new_page_fails_policy(self, valid_ir):
        """Entidade sem página de criação deve falhar."""
        # Remover página de criação
        valid_ir["ui"]["pages"] = [
            p for p in valid_ir["ui"]["pages"]
            if "new" not in p["path"]
        ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("criação" in v for v in violations)

    def test_missing_detail_page_fails_policy(self, valid_ir):
        """Entidade sem página de detalhe deve falhar."""
        # Remover página de detalhe
        valid_ir["ui"]["pages"] = [
            p for p in valid_ir["ui"]["pages"]
            if ":id" not in p["path"]
        ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("detalhe" in v for v in violations)

    def test_all_pages_present_passes(self, valid_ir):
        """Todas as páginas presentes deve passar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True

    def test_no_pages_fails_with_multiple_violations(self, valid_ir):
        """Sem nenhuma página deve falhar com múltiplas violações."""
        valid_ir["ui"]["pages"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        # Deve ter violações para list, new e detail
        assert len(violations) >= 3


class TestNfrAuthRequiredTypePolicy:
    """Testes da policy: nfr.security.auth_required deve ser boolean."""

    def test_auth_required_string_fails_policy(self, valid_ir):
        """auth_required como string deve falhar."""
        valid_ir["nfr"]["security"]["auth_required"] = "true"

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("auth_required" in v and "boolean" in v for v in violations)

    def test_auth_required_int_fails_policy(self, valid_ir):
        """auth_required como int deve falhar."""
        valid_ir["nfr"]["security"]["auth_required"] = 1

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert any("auth_required" in v and "boolean" in v for v in violations)

    def test_auth_required_true_passes(self, valid_ir):
        """auth_required True deve passar."""
        valid_ir["nfr"]["security"]["auth_required"] = True

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True

    def test_auth_required_false_passes(self, valid_ir):
        """auth_required False deve passar."""
        valid_ir["nfr"]["security"]["auth_required"] = False

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True

    def test_missing_auth_required_passes(self, valid_ir):
        """Sem auth_required deve passar (não é obrigatório)."""
        del valid_ir["nfr"]["security"]["auth_required"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is True


class TestMultiplePolicyViolations:
    """Testes de múltiplas violações de policy."""

    def test_multiple_violations_all_reported(self, valid_ir):
        """Múltiplas violações devem ser todas reportadas."""
        # Violar múltiplas policies
        valid_ir["domain"]["entities"] = []  # entities vazio
        valid_ir["nfr"]["security"]["auth_required"] = "yes"  # não boolean

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        assert len(violations) >= 2

    def test_ir_with_multiple_entities_all_checked(self, valid_ir):
        """IR com múltiplas entidades deve verificar todas."""
        # Adicionar entidade sem resource nem páginas
        valid_ir["domain"]["entities"].append({
            "name": "pedido",
            "primary_key": "id",
            "fields": [{"name": "id", "type": "uuid", "required": True}],
        })

        validator = PolicyValidator()
        is_valid, violations = validator.validate(valid_ir)

        assert is_valid is False
        # Deve ter violações para pedido (resource + 3 páginas)
        pedido_violations = [v for v in violations if "pedido" in v]
        assert len(pedido_violations) >= 4


class TestPolicyValidatorIntegration:
    """Testes de integração do PolicyValidator com DomainModeler."""

    def test_domain_modeler_ir_passes_policy(self):
        """IR gerado pelo DomainModeler deve passar policy."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()

        normalized = normalizer.normalize("sistema de clientes")
        srs = analyst.generate_srs(normalized, "CRM")
        ir = modeler.generate_ir(srs)

        validator = PolicyValidator()
        is_valid, violations = validator.validate(ir)

        assert is_valid is True, f"Violations: {violations}"

    def test_domain_modeler_empty_ir_fails_policy(self):
        """IR vazio do DomainModeler deve falhar policy."""
        from agents.domain_modeler import DomainModeler

        modeler = DomainModeler()

        # SRS sem data_requirements gera IR com entities vazio
        srs_empty = {
            "title": "Sistema Vazio",
            "meta": {"project_name": "Vazio"},
        }

        ir = modeler.generate_ir(srs_empty)

        validator = PolicyValidator()
        is_valid, violations = validator.validate(ir)

        assert is_valid is False
        assert any("entities está vazio" in v for v in violations)


# ==================== CONTRACTS POLICIES TESTS ====================


@pytest.fixture
def valid_openapi():
    """Retorna um OpenAPI válido para testes."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/api/users": {
                "get": {
                    "operationId": "listUsers",
                    "tags": ["users"],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createUser",
                    "tags": ["users"],
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/api/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "tags": ["users"],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "deleteUser",
                    "tags": ["users"],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            }
        },
    }


@pytest.fixture
def valid_rbac():
    """Retorna um RBAC válido para testes."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {"operation_id": "listUsers", "required_role": "authenticated"},
            {"operation_id": "createUser", "required_role": "authenticated"},
            {"operation_id": "getUser", "required_role": "authenticated"},
            {"operation_id": "deleteUser", "required_role": "admin"},
        ],
    }


class TestContractsPolicyBasic:
    """Testes básicos do validate_contracts."""

    def test_valid_contracts_passes_policy(self, valid_openapi, valid_rbac):
        """OpenAPI e RBAC válidos devem passar todas as policies."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is True
        assert len(violations) == 0

    def test_validate_contracts_returns_tuple(self, valid_openapi, valid_rbac):
        """validate_contracts deve retornar tuple (bool, list)."""
        validator = PolicyValidator()
        result = validator.validate_contracts(valid_openapi, valid_rbac)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)


class TestOperationPermissionPolicy:
    """Testes da policy: toda operação no OpenAPI deve ter permissão no RBAC."""

    def test_missing_permission_fails_policy(self, valid_openapi, valid_rbac):
        """Operação sem permissão correspondente deve falhar."""
        # Remover permissão de deleteUser
        valid_rbac["permissions"] = [
            p for p in valid_rbac["permissions"]
            if p["operation_id"] != "deleteUser"
        ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("deleteUser" in v and "não tem permissão" in v for v in violations)

    def test_multiple_missing_permissions_all_reported(self, valid_openapi, valid_rbac):
        """Múltiplas operações sem permissão devem ser todas reportadas."""
        # Remover todas as permissões exceto listUsers
        valid_rbac["permissions"] = [
            p for p in valid_rbac["permissions"]
            if p["operation_id"] == "listUsers"
        ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        # Deve ter 3 violações (createUser, getUser, deleteUser)
        operation_violations = [v for v in violations if "não tem permissão" in v]
        assert len(operation_violations) == 3


class TestOrphanPermissionPolicy:
    """Testes da policy: toda permissão no RBAC deve referenciar operação no OpenAPI."""

    def test_orphan_permission_fails_policy(self, valid_openapi, valid_rbac):
        """Permissão sem operação correspondente deve falhar."""
        # Adicionar permissão órfã
        valid_rbac["permissions"].append({
            "operation_id": "updateUser",
            "required_role": "authenticated",
        })

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("updateUser" in v and "não existe no OpenAPI" in v for v in violations)

    def test_multiple_orphan_permissions_all_reported(self, valid_openapi, valid_rbac):
        """Múltiplas permissões órfãs devem ser todas reportadas."""
        valid_rbac["permissions"].extend([
            {"operation_id": "updateUser", "required_role": "authenticated"},
            {"operation_id": "patchUser", "required_role": "authenticated"},
        ])

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        orphan_violations = [v for v in violations if "não existe no OpenAPI" in v]
        assert len(orphan_violations) == 2


class TestAuthenticatedRolePolicy:
    """Testes da policy: rbac.roles deve conter 'authenticated'."""

    def test_missing_authenticated_role_fails_policy(self, valid_openapi, valid_rbac):
        """RBAC sem role 'authenticated' deve falhar."""
        valid_rbac["roles"] = ["admin", "user"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("authenticated" in v for v in violations)

    def test_empty_roles_fails_policy(self, valid_openapi, valid_rbac):
        """RBAC com roles vazio deve falhar."""
        valid_rbac["roles"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("authenticated" in v for v in violations)

    def test_only_authenticated_role_passes(self, valid_openapi, valid_rbac):
        """RBAC com apenas 'authenticated' deve passar."""
        valid_rbac["roles"] = ["authenticated"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        # Pode falhar por outras razões, mas não pela role
        auth_violations = [v for v in violations if "authenticated" in v]
        assert len(auth_violations) == 0


class TestOpenAPISchemasPolicy:
    """Testes da policy: OpenAPI deve ter components/schemas."""

    def test_missing_schemas_fails_policy(self, valid_openapi, valid_rbac):
        """OpenAPI sem schemas deve falhar."""
        valid_openapi["components"]["schemas"] = {}

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("schemas" in v for v in violations)

    def test_missing_components_fails_policy(self, valid_openapi, valid_rbac):
        """OpenAPI sem components deve falhar."""
        del valid_openapi["components"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        assert any("schemas" in v for v in violations)

    def test_with_schemas_passes(self, valid_openapi, valid_rbac):
        """OpenAPI com schemas deve passar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        schema_violations = [v for v in violations if "schemas" in v]
        assert len(schema_violations) == 0


class TestMultipleContractsPolicyViolations:
    """Testes de múltiplas violações de contracts policy."""

    def test_multiple_violations_all_reported(self, valid_openapi, valid_rbac):
        """Múltiplas violações devem ser todas reportadas."""
        # Violar múltiplas policies
        valid_rbac["roles"] = ["admin"]  # sem authenticated
        valid_openapi["components"]["schemas"] = {}  # sem schemas
        valid_rbac["permissions"] = [
            p for p in valid_rbac["permissions"]
            if p["operation_id"] == "listUsers"
        ]  # missing permissions

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(valid_openapi, valid_rbac)

        assert is_valid is False
        # Deve ter pelo menos 3 tipos de violações
        assert len(violations) >= 3


class TestContractsPolicyIntegration:
    """Testes de integração do validate_contracts com o pipeline."""

    def test_contracts_agent_output_passes_policy(self):
        """Output do ContractsAgent deve passar policy."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()

        normalized = normalizer.normalize("sistema de produtos")
        srs = analyst.generate_srs(normalized, "Produtos")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(openapi, rbac)

        assert is_valid is True, f"Violations: {violations}"

    def test_removed_permission_fails_policy(self):
        """Se apagar uma permissão do RBAC, policy deve falhar."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()

        normalized = normalizer.normalize("sistema de clientes")
        srs = analyst.generate_srs(normalized, "CRM")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)

        # Remover uma permissão
        if rbac["permissions"]:
            rbac["permissions"].pop()

        validator = PolicyValidator()
        is_valid, violations = validator.validate_contracts(openapi, rbac)

        assert is_valid is False
        assert any("não tem permissão" in v for v in violations)


# ==================== PLAN POLICIES TESTS ====================


@pytest.fixture
def valid_plan():
    """Retorna um PLAN válido para testes."""
    return {
        "meta": {
            "version": "v1",
            "strategy": "PATCH_ONLY",
            "project_name": "Test Project",
        },
        "tasks": [
            {
                "id": "task_create_model",
                "title": "Create model",
                "order": 1,
                "files": ["src/models/entity.py"],
                "acceptance": ["Model file exists"],
            },
            {
                "id": "task_create_service",
                "title": "Create service",
                "order": 2,
                "files": ["src/services/entity_service.py"],
                "acceptance": ["Service file exists"],
            },
        ],
    }


class TestPlanPolicyBasic:
    """Testes básicos do validate_plan."""

    def test_valid_plan_passes_policy(self, valid_plan):
        """PLAN válido deve passar todas as policies."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is True
        assert len(violations) == 0

    def test_validate_plan_returns_tuple(self, valid_plan):
        """validate_plan deve retornar tuple (bool, list)."""
        validator = PolicyValidator()
        result = validator.validate_plan(valid_plan)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)


class TestPlanStrategyPolicy:
    """Testes da policy: meta.strategy deve ser PATCH_ONLY."""

    def test_invalid_strategy_fails_policy(self, valid_plan):
        """PLAN com strategy diferente de PATCH_ONLY deve falhar."""
        valid_plan["meta"]["strategy"] = "FULL_REWRITE"

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("PATCH_ONLY" in v for v in violations)

    def test_missing_strategy_fails_policy(self, valid_plan):
        """PLAN sem strategy deve falhar."""
        del valid_plan["meta"]["strategy"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("PATCH_ONLY" in v for v in violations)

    def test_patch_only_strategy_passes(self, valid_plan):
        """PLAN com strategy PATCH_ONLY deve passar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        strategy_violations = [v for v in violations if "strategy" in v.lower()]
        assert len(strategy_violations) == 0


class TestPlanHasTasksPolicy:
    """Testes da policy: PLAN deve ter pelo menos uma task."""

    def test_empty_tasks_fails_policy(self, valid_plan):
        """PLAN com tasks vazio deve falhar."""
        valid_plan["tasks"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("pelo menos uma task" in v for v in violations)

    def test_missing_tasks_fails_policy(self, valid_plan):
        """PLAN sem tasks deve falhar."""
        del valid_plan["tasks"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("pelo menos uma task" in v for v in violations)

    def test_with_tasks_passes(self, valid_plan):
        """PLAN com tasks deve passar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        task_violations = [v for v in violations if "pelo menos uma task" in v]
        assert len(task_violations) == 0


class TestPlanTasksHaveFilesPolicy:
    """Testes da policy: cada task deve ter files não vazio."""

    def test_empty_files_fails_policy(self, valid_plan):
        """Task com files vazio deve falhar."""
        valid_plan["tasks"][0]["files"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("files não vazio" in v for v in violations)

    def test_missing_files_fails_policy(self, valid_plan):
        """Task sem files deve falhar."""
        del valid_plan["tasks"][0]["files"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("files não vazio" in v for v in violations)

    def test_multiple_tasks_empty_files_all_reported(self, valid_plan):
        """Múltiplas tasks com files vazio devem ser todas reportadas."""
        valid_plan["tasks"][0]["files"] = []
        valid_plan["tasks"][1]["files"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        files_violations = [v for v in violations if "files não vazio" in v]
        assert len(files_violations) == 2


class TestPlanTasksHaveAcceptancePolicy:
    """Testes da policy: cada task deve ter acceptance não vazio."""

    def test_empty_acceptance_fails_policy(self, valid_plan):
        """Task com acceptance vazio deve falhar."""
        valid_plan["tasks"][0]["acceptance"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("acceptance não vazio" in v for v in violations)

    def test_missing_acceptance_fails_policy(self, valid_plan):
        """Task sem acceptance deve falhar."""
        del valid_plan["tasks"][0]["acceptance"]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        assert any("acceptance não vazio" in v for v in violations)

    def test_multiple_tasks_empty_acceptance_all_reported(self, valid_plan):
        """Múltiplas tasks com acceptance vazio devem ser todas reportadas."""
        valid_plan["tasks"][0]["acceptance"] = []
        valid_plan["tasks"][1]["acceptance"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        acceptance_violations = [v for v in violations if "acceptance não vazio" in v]
        assert len(acceptance_violations) == 2


class TestMultiplePlanPolicyViolations:
    """Testes de múltiplas violações de plan policy."""

    def test_multiple_violations_all_reported(self, valid_plan):
        """Múltiplas violações devem ser todas reportadas."""
        # Violar múltiplas policies
        valid_plan["meta"]["strategy"] = "INVALID"
        valid_plan["tasks"][0]["files"] = []
        valid_plan["tasks"][0]["acceptance"] = []

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is False
        # Deve ter pelo menos 3 violações
        assert len(violations) >= 3


class TestPlanPolicyIntegration:
    """Testes de integração do validate_plan com o pipeline."""

    def test_planner_agent_output_passes_policy(self):
        """Output do PlannerAgent deve passar policy."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        from agents.planner_agent import PlannerAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()
        planner = PlannerAgent()

        normalized = normalizer.normalize("sistema de produtos")
        srs = analyst.generate_srs(normalized, "Produtos")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)
        plan = planner.generate_plan(ir, openapi, rbac)

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan)

        assert is_valid is True, f"Violations: {violations}"

    def test_plan_with_modified_strategy_fails(self):
        """Se modificar strategy do PLAN, policy deve falhar."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        from agents.planner_agent import PlannerAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()
        planner = PlannerAgent()

        normalized = normalizer.normalize("sistema de clientes")
        srs = analyst.generate_srs(normalized, "CRM")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)
        plan = planner.generate_plan(ir, openapi, rbac)

        # Modificar strategy
        plan["meta"]["strategy"] = "FULL_REWRITE"

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan)

        assert is_valid is False
        assert any("PATCH_ONLY" in v for v in violations)


# ==================== PLAN CONTEXT POLICIES TESTS ====================


@pytest.fixture
def sample_ir():
    """Retorna um IR de exemplo para testes de contexto."""
    return {
        "meta": {"project_name": "Test", "version": "v1"},
        "domain": {
            "entities": [
                {
                    "name": "cliente",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "nome", "type": "string", "required": True},
                    ],
                }
            ],
            "relations": [],
            "workflows": [],
            "rules": [],
        },
        "api_intent": {"resources": ["cliente"]},
        "ui": {
            "pages": [
                {"path": "/app/cliente/list", "title": "List", "components": [], "actions": []},
                {"path": "/app/cliente/new", "title": "New", "components": [], "actions": []},
                {"path": "/app/cliente/:id", "title": "Detail", "components": [], "actions": []},
            ]
        },
        "nfr": {"security": {"auth_required": True}},
    }


@pytest.fixture
def sample_openapi():
    """Retorna um OpenAPI de exemplo para testes de contexto."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/api/clientes": {
                "get": {"operationId": "listCliente", "tags": ["clientes"], "responses": {"200": {"description": "OK"}}},
                "post": {"operationId": "createCliente", "tags": ["clientes"], "responses": {"201": {"description": "Created"}}},
            },
            "/api/clientes/{id}": {
                "get": {"operationId": "getCliente", "tags": ["clientes"], "responses": {"200": {"description": "OK"}}},
                "put": {"operationId": "updateCliente", "tags": ["clientes"], "responses": {"200": {"description": "OK"}}},
                "delete": {"operationId": "deleteCliente", "tags": ["clientes"], "responses": {"200": {"description": "OK"}}},
            },
        },
        "components": {"schemas": {"Cliente": {"type": "object"}}},
    }


@pytest.fixture
def complete_plan():
    """Retorna um PLAN completo para a entidade cliente."""
    return {
        "meta": {"version": "v1", "strategy": "PATCH_ONLY", "project_name": "Test"},
        "tasks": [
            {
                "id": "task_cliente_migration",
                "title": "Create DB migration",
                "order": 1,
                "files": ["backend/migrations/V1__create_cliente.sql"],
                "acceptance": ["Migration runs"],
            },
            {
                "id": "task_cliente_model",
                "title": "Create model",
                "order": 2,
                "files": ["backend/domain/Cliente.java"],
                "acceptance": ["Build passes"],
            },
            {
                "id": "task_cliente_repository",
                "title": "Create repository",
                "order": 3,
                "files": ["backend/repo/ClienteRepository.java"],
                "acceptance": ["Build passes"],
            },
            {
                "id": "task_cliente_service",
                "title": "Create service",
                "order": 4,
                "files": ["backend/service/ClienteService.java"],
                "acceptance": ["Build passes"],
            },
            {
                "id": "task_cliente_controller",
                "title": "Create controller",
                "order": 5,
                "files": ["backend/api/ClienteController.java"],
                "acceptance": [
                    "Contract tests pass",
                    "Implements operations: listCliente, createCliente, getCliente, updateCliente, deleteCliente",
                ],
            },
            {
                "id": "task_cliente_security",
                "title": "Configure security",
                "order": 6,
                "files": ["backend/security/SecurityConfig.java"],
                "acceptance": ["Auth required"],
            },
            {
                "id": "task_cliente_frontend_pages",
                "title": "Create frontend pages",
                "order": 7,
                "files": ["frontend/pages/cliente/List.tsx", "frontend/pages/cliente/New.tsx"],
                "acceptance": ["Pages render"],
            },
            {
                "id": "task_cliente_api_client",
                "title": "Create API client",
                "order": 8,
                "files": ["frontend/api/client.ts"],
                "acceptance": ["Build passes"],
            },
        ],
    }


class TestPlanEntityTasksPolicy:
    """Testes da policy: cada entidade deve ter tasks essenciais."""

    def test_complete_plan_passes(self, complete_plan, sample_ir, sample_openapi):
        """PLAN completo deve passar todas as policies."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is True, f"Violations: {violations}"

    def test_missing_migration_task_fails(self, complete_plan, sample_ir, sample_openapi):
        """PLAN sem task de migration deve falhar."""
        # Remover task de migration
        complete_plan["tasks"] = [t for t in complete_plan["tasks"] if "migration" not in t["id"]]
        # Ajustar orders
        for i, task in enumerate(complete_plan["tasks"]):
            task["order"] = i + 1

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        assert any("migration" in v for v in violations)

    def test_missing_controller_task_fails(self, complete_plan, sample_ir, sample_openapi):
        """PLAN sem task de controller deve falhar."""
        # Remover task de controller
        complete_plan["tasks"] = [t for t in complete_plan["tasks"] if "controller" not in t["id"]]
        # Ajustar orders
        for i, task in enumerate(complete_plan["tasks"]):
            task["order"] = i + 1

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        assert any("controller" in v for v in violations)

    def test_missing_frontend_task_fails(self, complete_plan, sample_ir, sample_openapi):
        """PLAN sem task de frontend pages deve falhar."""
        # Remover task de frontend_pages
        complete_plan["tasks"] = [t for t in complete_plan["tasks"] if "frontend_pages" not in t["id"]]
        # Ajustar orders
        for i, task in enumerate(complete_plan["tasks"]):
            task["order"] = i + 1

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        assert any("frontend" in v for v in violations)

    def test_missing_all_essential_tasks_reports_all(self, sample_ir, sample_openapi):
        """PLAN sem nenhuma task essencial deve reportar todas as violações."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {
                    "id": "task_something_else",
                    "title": "Something",
                    "order": 1,
                    "files": ["file.py"],
                    "acceptance": ["Done"],
                }
            ],
        }

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        # Deve ter violações para migration, controller, frontend
        assert any("migration" in v for v in violations)
        assert any("controller" in v for v in violations)
        assert any("frontend" in v for v in violations)


class TestPlanOperationsCoveragePolicy:
    """Testes da policy: todo operationId deve aparecer em tasks de controller."""

    def test_all_operations_covered_passes(self, complete_plan, sample_ir, sample_openapi):
        """PLAN com todos operationIds cobertos deve passar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is True, f"Violations: {violations}"

    def test_missing_operation_fails(self, complete_plan, sample_ir, sample_openapi):
        """PLAN sem cobertura de um operationId deve falhar."""
        # Remover deleteCliente da lista de operations no acceptance
        for task in complete_plan["tasks"]:
            if "controller" in task["id"]:
                task["acceptance"] = [
                    "Contract tests pass",
                    "Implements operations: listCliente, createCliente, getCliente, updateCliente",
                    # deleteCliente removido
                ]

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        assert any("deleteCliente" in v for v in violations)

    def test_missing_all_operations_reports_all(self, sample_ir, sample_openapi):
        """PLAN sem cobertura de operações deve reportar todas."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {
                    "id": "task_cliente_migration",
                    "title": "Migration",
                    "order": 1,
                    "files": ["m.sql"],
                    "acceptance": ["ok"],
                },
                {
                    "id": "task_cliente_controller",
                    "title": "Controller",
                    "order": 2,
                    "files": ["c.java"],
                    "acceptance": ["Contract tests pass"],  # Sem operationIds
                },
                {
                    "id": "task_cliente_frontend_pages",
                    "title": "Frontend",
                    "order": 3,
                    "files": ["f.tsx"],
                    "acceptance": ["ok"],
                },
            ],
        }

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan, ir=sample_ir, openapi=sample_openapi)

        assert is_valid is False
        # Deve ter violações para cada operationId
        operation_violations = [v for v in violations if "operationId" in v]
        assert len(operation_violations) == 5  # 5 operações no sample_openapi


class TestPlanContextPoliciesIntegration:
    """Testes de integração das policies de contexto com pipeline completo."""

    def test_planner_output_passes_context_policies(self):
        """Output do PlannerAgent deve passar policies de contexto."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        from agents.planner_agent import PlannerAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()
        planner = PlannerAgent()

        normalized = normalizer.normalize("sistema de clientes")
        srs = analyst.generate_srs(normalized, "CRM")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)
        plan = planner.generate_plan(ir, openapi, rbac)

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan, ir=ir, openapi=openapi)

        assert is_valid is True, f"Violations: {violations}"

    def test_removing_essential_task_breaks_policy(self):
        """Remover task essencial do output do PlannerAgent deve quebrar policy."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        from agents.planner_agent import PlannerAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()
        planner = PlannerAgent()

        normalized = normalizer.normalize("sistema de produtos")
        srs = analyst.generate_srs(normalized, "Produtos")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)
        plan = planner.generate_plan(ir, openapi, rbac)

        # Remover task de controller
        plan["tasks"] = [t for t in plan["tasks"] if "_controller" not in t["id"]]
        # Reajustar orders
        for i, task in enumerate(plan["tasks"]):
            task["order"] = i + 1

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan, ir=ir, openapi=openapi)

        assert is_valid is False
        assert any("controller" in v for v in violations)

    def test_plan_with_incomplete_tasks_fails(self):
        """PLAN com tasks incompletas deve falhar."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler
        from agents.contracts_agent import ContractsAgent
        from agents.planner_agent import PlannerAgent
        import yaml

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()
        contracts = ContractsAgent()
        planner = PlannerAgent()

        normalized = normalizer.normalize("sistema de pedidos")
        srs = analyst.generate_srs(normalized, "Pedidos")
        ir = modeler.generate_ir(srs)
        openapi_yaml, rbac = contracts.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)
        plan = planner.generate_plan(ir, openapi, rbac)

        # Remover operationIds do acceptance do controller
        for task in plan["tasks"]:
            if "_controller" in task["id"]:
                task["acceptance"] = ["Build passes"]  # Sem operationIds

        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(plan, ir=ir, openapi=openapi)

        assert is_valid is False
        # Deve ter violações de operationId não coberto
        assert any("operationId" in v for v in violations)


class TestPlanPolicyBackwardsCompatibility:
    """Testes de compatibilidade - validate_plan sem contexto ainda funciona."""

    def test_validate_plan_without_context_still_works(self, valid_plan):
        """validate_plan sem IR/OAS deve funcionar como antes."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(valid_plan)

        assert is_valid is True
        assert len(violations) == 0

    def test_validate_plan_with_only_ir(self, complete_plan, sample_ir):
        """validate_plan só com IR deve funcionar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, ir=sample_ir)

        # Deve passar as validações de entidade
        entity_violations = [v for v in violations if "entidade" in v]
        assert len(entity_violations) == 0

    def test_validate_plan_with_only_openapi(self, complete_plan, sample_openapi):
        """validate_plan só com OpenAPI deve funcionar."""
        validator = PolicyValidator()
        is_valid, violations = validator.validate_plan(complete_plan, openapi=sample_openapi)

        # Deve verificar cobertura de operações
        assert is_valid is True
