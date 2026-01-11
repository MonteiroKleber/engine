"""IDL to IR Converter.

Converte um IDLDocument para o formato IR esperado pelo pipeline.

O IR é gerado diretamente a partir do IDL, sem passar por SRS.
Isso permite que entradas IDL pulem a fase de análise de requisitos
e vão direto para a geração de contratos.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .idl_v1 import (
    IDLDocument,
    EntityDefinition,
    FieldDefinition,
    RelationDefinition,
    UseCaseDefinition,
    ActorDefinition,
    NFRDefinition,
    RelationType,
    PriorityLevel,
)


@dataclass
class IDLToIRError(Exception):
    """Erro na conversão IDL → IR."""
    message: str
    error_code: str

    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


# Mapeamento de tipos IDL → tipos IR
TYPE_MAPPING = {
    "string": "string",
    "text": "text",
    "int": "integer",
    "integer": "integer",
    "float": "decimal",
    "decimal": "decimal",
    "bool": "boolean",
    "boolean": "boolean",
    "datetime": "datetime",
    "date": "date",
    "uuid": "uuid",
    "email": "string",
    "phone": "string",
    "url": "string",
}


def _map_field_type(idl_type: str) -> str:
    """Mapeia tipo IDL para tipo IR."""
    # Remover qualquer prefixo list<> ou set<>
    base_type = idl_type.lower()
    if base_type.startswith("list<") or base_type.startswith("set<"):
        # Extrair tipo interno
        inner = base_type.split("<")[1].rstrip(">")
        return TYPE_MAPPING.get(inner, "string")
    return TYPE_MAPPING.get(base_type, "string")


def _convert_entity(entity: EntityDefinition) -> Dict[str, Any]:
    """Converte EntityDefinition para formato IR."""
    fields = []

    # Adicionar campo ID se não existir
    has_id = any(f.id.lower() == "id" for f in entity.fields)
    if not has_id:
        fields.append({
            "name": "id",
            "type": "uuid",
            "required": True,
            "unique": True,
            "indexed": True,
        })

    # Converter campos
    for field in entity.fields:
        field_dict = {
            "name": field.id,
            "type": _map_field_type(field.field_type),
            "required": field.required,
            "unique": field.unique,
            "indexed": field.indexed,
        }
        if field.default is not None:
            field_dict["default"] = field.default
        fields.append(field_dict)

    # Adicionar campos de FK para relações belongs_to
    for rel in entity.relations:
        if rel.relation_type == RelationType.BELONGS_TO:
            fk_name = f"{rel.target_entity.lower()}_id"
            if not any(f["name"] == fk_name for f in fields):
                fields.append({
                    "name": fk_name,
                    "type": "uuid",
                    "required": True,
                    "unique": False,
                    "indexed": True,
                })

    return {
        "name": entity.id.lower(),
        "primary_key": "id",
        "fields": fields,
    }


def _convert_relations(entities: List[EntityDefinition]) -> List[Dict[str, Any]]:
    """Converte relações IDL para formato IR."""
    relations = []

    for entity in entities:
        for rel in entity.relations:
            relation_dict = {
                "from_entity": entity.id.lower(),
                "to_entity": rel.target_entity.lower(),
                "type": rel.relation_type.value,
                "fk_field": f"{rel.target_entity.lower()}_id" if rel.relation_type == RelationType.BELONGS_TO else None,
            }
            if rel.cascade_delete:
                relation_dict["on_delete"] = "cascade"
            relations.append(relation_dict)

    return relations


def _usecase_to_operations(
    usecase: UseCaseDefinition,
    entities: List[EntityDefinition],
) -> List[Dict[str, Any]]:
    """Deriva operações CRUD a partir de um usecase."""
    operations = []

    # Inferir entidade principal do usecase
    # Estratégia: procurar nome da entidade no id/name do usecase
    target_entity = None
    usecase_lower = usecase.id.lower()

    for entity in entities:
        if entity.id.lower() in usecase_lower:
            target_entity = entity.id.lower()
            break

    # Se não encontrou, usar primeira entidade
    if not target_entity and entities:
        target_entity = entities[0].id.lower()

    if not target_entity:
        return operations

    # Inferir operação a partir do nome do usecase
    if "create" in usecase_lower or "cadastr" in usecase_lower or "novo" in usecase_lower or "add" in usecase_lower:
        operations.append({
            "entity": target_entity,
            "verb": "POST",
            "path": f"/{target_entity}",
            "summary": usecase.name or f"Create {target_entity}",
            "derived_from": usecase.id,
        })
    if "list" in usecase_lower or "listar" in usecase_lower or "search" in usecase_lower or "buscar" in usecase_lower:
        operations.append({
            "entity": target_entity,
            "verb": "GET",
            "path": f"/{target_entity}",
            "summary": usecase.name or f"List {target_entity}",
            "derived_from": usecase.id,
        })
    if "update" in usecase_lower or "edit" in usecase_lower or "atualiz" in usecase_lower or "alter" in usecase_lower:
        operations.append({
            "entity": target_entity,
            "verb": "PUT",
            "path": f"/{target_entity}/{{id}}",
            "summary": usecase.name or f"Update {target_entity}",
            "derived_from": usecase.id,
        })
    if "delete" in usecase_lower or "remov" in usecase_lower or "exclu" in usecase_lower:
        operations.append({
            "entity": target_entity,
            "verb": "DELETE",
            "path": f"/{target_entity}/{{id}}",
            "summary": usecase.name or f"Delete {target_entity}",
            "derived_from": usecase.id,
        })
    if "view" in usecase_lower or "detail" in usecase_lower or "visualiz" in usecase_lower or "get" in usecase_lower:
        operations.append({
            "entity": target_entity,
            "verb": "GET",
            "path": f"/{target_entity}/{{id}}",
            "summary": usecase.name or f"Get {target_entity}",
            "derived_from": usecase.id,
        })

    # Se não inferiu nada, criar CRUD básico
    if not operations:
        operations = [
            {
                "entity": target_entity,
                "verb": "POST",
                "path": f"/{target_entity}",
                "summary": f"Create {target_entity}",
                "derived_from": usecase.id,
            },
            {
                "entity": target_entity,
                "verb": "GET",
                "path": f"/{target_entity}",
                "summary": f"List {target_entity}",
                "derived_from": usecase.id,
            },
        ]

    return operations


def _generate_crud_for_entity(entity: EntityDefinition) -> List[Dict[str, Any]]:
    """Gera operações CRUD padrão para uma entidade."""
    entity_name = entity.id.lower()
    return [
        {
            "entity": entity_name,
            "verb": "GET",
            "path": f"/{entity_name}",
            "summary": f"List all {entity_name}",
        },
        {
            "entity": entity_name,
            "verb": "POST",
            "path": f"/{entity_name}",
            "summary": f"Create {entity_name}",
        },
        {
            "entity": entity_name,
            "verb": "GET",
            "path": f"/{entity_name}/{{id}}",
            "summary": f"Get {entity_name} by ID",
        },
        {
            "entity": entity_name,
            "verb": "PUT",
            "path": f"/{entity_name}/{{id}}",
            "summary": f"Update {entity_name}",
        },
        {
            "entity": entity_name,
            "verb": "DELETE",
            "path": f"/{entity_name}/{{id}}",
            "summary": f"Delete {entity_name}",
        },
    ]


def _convert_actors_to_roles(actors: List[ActorDefinition]) -> List[Dict[str, Any]]:
    """Converte atores IDL para roles RBAC."""
    roles = []
    for actor in actors:
        permissions = []
        if actor.permissions:
            permissions = [p for p in actor.permissions]

        roles.append({
            "id": actor.id.lower(),
            "name": actor.name or actor.id,
            "description": actor.description or "",
            "permissions": permissions,
        })
    return roles


def _convert_nfr(nfr: NFRDefinition) -> Dict[str, Any]:
    """Converte NFR IDL para formato IR."""
    return {
        "id": nfr.id,
        "type": nfr.nfr_type.value if nfr.nfr_type else "general",
        "name": nfr.name or nfr.id,
        "description": nfr.description or "",
        "metric": nfr.metric or "",
        "target": nfr.target or "",
        "priority": nfr.priority.value if nfr.priority else "medium",
    }


def _generate_ui_pages(entities: List[EntityDefinition]) -> List[Dict[str, Any]]:
    """Gera páginas de UI para entidades (formato IR schema)."""
    pages = []
    for entity in entities:
        entity_name = entity.id.lower()
        pages.extend([
            {
                "path": f"/app/{entity_name}/list",
                "title": f"Listar {entity.id}",
                "components": ["table", "pagination", "search"],
                "actions": ["list", "view", "delete"],
            },
            {
                "path": f"/app/{entity_name}/new",
                "title": f"Novo {entity.id}",
                "components": ["form"],
                "actions": ["create"],
            },
            {
                "path": f"/app/{entity_name}/:id",
                "title": f"Detalhes {entity.id}",
                "components": ["form"],
                "actions": ["view", "update", "delete"],
            },
        ])
    return pages


def _convert_nfr_to_ir_format(nfrs: List[NFRDefinition]) -> Dict[str, Any]:
    """Converte NFRs IDL para formato IR schema (objeto com security/performance/availability)."""
    result: Dict[str, Any] = {}

    for nfr in nfrs:
        nfr_type = nfr.nfr_type.value if nfr.nfr_type else "general"

        if nfr_type == "security":
            if "security" not in result:
                result["security"] = {}
            result["security"]["auth_required"] = True
            result["security"]["audit_log_required"] = True

        elif nfr_type == "performance":
            if "performance" not in result:
                result["performance"] = {}
            # Tentar extrair max_response_time do target
            if nfr.target and "ms" in nfr.target:
                try:
                    # Extrair número do target (ex: "< 300ms" -> 300)
                    import re
                    match = re.search(r'(\d+)', nfr.target)
                    if match:
                        result["performance"]["max_response_time_ms"] = int(match.group(1))
                except (ValueError, AttributeError):
                    result["performance"]["max_response_time_ms"] = 3000

        elif nfr_type == "availability":
            if "availability" not in result:
                result["availability"] = {}
            result["availability"]["uptime_sla"] = nfr.target or "99.5%"

    return result


def idl_to_ir(doc: IDLDocument, project_title: str = "Sistema") -> Dict[str, Any]:
    """Converte IDLDocument para formato IR.

    Args:
        doc: Documento IDL parseado
        project_title: Título do projeto

    Returns:
        Dicionário no formato IR esperado pelo pipeline

    Raises:
        IDLToIRError: Se o IDL não contém informação suficiente para gerar IR
    """
    # Validar requisitos mínimos
    if not doc.entities:
        raise IDLToIRError(
            message="IDL must contain at least one entity to generate IR",
            error_code="IDL_TO_IR_INCOMPLETE",
        )

    # Converter entidades
    entities = [_convert_entity(e) for e in doc.entities]

    # Converter relações
    relations = _convert_relations(doc.entities)

    # Gerar operações API no formato IR schema
    # resources é uma lista de strings (nomes de entidades)
    # operations é uma lista de objetos com resource/method/path
    resource_names = [e.id.lower() for e in doc.entities]
    operations = []

    # Se tem usecases, derivar operações deles
    if doc.usecases:
        for usecase in doc.usecases:
            ops = _usecase_to_operations(usecase, doc.entities)
            for op in ops:
                operations.append({
                    "resource": op["entity"],
                    "method": op["verb"],
                    "path": op["path"],
                })

    # Garantir CRUD básico para todas as entidades
    existing_ops = {(o["resource"], o["method"], o["path"]) for o in operations}
    for entity in doc.entities:
        crud_ops = _generate_crud_for_entity(entity)
        for op in crud_ops:
            key = (op["entity"], op["verb"], op["path"])
            if key not in existing_ops:
                operations.append({
                    "resource": op["entity"],
                    "method": op["verb"],
                    "path": op["path"],
                })
                existing_ops.add(key)

    # Converter NFRs para formato IR schema (objeto, não array)
    nfr_obj = _convert_nfr_to_ir_format(doc.nonfunctional) if doc.nonfunctional else {}

    # Gerar UI pages (não routes)
    ui_pages = _generate_ui_pages(doc.entities)

    # Montar IR no formato esperado pelo schema
    ir = {
        "meta": {
            "project_name": project_title,
            "created_at": datetime.now().isoformat(),
            "version": "v1",
            "source": "idl",  # Indica que veio de IDL
        },
        "domain": {
            "entities": entities,
            "relations": relations,
            "workflows": [],  # IDL não tem workflows diretamente
            "rules": [],  # Regras podem vir de constraints, mas simplificamos
        },
        "api_intent": {
            "resources": resource_names,  # Lista de strings
            "operations": operations,  # Lista de objetos
        },
        "ui": {
            "pages": ui_pages,  # pages, não routes
        },
        "nfr": nfr_obj,  # Objeto, não array
    }

    # Adicionar roles se tiver actors
    if doc.actors:
        ir["roles"] = _convert_actors_to_roles(doc.actors)

    return ir
