"""Contracts Agent - Gera OpenAPI e RBAC a partir do IR."""

from datetime import datetime
from typing import Any, Dict, List, Tuple

import yaml


class ContractsAgent:
    """Gera contratos OpenAPI e RBAC a partir do IR.

    Regras determinísticas v1:
    - Para cada entity gera CRUD padrão (5 rotas)
    - operationId fixo: list<Entity>, create<Entity>, get<Entity>, update<Entity>, delete<Entity>
    - tags = [Entity]
    - responses: 200/201 + 400 + 500
    - RBAC: roles = ["authenticated", "admin"], todas ops requerem "authenticated"
    """

    def __init__(self) -> None:
        self.openapi_version = "3.0.0"

    def generate_contracts(self, ir: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Gera OpenAPI YAML e RBAC dict a partir do IR.

        Args:
            ir: Intermediate Representation

        Returns:
            Tuple de (openapi_yaml_str, rbac_dict)
        """
        entities = self._extract_entities(ir)
        project_name = ir.get("meta", {}).get("project_name", "API")

        openapi = self._generate_openapi(entities, project_name)
        rbac = self._generate_rbac(entities)

        # Converter OpenAPI para YAML
        openapi_yaml = yaml.dump(openapi, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return openapi_yaml, rbac

    def _extract_entities(self, ir: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai entidades do IR."""
        domain = ir.get("domain", {})
        return domain.get("entities", [])

    def _pluralize(self, name: str) -> str:
        """Pluraliza nome da entidade (simples)."""
        if name.endswith("s"):
            return name + "es"
        elif name.endswith("y"):
            return name[:-1] + "ies"
        else:
            return name + "s"

    def _capitalize(self, name: str) -> str:
        """Capitaliza nome para uso em operationId."""
        return name[0].upper() + name[1:] if name else name

    def _generate_openapi(
        self, entities: List[Dict[str, Any]], project_name: str
    ) -> Dict[str, Any]:
        """Gera estrutura OpenAPI."""
        openapi = {
            "openapi": self.openapi_version,
            "info": {
                "title": f"{project_name} API",
                "version": "1.0.0",
                "description": f"API gerada automaticamente para {project_name}",
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
        }

        for entity in entities:
            entity_name = entity.get("name", "")
            if not entity_name:
                continue

            # Gerar paths CRUD
            paths = self._generate_crud_paths(entity)
            openapi["paths"].update(paths)

            # Gerar schema
            schema = self._generate_entity_schema(entity)
            openapi["components"]["schemas"][self._capitalize(entity_name)] = schema

        return openapi

    def _generate_crud_paths(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Gera paths CRUD para uma entidade."""
        name = entity.get("name", "")
        plural = self._pluralize(name)
        capitalized = self._capitalize(name)
        tag = capitalized

        paths = {}

        # Collection path: /api/{plural}
        collection_path = f"/api/{plural}"
        paths[collection_path] = {
            "get": self._create_operation(
                operation_id=f"list{capitalized}",
                tags=[tag],
                summary=f"Listar {plural}",
                responses={
                    "200": {"description": f"Lista de {plural}"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
            ),
            "post": self._create_operation(
                operation_id=f"create{capitalized}",
                tags=[tag],
                summary=f"Criar {name}",
                responses={
                    "201": {"description": f"{capitalized} criado"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
                request_body={
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{capitalized}"}
                        }
                    }
                },
            ),
        }

        # Item path: /api/{plural}/{id}
        item_path = f"/api/{plural}/{{id}}"
        paths[item_path] = {
            "get": self._create_operation(
                operation_id=f"get{capitalized}",
                tags=[tag],
                summary=f"Obter {name} por ID",
                responses={
                    "200": {"description": f"Detalhes do {name}"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
                parameters=[
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            ),
            "put": self._create_operation(
                operation_id=f"update{capitalized}",
                tags=[tag],
                summary=f"Atualizar {name}",
                responses={
                    "200": {"description": f"{capitalized} atualizado"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
                parameters=[
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                request_body={
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{capitalized}"}
                        }
                    }
                },
            ),
            "delete": self._create_operation(
                operation_id=f"delete{capitalized}",
                tags=[tag],
                summary=f"Deletar {name}",
                responses={
                    "200": {"description": f"{capitalized} deletado"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
                parameters=[
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            ),
        }

        return paths

    def _create_operation(
        self,
        operation_id: str,
        tags: List[str],
        summary: str,
        responses: Dict[str, Any],
        parameters: List[Dict[str, Any]] = None,
        request_body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Cria uma operação OpenAPI."""
        operation = {
            "operationId": operation_id,
            "tags": tags,
            "summary": summary,
            "responses": responses,
        }

        if parameters:
            operation["parameters"] = parameters

        if request_body:
            operation["requestBody"] = request_body

        return operation

    def _generate_entity_schema(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Gera schema para uma entidade."""
        fields = entity.get("fields", [])

        properties = {}
        required = []

        for field in fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "string")

            # id sempre string
            if field_name == "id":
                field_type = "string"

            # Mapear tipos do IR para OpenAPI
            openapi_type = self._map_type(field_type)
            properties[field_name] = {"type": openapi_type}

            if field.get("required", False):
                required.append(field_name)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    def _map_type(self, ir_type: str) -> str:
        """Mapeia tipo do IR para tipo OpenAPI."""
        type_mapping = {
            "string": "string",
            "uuid": "string",
            "text": "string",
            "integer": "integer",
            "int": "integer",
            "number": "number",
            "float": "number",
            "boolean": "boolean",
            "bool": "boolean",
            "date": "string",
            "datetime": "string",
            "array": "array",
            "object": "object",
        }
        return type_mapping.get(ir_type.lower(), "string")

    def _generate_rbac(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Gera RBAC para todas as entidades."""
        permissions = []

        for entity in entities:
            name = entity.get("name", "")
            if not name:
                continue

            capitalized = self._capitalize(name)

            # CRUD operations
            operations = [
                f"list{capitalized}",
                f"create{capitalized}",
                f"get{capitalized}",
                f"update{capitalized}",
                f"delete{capitalized}",
            ]

            for op_id in operations:
                permissions.append({
                    "operation_id": op_id,
                    "required_role": "authenticated",
                })

        rbac = {
            "roles": ["authenticated", "admin"],
            "permissions": permissions,
            "meta": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0",
            }
        }

        return rbac
