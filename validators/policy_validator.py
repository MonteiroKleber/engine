"""Validador de políticas para IR, Contracts e PLAN."""

import unicodedata
from typing import Any, Dict, List, Optional, Tuple


class PolicyValidator:
    """Valida IR, Contracts e PLAN contra políticas de consistência.

    Policies obrigatórias para IR:
    - api_intent.resources deve conter todas entidades
    - ui.pages deve existir para cada entidade (mínimo list/new/detail)
    - nfr.security.auth_required deve ser boolean
    - se domain.entities estiver vazio → FAIL (bloqueia)

    Policies obrigatórias para Contracts:
    - Todo operationId no OpenAPI deve existir em rbac.permissions[].operation_id
    - rbac.roles deve conter 'authenticated'
    - Nenhuma operação pode ficar sem permissão
    - OpenAPI deve ter components/schemas

    Policies obrigatórias para PLAN (básicas):
    - meta.strategy deve ser PATCH_ONLY
    - Pelo menos uma task deve existir
    - Cada task deve ter files não vazio
    - Cada task deve ter acceptance não vazio

    Policies obrigatórias para PLAN (com contexto IR/OAS):
    - Para cada entidade do IR deve existir:
      - 1 task de DB (migration)
      - 1 task de backend controller
      - 1 task de frontend page
    - Todo operationId do OAS deve aparecer em alguma task de controller
    """

    def __init__(self) -> None:
        self.policies: List[Dict[str, Any]] = []

    def add_policy(self, policy: Dict[str, Any]) -> None:
        """Adiciona uma política de validação customizada."""
        self.policies.append(policy)

    def validate(self, ir: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Valida IR contra políticas de consistência.

        Args:
            ir: Documento IR a validar

        Returns:
            Tuple de (is_valid, list of violations)
        """
        violations: List[str] = []

        # Policy 1: domain.entities não pode estar vazio
        violations.extend(self._check_entities_not_empty(ir))

        # Policy 2: api_intent.resources deve conter todas entidades
        violations.extend(self._check_api_resources_match_entities(ir))

        # Policy 3: ui.pages deve existir para cada entidade
        violations.extend(self._check_ui_pages_for_entities(ir))

        # Policy 4: nfr.security.auth_required deve ser boolean
        violations.extend(self._check_nfr_auth_required_type(ir))

        return len(violations) == 0, violations

    def _check_entities_not_empty(self, ir: Dict[str, Any]) -> List[str]:
        """Verifica se domain.entities não está vazio."""
        violations = []

        domain = ir.get("domain", {})
        entities = domain.get("entities", [])

        if not entities:
            violations.append("POLICY_FAIL: domain.entities está vazio - IR bloqueado")

        return violations

    def _check_api_resources_match_entities(self, ir: Dict[str, Any]) -> List[str]:
        """Verifica se api_intent.resources contém todas as entidades."""
        violations = []

        domain = ir.get("domain", {})
        entities = domain.get("entities", [])
        entity_names = {e.get("name", "") for e in entities}

        api_intent = ir.get("api_intent", {})
        resources = set(api_intent.get("resources", []))

        # Verificar se todas as entidades têm resource
        missing_resources = entity_names - resources
        for entity in missing_resources:
            violations.append(
                f"POLICY_FAIL: entidade '{entity}' não tem resource em api_intent"
            )

        return violations

    def _check_ui_pages_for_entities(self, ir: Dict[str, Any]) -> List[str]:
        """Verifica se cada entidade tem páginas UI (list, new, detail)."""
        violations = []

        domain = ir.get("domain", {})
        entities = domain.get("entities", [])
        entity_names = [e.get("name", "") for e in entities]

        ui = ir.get("ui", {})
        pages = ui.get("pages", [])

        # Extrair paths das páginas
        page_paths = [p.get("path", "") for p in pages]

        for entity in entity_names:
            # Verificar página de listagem (deve terminar com /list ou ser exatamente /{entity})
            has_list = any(
                path.endswith(f"/{entity}/list") or path == f"/{entity}"
                for path in page_paths
            )

            # Verificar página de criação
            has_new = any(
                path.endswith(f"/{entity}/new") or path.endswith(f"/{entity}/create")
                for path in page_paths
            )

            # Verificar página de detalhe
            has_detail = any(
                path.endswith(f"/{entity}/:id") or path.endswith(f"/{entity}/{{id}}")
                for path in page_paths
            )

            if not has_list:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity}' não tem página de listagem"
                )

            if not has_new:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity}' não tem página de criação"
                )

            if not has_detail:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity}' não tem página de detalhe"
                )

        return violations

    def _check_nfr_auth_required_type(self, ir: Dict[str, Any]) -> List[str]:
        """Verifica se nfr.security.auth_required é boolean."""
        violations = []

        nfr = ir.get("nfr", {})
        security = nfr.get("security", {})

        if "auth_required" in security:
            auth_required = security["auth_required"]
            if not isinstance(auth_required, bool):
                violations.append(
                    f"POLICY_FAIL: nfr.security.auth_required deve ser boolean, "
                    f"encontrado {type(auth_required).__name__}"
                )

        return violations

    # ==================== CONTRACTS POLICIES ====================

    def validate_contracts(
        self, openapi: Dict[str, Any], rbac: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Valida OpenAPI e RBAC contra políticas de consistência.

        Args:
            openapi: Documento OpenAPI (dict)
            rbac: Documento RBAC (dict)

        Returns:
            Tuple de (is_valid, list of violations)
        """
        violations: List[str] = []

        # Policy 1: Todo operationId no OpenAPI deve existir no RBAC
        violations.extend(self._check_all_operations_have_permission(openapi, rbac))

        # Policy 2: Toda permissão no RBAC deve referenciar operação no OpenAPI
        violations.extend(self._check_all_permissions_have_operation(openapi, rbac))

        # Policy 3: rbac.roles deve conter 'authenticated'
        violations.extend(self._check_rbac_has_authenticated_role(rbac))

        # Policy 4: OpenAPI deve ter components/schemas
        violations.extend(self._check_openapi_has_schemas(openapi))

        return len(violations) == 0, violations

    def _extract_operation_ids_from_openapi(self, openapi: Dict[str, Any]) -> set:
        """Extrai todos os operationIds do OpenAPI."""
        operation_ids: set = set()
        http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

        paths = openapi.get("paths", {})
        for path_item in paths.values():
            if isinstance(path_item, dict):
                for method, operation in path_item.items():
                    if method.lower() in http_methods and isinstance(operation, dict):
                        op_id = operation.get("operationId")
                        if op_id:
                            operation_ids.add(op_id)

        return operation_ids

    def _extract_operation_ids_from_rbac(self, rbac: Dict[str, Any]) -> set:
        """Extrai todos os operation_ids do RBAC."""
        operation_ids: set = set()

        for perm in rbac.get("permissions", []):
            op_id = perm.get("operation_id")
            if op_id:
                operation_ids.add(op_id)

        return operation_ids

    def _check_all_operations_have_permission(
        self, openapi: Dict[str, Any], rbac: Dict[str, Any]
    ) -> List[str]:
        """Verifica se toda operação no OpenAPI tem permissão no RBAC."""
        violations = []

        oas_op_ids = self._extract_operation_ids_from_openapi(openapi)
        rbac_op_ids = self._extract_operation_ids_from_rbac(rbac)

        missing_in_rbac = oas_op_ids - rbac_op_ids
        for op_id in sorted(missing_in_rbac):
            violations.append(
                f"POLICY_FAIL: operação '{op_id}' no OpenAPI não tem permissão no RBAC"
            )

        return violations

    def _check_all_permissions_have_operation(
        self, openapi: Dict[str, Any], rbac: Dict[str, Any]
    ) -> List[str]:
        """Verifica se toda permissão no RBAC referencia operação existente no OpenAPI."""
        violations = []

        oas_op_ids = self._extract_operation_ids_from_openapi(openapi)
        rbac_op_ids = self._extract_operation_ids_from_rbac(rbac)

        orphan_in_rbac = rbac_op_ids - oas_op_ids
        for op_id in sorted(orphan_in_rbac):
            violations.append(
                f"POLICY_FAIL: permissão '{op_id}' no RBAC não existe no OpenAPI"
            )

        return violations

    def _check_rbac_has_authenticated_role(self, rbac: Dict[str, Any]) -> List[str]:
        """Verifica se rbac.roles contém 'authenticated'."""
        violations = []

        roles = rbac.get("roles", [])
        if "authenticated" not in roles:
            violations.append(
                "POLICY_FAIL: rbac.roles deve conter 'authenticated'"
            )

        return violations

    def _check_openapi_has_schemas(self, openapi: Dict[str, Any]) -> List[str]:
        """Verifica se OpenAPI tem components/schemas."""
        violations = []

        components = openapi.get("components", {})
        schemas = components.get("schemas", {})

        if not schemas:
            violations.append(
                "POLICY_FAIL: OpenAPI deve ter components/schemas definidos"
            )

        return violations

    # ==================== PLAN POLICIES ====================

    def validate_plan(
        self,
        plan: Dict[str, Any],
        ir: Optional[Dict[str, Any]] = None,
        openapi: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """Valida PLAN contra políticas de consistência.

        Args:
            plan: Documento PLAN a validar
            ir: Intermediate Representation (opcional, para validações avançadas)
            openapi: OpenAPI specification (opcional, para validações avançadas)

        Returns:
            Tuple de (is_valid, list of violations)
        """
        violations: List[str] = []

        # Policy 1: meta.strategy deve ser PATCH_ONLY
        violations.extend(self._check_plan_strategy(plan))

        # Policy 2: Pelo menos uma task deve existir
        violations.extend(self._check_plan_has_tasks(plan))

        # Policy 3: Cada task deve ter files não vazio
        violations.extend(self._check_plan_tasks_have_files(plan))

        # Policy 4: Cada task deve ter acceptance não vazio
        violations.extend(self._check_plan_tasks_have_acceptance(plan))

        # Validações avançadas (requerem IR e/ou OAS)
        if ir is not None:
            # Policy 5: Para cada entidade do IR deve existir tasks essenciais
            violations.extend(self._check_plan_has_entity_tasks(plan, ir))

        if openapi is not None:
            # Policy 6: Todo operationId do OAS deve aparecer em alguma task
            violations.extend(self._check_plan_covers_operations(plan, openapi))

        return len(violations) == 0, violations

    def _check_plan_strategy(self, plan: Dict[str, Any]) -> List[str]:
        """Verifica se meta.strategy é PATCH_ONLY."""
        violations = []

        meta = plan.get("meta", {})
        strategy = meta.get("strategy")

        if strategy != "PATCH_ONLY":
            violations.append(
                f"POLICY_FAIL: meta.strategy deve ser 'PATCH_ONLY', encontrado '{strategy}'"
            )

        return violations

    def _check_plan_has_tasks(self, plan: Dict[str, Any]) -> List[str]:
        """Verifica se PLAN tem pelo menos uma task."""
        violations = []

        tasks = plan.get("tasks", [])

        if not tasks:
            violations.append("POLICY_FAIL: PLAN deve ter pelo menos uma task")

        return violations

    def _check_plan_tasks_have_files(self, plan: Dict[str, Any]) -> List[str]:
        """Verifica se cada task tem files não vazio."""
        violations = []

        tasks = plan.get("tasks", [])

        for i, task in enumerate(tasks):
            task_id = task.get("id", f"task[{i}]")
            files = task.get("files", [])

            if not files:
                violations.append(
                    f"POLICY_FAIL: task '{task_id}' deve ter files não vazio"
                )

        return violations

    def _check_plan_tasks_have_acceptance(self, plan: Dict[str, Any]) -> List[str]:
        """Verifica se cada task tem acceptance não vazio."""
        violations = []

        tasks = plan.get("tasks", [])

        for i, task in enumerate(tasks):
            task_id = task.get("id", f"task[{i}]")
            acceptance = task.get("acceptance", [])

            if not acceptance:
                violations.append(
                    f"POLICY_FAIL: task '{task_id}' deve ter acceptance não vazio"
                )

        return violations

    def _normalize_name(self, name: str) -> str:
        """Remove acentos e caracteres especiais do nome."""
        normalized = unicodedata.normalize("NFD", name)
        ascii_name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return ascii_name

    def _to_snake_case(self, name: str) -> str:
        """Converte para snake_case (ASCII only)."""
        name = self._normalize_name(name)
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _check_plan_has_entity_tasks(
        self, plan: Dict[str, Any], ir: Dict[str, Any]
    ) -> List[str]:
        """Verifica se cada entidade do IR tem tasks essenciais no PLAN.

        Para cada entidade deve existir:
        - 1 task de DB (migration) - id contém '_migration'
        - 1 task de backend controller - id contém '_controller'
        - 1 task de frontend page - id contém '_frontend_pages'
        """
        violations = []

        domain = ir.get("domain", {})
        entities = domain.get("entities", [])
        tasks = plan.get("tasks", [])

        # Extrair task_ids
        task_ids = [t.get("id", "") for t in tasks]

        for entity in entities:
            entity_name = entity.get("name", "")
            snake_name = self._to_snake_case(entity_name)

            # Verificar task de migration
            has_migration = any(
                f"task_{snake_name}_migration" in task_id
                for task_id in task_ids
            )
            if not has_migration:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity_name}' não tem task de DB migration"
                )

            # Verificar task de controller
            has_controller = any(
                f"task_{snake_name}_controller" in task_id
                for task_id in task_ids
            )
            if not has_controller:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity_name}' não tem task de backend controller"
                )

            # Verificar task de frontend pages
            has_frontend = any(
                f"task_{snake_name}_frontend_pages" in task_id
                for task_id in task_ids
            )
            if not has_frontend:
                violations.append(
                    f"POLICY_FAIL: entidade '{entity_name}' não tem task de frontend page"
                )

        return violations

    def _check_plan_covers_operations(
        self, plan: Dict[str, Any], openapi: Dict[str, Any]
    ) -> List[str]:
        """Verifica se todo operationId do OAS aparece em alguma task.

        Os operationIds devem aparecer no campo 'acceptance' das tasks
        de controller (via string como "Implements operations: op1, op2").
        """
        violations = []

        # Extrair operationIds do OpenAPI
        oas_op_ids = self._extract_operation_ids_from_openapi(openapi)

        if not oas_op_ids:
            return violations

        # Extrair todos os acceptance de tasks de controller
        tasks = plan.get("tasks", [])
        acceptance_texts = []
        for task in tasks:
            task_id = task.get("id", "")
            # Incluir acceptance de tasks de controller
            if "_controller" in task_id:
                for acc in task.get("acceptance", []):
                    acceptance_texts.append(acc)

        # Concatenar todos os textos de acceptance
        all_acceptance = " ".join(acceptance_texts)

        # Verificar cada operationId
        for op_id in sorted(oas_op_ids):
            if op_id not in all_acceptance:
                violations.append(
                    f"POLICY_FAIL: operationId '{op_id}' não está coberto em nenhuma task de controller"
                )

        return violations
