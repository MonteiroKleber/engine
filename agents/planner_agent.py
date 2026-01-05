"""Planner Agent - Gera PLAN a partir de IR, OpenAPI e RBAC."""

import unicodedata
from datetime import datetime
from typing import Any, Dict, List


class PlannerAgent:
    """Gera plano de implementação a partir de IR, OpenAPI e RBAC.

    Regras determinísticas v1 (sem LLM):
    Para cada entidade em ir.domain.entities, gera tasks na ordem fixa:
    1) DB migrations
    2) Backend model (JPA Entity)
    3) Repository
    4) Service
    5) Controller CRUD
    6) Security mapping (RBAC)
    7) Frontend pages CRUD
    8) API client
    """

    # Base package para código Java
    BASE_PACKAGE = "com/example/app"

    def __init__(self) -> None:
        self.task_counter = 0

    def generate_plan(
        self,
        ir: Dict[str, Any],
        openapi: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Gera plano de implementação.

        Args:
            ir: Intermediate Representation
            openapi: OpenAPI specification dict
            rbac: RBAC definition dict

        Returns:
            PLAN dict com meta e tasks
        """
        self.task_counter = 0

        entities = self._extract_entities(ir)
        project_name = ir.get("meta", {}).get("project_name", "Project")
        ir_version = ir.get("meta", {}).get("version", "v1")

        tasks: List[Dict[str, Any]] = []

        # Gerar tasks para cada entidade
        for entity in entities:
            entity_tasks = self._generate_entity_tasks(entity, openapi, rbac)
            tasks.extend(entity_tasks)

        return {
            "meta": {
                "version": "v1",
                "strategy": "PATCH_ONLY",
                "ir_version": ir_version,
                "project_name": project_name,
                "created_at": datetime.now().isoformat(),
            },
            "tasks": tasks,
        }

    def _extract_entities(self, ir: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai entidades do IR."""
        domain = ir.get("domain", {})
        return domain.get("entities", [])

    def _next_order(self) -> int:
        """Retorna próximo número de ordem (1-based)."""
        self.task_counter += 1
        return self.task_counter

    def _normalize_name(self, name: str) -> str:
        """Remove acentos e caracteres especiais do nome.

        Converte caracteres acentuados para ASCII equivalente:
        - ç -> c
        - á, à, ã, â -> a
        - é, ê -> e
        - í -> i
        - ó, ô, õ -> o
        - ú -> u
        """
        # Normaliza para NFD (decompõe caracteres acentuados)
        normalized = unicodedata.normalize("NFD", name)
        # Remove marcas de acento (categoria 'Mn' = Mark, Nonspacing)
        ascii_name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return ascii_name

    def _to_snake_case(self, name: str) -> str:
        """Converte para snake_case (ASCII only)."""
        # Primeiro normaliza para remover acentos
        name = self._normalize_name(name)
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _capitalize(self, name: str) -> str:
        """Capitaliza primeira letra (mantém acentos para display)."""
        return name[0].upper() + name[1:] if name else name

    def _capitalize_ascii(self, name: str) -> str:
        """Capitaliza primeira letra (ASCII only para paths)."""
        name = self._normalize_name(name)
        return name[0].upper() + name[1:] if name else name

    def _get_operation_ids_for_entity(
        self, entity_name: str, openapi: Dict[str, Any]
    ) -> List[str]:
        """Extrai operationIds do OpenAPI para uma entidade."""
        operation_ids = []
        capitalized = self._capitalize(entity_name)
        paths = openapi.get("paths", {})

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                op_id = operation.get("operationId", "")
                if capitalized in op_id:
                    operation_ids.append(op_id)

        return operation_ids

    def _generate_entity_tasks(
        self,
        entity: Dict[str, Any],
        openapi: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Gera 8 tasks para uma entidade."""
        entity_name = entity.get("name", "entity")
        snake_name = self._to_snake_case(entity_name)  # ASCII snake_case
        capitalized = self._capitalize(entity_name)  # Display name (mantém acentos)
        capitalized_ascii = self._capitalize_ascii(entity_name)  # Para file paths
        operation_ids = self._get_operation_ids_for_entity(entity_name, openapi)

        tasks = []

        # 1) DB migrations
        tasks.append({
            "id": f"task_{snake_name}_migration",
            "title": f"Create database migration for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/resources/db/migration/V{self.task_counter}__create_{snake_name}.sql"
            ],
            "acceptance": [
                "Migration compiles without errors",
                f"Table {snake_name} exists in database",
            ],
        })

        # 2) Backend model (JPA Entity)
        tasks.append({
            "id": f"task_{snake_name}_model",
            "title": f"Create JPA Entity for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/java/{self.BASE_PACKAGE}/domain/{capitalized_ascii}.java"
            ],
            "acceptance": [
                "Build backend passes",
                f"{capitalized} entity has all required fields",
            ],
            "depends_on": [f"task_{snake_name}_migration"],
        })

        # 3) Repository
        tasks.append({
            "id": f"task_{snake_name}_repository",
            "title": f"Create Repository for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/java/{self.BASE_PACKAGE}/repo/{capitalized_ascii}Repository.java"
            ],
            "acceptance": [
                "Build backend passes",
                f"{capitalized}Repository extends JpaRepository",
            ],
            "depends_on": [f"task_{snake_name}_model"],
        })

        # 4) Service
        tasks.append({
            "id": f"task_{snake_name}_service",
            "title": f"Create Service for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/java/{self.BASE_PACKAGE}/service/{capitalized_ascii}Service.java"
            ],
            "acceptance": [
                "Build backend passes",
                f"{capitalized}Service has CRUD methods",
            ],
            "depends_on": [f"task_{snake_name}_repository"],
        })

        # 5) Controller CRUD
        acceptance_controller = [
            "Contract tests pass",
            "All endpoints return correct status codes",
        ]
        if operation_ids:
            acceptance_controller.append(f"Implements operations: {', '.join(operation_ids)}")

        tasks.append({
            "id": f"task_{snake_name}_controller",
            "title": f"Create REST Controller for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/java/{self.BASE_PACKAGE}/api/{capitalized_ascii}Controller.java"
            ],
            "acceptance": acceptance_controller,
            "depends_on": [f"task_{snake_name}_service"],
        })

        # 6) Security mapping (RBAC)
        tasks.append({
            "id": f"task_{snake_name}_security",
            "title": f"Configure security for {capitalized} endpoints",
            "order": self._next_order(),
            "files": [
                f"backend/src/main/java/{self.BASE_PACKAGE}/security/SecurityConfig.java"
            ],
            "acceptance": [
                "Endpoints require authentication",
                "RBAC roles are enforced",
            ],
            "depends_on": [f"task_{snake_name}_controller"],
        })

        # 7) Frontend pages CRUD
        tasks.append({
            "id": f"task_{snake_name}_frontend_pages",
            "title": f"Create frontend pages for {capitalized}",
            "order": self._next_order(),
            "files": [
                f"frontend/src/pages/{snake_name}/List.tsx",
                f"frontend/src/pages/{snake_name}/New.tsx",
                f"frontend/src/pages/{snake_name}/Detail.tsx",
            ],
            "acceptance": [
                "TypeScript typecheck passes",
                "Pages render without errors",
            ],
            "depends_on": [f"task_{snake_name}_controller"],
        })

        # 8) API client
        tasks.append({
            "id": f"task_{snake_name}_api_client",
            "title": f"Create API client for {capitalized}",
            "order": self._next_order(),
            "files": [
                "frontend/src/api/client.ts"
            ],
            "acceptance": [
                "Build frontend passes",
                f"API client has methods for {capitalized} CRUD",
            ],
            "depends_on": [f"task_{snake_name}_frontend_pages"],
        })

        return tasks
