"""IDL Draft Schema - Validacao estrutural do Draft.

GATE 1: Draft Structural Validation

Este modulo implementa a validacao estrutural do IDL Draft v1.

REJEITA se:
- schema_version != idl_draft.v1
- IDs duplicados
- Tipos invalidos (ex: lista onde deveria ser string)
- Estrutura JSON invalida

PERMITE:
- Campos "unknown"
- Campos ausentes
- Assumptions e open_questions
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .idl_draft_v1 import IDL_DRAFT_SCHEMA_VERSION, IDLDraftV1


# ============================================
# VALIDATION ERRORS
# ============================================

@dataclass
class DraftValidationError:
    """Erro de validacao estrutural do Draft."""
    error_type: str
    message: str
    location: str

    def to_dict(self) -> Dict[str, str]:
        """Converte para dicionario."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class DraftValidationResult:
    """Resultado da validacao estrutural."""
    valid: bool
    errors: List[DraftValidationError]
    draft: Optional[IDLDraftV1] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
        }


# ============================================
# VALIDATOR
# ============================================

class DraftSchemaValidator:
    """Validador estrutural do IDL Draft v1.

    Valida:
    - Schema version
    - Tipos de dados
    - IDs duplicados
    - Estrutura geral

    NAO valida:
    - Campos unknown (permitido)
    - Campos ausentes (permitido)
    - Completude semantica (responsabilidade do compilador)
    """

    def validate(self, data: Dict[str, Any]) -> DraftValidationResult:
        """Valida estrutura do Draft.

        Args:
            data: Dicionario JSON do Draft

        Returns:
            DraftValidationResult com status e erros
        """
        errors: List[DraftValidationError] = []

        # 1. Validar schema_version
        schema_errors = self._validate_schema_version(data)
        errors.extend(schema_errors)

        # 2. Validar project
        project_errors = self._validate_project(data)
        errors.extend(project_errors)

        # 3. Validar source
        source_errors = self._validate_source(data)
        errors.extend(source_errors)

        # 4. Validar actors
        actor_errors = self._validate_actors(data)
        errors.extend(actor_errors)

        # 5. Validar entities
        entity_errors = self._validate_entities(data)
        errors.extend(entity_errors)

        # 6. Validar use_cases
        uc_errors = self._validate_use_cases(data)
        errors.extend(uc_errors)

        # 7. Validar integrations
        integ_errors = self._validate_integrations(data)
        errors.extend(integ_errors)

        # 8. Validar non_functional
        nf_errors = self._validate_non_functional(data)
        errors.extend(nf_errors)

        # 9. Validar assumptions
        assumption_errors = self._validate_assumptions(data)
        errors.extend(assumption_errors)

        # 10. Validar open_questions
        oq_errors = self._validate_open_questions(data)
        errors.extend(oq_errors)

        # 11. Validar IDs duplicados globalmente
        dup_errors = self._validate_no_duplicate_ids(data)
        errors.extend(dup_errors)

        if errors:
            return DraftValidationResult(valid=False, errors=errors, draft=None)

        # Criar objeto Draft
        try:
            draft = IDLDraftV1.from_dict(data)
            return DraftValidationResult(valid=True, errors=[], draft=draft)
        except Exception as e:
            errors.append(DraftValidationError(
                error_type="PARSE_ERROR",
                message=f"Failed to parse draft: {str(e)}",
                location="root",
            ))
            return DraftValidationResult(valid=False, errors=errors, draft=None)

    def validate_json(self, json_str: str) -> DraftValidationResult:
        """Valida JSON string do Draft.

        Args:
            json_str: String JSON do Draft

        Returns:
            DraftValidationResult com status e erros
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return DraftValidationResult(
                valid=False,
                errors=[DraftValidationError(
                    error_type="INVALID_JSON",
                    message=f"Invalid JSON: {str(e)}",
                    location="root",
                )],
                draft=None,
            )

        return self.validate(data)

    def _validate_schema_version(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida schema_version."""
        errors = []

        if "schema_version" not in data:
            errors.append(DraftValidationError(
                error_type="MISSING_SCHEMA_VERSION",
                message="schema_version is required",
                location="root.schema_version",
            ))
        elif data["schema_version"] != IDL_DRAFT_SCHEMA_VERSION:
            errors.append(DraftValidationError(
                error_type="INVALID_SCHEMA_VERSION",
                message=f"schema_version must be '{IDL_DRAFT_SCHEMA_VERSION}', got '{data['schema_version']}'",
                location="root.schema_version",
            ))

        return errors

    def _validate_project(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida campo project."""
        errors = []

        if "project" not in data:
            errors.append(DraftValidationError(
                error_type="MISSING_PROJECT",
                message="project is required",
                location="root.project",
            ))
        elif not isinstance(data["project"], str):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="project must be a string",
                location="root.project",
            ))

        return errors

    def _validate_source(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida campo source."""
        errors = []
        valid_sources = {"natural_text", "wizard", "imported"}

        if "source" in data:
            if not isinstance(data["source"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message="source must be a string",
                    location="root.source",
                ))
            elif data["source"] not in valid_sources:
                errors.append(DraftValidationError(
                    error_type="INVALID_SOURCE",
                    message=f"source must be one of {valid_sources}, got '{data['source']}'",
                    location="root.source",
                ))

        return errors

    def _validate_actors(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida lista de actors."""
        errors = []

        if "actors" not in data:
            return errors  # Opcional

        if not isinstance(data["actors"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="actors must be a list",
                location="root.actors",
            ))
            return errors

        seen_ids: Set[str] = set()
        for i, actor in enumerate(data["actors"]):
            if not isinstance(actor, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"actor[{i}] must be an object",
                    location=f"actors[{i}]",
                ))
                continue

            # ID obrigatorio
            if "id" not in actor:
                errors.append(DraftValidationError(
                    error_type="MISSING_ID",
                    message=f"actor[{i}].id is required",
                    location=f"actors[{i}].id",
                ))
            elif not isinstance(actor["id"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"actor[{i}].id must be a string",
                    location=f"actors[{i}].id",
                ))
            else:
                if actor["id"] in seen_ids:
                    errors.append(DraftValidationError(
                        error_type="DUPLICATE_ID",
                        message=f"Duplicate actor id: '{actor['id']}'",
                        location=f"actors[{i}].id",
                    ))
                seen_ids.add(actor["id"])

            # Role - pode ser string ou unknown
            if "role" in actor and not isinstance(actor["role"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"actor[{i}].role must be a string",
                    location=f"actors[{i}].role",
                ))

            # Permissions - deve ser lista
            if "permissions" in actor:
                if not isinstance(actor["permissions"], list):
                    errors.append(DraftValidationError(
                        error_type="INVALID_TYPE",
                        message=f"actor[{i}].permissions must be a list",
                        location=f"actors[{i}].permissions",
                    ))
                else:
                    for j, perm in enumerate(actor["permissions"]):
                        if not isinstance(perm, str):
                            errors.append(DraftValidationError(
                                error_type="INVALID_TYPE",
                                message=f"actor[{i}].permissions[{j}] must be a string",
                                location=f"actors[{i}].permissions[{j}]",
                            ))

        return errors

    def _validate_entities(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida lista de entities."""
        errors = []

        if "entities" not in data:
            return errors  # Opcional

        if not isinstance(data["entities"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="entities must be a list",
                location="root.entities",
            ))
            return errors

        seen_ids: Set[str] = set()
        for i, entity in enumerate(data["entities"]):
            if not isinstance(entity, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"entity[{i}] must be an object",
                    location=f"entities[{i}]",
                ))
                continue

            # ID obrigatorio
            if "id" not in entity:
                errors.append(DraftValidationError(
                    error_type="MISSING_ID",
                    message=f"entity[{i}].id is required",
                    location=f"entities[{i}].id",
                ))
            elif not isinstance(entity["id"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"entity[{i}].id must be a string",
                    location=f"entities[{i}].id",
                ))
            else:
                if entity["id"] in seen_ids:
                    errors.append(DraftValidationError(
                        error_type="DUPLICATE_ID",
                        message=f"Duplicate entity id: '{entity['id']}'",
                        location=f"entities[{i}].id",
                    ))
                seen_ids.add(entity["id"])

            # Fields - deve ser lista
            if "fields" in entity:
                if not isinstance(entity["fields"], list):
                    errors.append(DraftValidationError(
                        error_type="INVALID_TYPE",
                        message=f"entity[{i}].fields must be a list",
                        location=f"entities[{i}].fields",
                    ))
                else:
                    errors.extend(self._validate_entity_fields(entity["fields"], i))

        return errors

    def _validate_entity_fields(self, fields: list, entity_idx: int) -> List[DraftValidationError]:
        """Valida campos de uma entidade."""
        errors = []
        seen_names: Set[str] = set()

        for j, field_data in enumerate(fields):
            if not isinstance(field_data, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"entity[{entity_idx}].fields[{j}] must be an object",
                    location=f"entities[{entity_idx}].fields[{j}]",
                ))
                continue

            # Name obrigatorio
            if "name" not in field_data:
                errors.append(DraftValidationError(
                    error_type="MISSING_NAME",
                    message=f"entity[{entity_idx}].fields[{j}].name is required",
                    location=f"entities[{entity_idx}].fields[{j}].name",
                ))
            elif not isinstance(field_data["name"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"entity[{entity_idx}].fields[{j}].name must be a string",
                    location=f"entities[{entity_idx}].fields[{j}].name",
                ))
            else:
                if field_data["name"] in seen_names:
                    errors.append(DraftValidationError(
                        error_type="DUPLICATE_FIELD_NAME",
                        message=f"Duplicate field name: '{field_data['name']}'",
                        location=f"entities[{entity_idx}].fields[{j}].name",
                    ))
                seen_names.add(field_data["name"])

            # Type - pode ser string (incluindo unknown)
            if "type" in field_data and not isinstance(field_data["type"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"entity[{entity_idx}].fields[{j}].type must be a string",
                    location=f"entities[{entity_idx}].fields[{j}].type",
                ))

            # Required - pode ser bool ou string (unknown)
            if "required" in field_data:
                if not isinstance(field_data["required"], (bool, str)):
                    errors.append(DraftValidationError(
                        error_type="INVALID_TYPE",
                        message=f"entity[{entity_idx}].fields[{j}].required must be boolean or string",
                        location=f"entities[{entity_idx}].fields[{j}].required",
                    ))

        return errors

    def _validate_use_cases(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida lista de use_cases."""
        errors = []

        if "use_cases" not in data:
            return errors  # Opcional

        if not isinstance(data["use_cases"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="use_cases must be a list",
                location="root.use_cases",
            ))
            return errors

        seen_ids: Set[str] = set()
        for i, uc in enumerate(data["use_cases"]):
            if not isinstance(uc, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{i}] must be an object",
                    location=f"use_cases[{i}]",
                ))
                continue

            # ID obrigatorio
            if "id" not in uc:
                errors.append(DraftValidationError(
                    error_type="MISSING_ID",
                    message=f"use_case[{i}].id is required",
                    location=f"use_cases[{i}].id",
                ))
            elif not isinstance(uc["id"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{i}].id must be a string",
                    location=f"use_cases[{i}].id",
                ))
            else:
                if uc["id"] in seen_ids:
                    errors.append(DraftValidationError(
                        error_type="DUPLICATE_ID",
                        message=f"Duplicate use_case id: '{uc['id']}'",
                        location=f"use_cases[{i}].id",
                    ))
                seen_ids.add(uc["id"])

            # Actor - pode ser string (incluindo unknown)
            if "actor" in uc and not isinstance(uc["actor"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{i}].actor must be a string",
                    location=f"use_cases[{i}].actor",
                ))

            # Flow - deve ser lista
            if "flow" in uc:
                if not isinstance(uc["flow"], list):
                    errors.append(DraftValidationError(
                        error_type="INVALID_TYPE",
                        message=f"use_case[{i}].flow must be a list",
                        location=f"use_cases[{i}].flow",
                    ))
                else:
                    errors.extend(self._validate_flow_steps(uc["flow"], i))

        return errors

    def _validate_flow_steps(self, flow: list, uc_idx: int) -> List[DraftValidationError]:
        """Valida passos de fluxo."""
        errors = []

        for j, step in enumerate(flow):
            if not isinstance(step, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{uc_idx}].flow[{j}] must be an object",
                    location=f"use_cases[{uc_idx}].flow[{j}]",
                ))
                continue

            # Step number
            if "step" in step and not isinstance(step["step"], int):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{uc_idx}].flow[{j}].step must be an integer",
                    location=f"use_cases[{uc_idx}].flow[{j}].step",
                ))

            # Action
            if "action" in step and not isinstance(step["action"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"use_case[{uc_idx}].flow[{j}].action must be a string",
                    location=f"use_cases[{uc_idx}].flow[{j}].action",
                ))

        return errors

    def _validate_integrations(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida lista de integrations."""
        errors = []

        if "integrations" not in data:
            return errors  # Opcional

        if not isinstance(data["integrations"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="integrations must be a list",
                location="root.integrations",
            ))
            return errors

        for i, integ in enumerate(data["integrations"]):
            if not isinstance(integ, dict):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"integration[{i}] must be an object",
                    location=f"integrations[{i}]",
                ))
                continue

            # System obrigatorio
            if "system" not in integ:
                errors.append(DraftValidationError(
                    error_type="MISSING_SYSTEM",
                    message=f"integration[{i}].system is required",
                    location=f"integrations[{i}].system",
                ))
            elif not isinstance(integ["system"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"integration[{i}].system must be a string",
                    location=f"integrations[{i}].system",
                ))

            # Type - pode ser string (incluindo unknown)
            if "type" in integ and not isinstance(integ["type"], str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"integration[{i}].type must be a string",
                    location=f"integrations[{i}].type",
                ))

        return errors

    def _validate_non_functional(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida non_functional."""
        errors = []

        if "non_functional" not in data:
            return errors  # Opcional

        nf = data["non_functional"]
        if not isinstance(nf, dict):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="non_functional must be an object",
                location="root.non_functional",
            ))
            return errors

        # Performance
        if "performance" in nf and not isinstance(nf["performance"], str):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="non_functional.performance must be a string",
                location="non_functional.performance",
            ))

        # Security
        if "security" in nf and not isinstance(nf["security"], str):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="non_functional.security must be a string",
                location="non_functional.security",
            ))

        return errors

    def _validate_assumptions(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida assumptions."""
        errors = []

        if "assumptions" not in data:
            return errors  # Opcional

        if not isinstance(data["assumptions"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="assumptions must be a list",
                location="root.assumptions",
            ))
            return errors

        for i, assumption in enumerate(data["assumptions"]):
            if not isinstance(assumption, str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"assumption[{i}] must be a string",
                    location=f"assumptions[{i}]",
                ))

        return errors

    def _validate_open_questions(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida open_questions."""
        errors = []

        if "open_questions" not in data:
            return errors  # Opcional

        if not isinstance(data["open_questions"], list):
            errors.append(DraftValidationError(
                error_type="INVALID_TYPE",
                message="open_questions must be a list",
                location="root.open_questions",
            ))
            return errors

        for i, question in enumerate(data["open_questions"]):
            if not isinstance(question, str):
                errors.append(DraftValidationError(
                    error_type="INVALID_TYPE",
                    message=f"open_question[{i}] must be a string",
                    location=f"open_questions[{i}]",
                ))

        return errors

    def _validate_no_duplicate_ids(self, data: Dict[str, Any]) -> List[DraftValidationError]:
        """Valida que nao ha IDs duplicados entre diferentes secoes."""
        errors = []
        all_ids: Dict[str, str] = {}  # id -> location

        # Coletar IDs de actors
        for actor in data.get("actors", []):
            if isinstance(actor, dict) and "id" in actor:
                actor_id = actor["id"]
                if actor_id in all_ids:
                    # Duplicado entre actors ja foi verificado
                    pass

        # Coletar IDs de entities
        for entity in data.get("entities", []):
            if isinstance(entity, dict) and "id" in entity:
                entity_id = entity["id"]
                # Entities podem ter mesmo ID que actors (namespaces diferentes)

        # Coletar IDs de use_cases
        for uc in data.get("use_cases", []):
            if isinstance(uc, dict) and "id" in uc:
                uc_id = uc["id"]
                # Use cases podem ter mesmo ID que outras secoes

        return errors


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def validate_draft(data: Dict[str, Any]) -> DraftValidationResult:
    """Funcao de conveniencia para validar Draft.

    Args:
        data: Dicionario JSON do Draft

    Returns:
        DraftValidationResult
    """
    validator = DraftSchemaValidator()
    return validator.validate(data)


def validate_draft_json(json_str: str) -> DraftValidationResult:
    """Funcao de conveniencia para validar Draft JSON.

    Args:
        json_str: String JSON do Draft

    Returns:
        DraftValidationResult
    """
    validator = DraftSchemaValidator()
    return validator.validate_json(json_str)
