"""Domain Modeler Agent - Transforma SRS → IR (determinístico v1)."""

from datetime import datetime
from typing import Any, Dict, List, Optional


class DomainModeler:
    """Transforma SRS em IR de forma determinística (v1, sem LLM).

    Regras:
    - Não infere entidades não citadas no SRS
    - Se SRS não tem data_requirements, gera IR inválido para bloquear pipeline
    """

    def generate_ir(self, srs: Dict[str, Any]) -> Dict[str, Any]:
        """Gera IR a partir do SRS.

        Args:
            srs: Documento SRS

        Returns:
            Documento IR (pode ser inválido se SRS não tiver entidades)
        """
        # Extrair data_requirements do SRS
        data_requirements = srs.get("data_requirements", [])

        # Se não há entidades, gerar IR propositalmente inválido
        # (entities vazio falha validação por minItems: 1)
        if not data_requirements:
            return self._generate_invalid_ir(srs)

        # Gerar IR válido
        return self._generate_valid_ir(srs, data_requirements)

    def _generate_invalid_ir(self, srs: Dict[str, Any]) -> Dict[str, Any]:
        """Gera IR inválido para bloquear pipeline quando SRS não tem entidades."""
        project_name = self._extract_project_name(srs)

        return {
            "meta": {
                "project_name": project_name,
                "created_at": datetime.now().isoformat(),
            },
            "domain": {
                "entities": [],  # Vazio = falha validação (minItems: 1)
                "relations": [],
                "workflows": [],
                "rules": [],
            },
            "api_intent": {
                "resources": [],
            },
            "ui": {
                "pages": [],
            },
            "nfr": self._extract_nfr(srs),
        }

    def _generate_valid_ir(
        self,
        srs: Dict[str, Any],
        data_requirements: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Gera IR válido a partir do SRS com entidades."""
        project_name = self._extract_project_name(srs)

        # Gerar entidades
        entities = self._generate_entities(data_requirements)
        entity_names = [e["name"] for e in entities]

        # Gerar regras de negócio
        rules = self._generate_rules(srs.get("business_rules", []))

        # Gerar páginas UI
        pages = self._generate_ui_pages(entity_names)

        return {
            "meta": {
                "project_name": project_name,
                "created_at": datetime.now().isoformat(),
                # version NÃO é definido aqui - engine define via next_version
            },
            "domain": {
                "entities": entities,
                "relations": [],  # Vazio por padrão v1
                "workflows": [],  # Vazio por padrão v1
                "rules": rules,
            },
            "api_intent": {
                "resources": entity_names,
            },
            "ui": {
                "pages": pages,
            },
            "nfr": self._extract_nfr(srs),
        }

    def _extract_project_name(self, srs: Dict[str, Any]) -> str:
        """Extrai nome do projeto do SRS."""
        # Tentar meta.project_name primeiro
        meta = srs.get("meta", srs.get("metadata", {}))
        if isinstance(meta, dict) and "project_name" in meta:
            return meta["project_name"]

        # Fallback para title
        return srs.get("title", "Projeto")

    def _generate_entities(
        self, data_requirements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Gera entidades a partir de data_requirements."""
        entities = []

        for req in data_requirements:
            entity_name = req.get("entity", req.get("name", ""))
            if not entity_name:
                continue

            # Gerar campos
            fields = self._generate_fields(req.get("fields", []))

            # Verificar se tem primary_key definido
            primary_key = req.get("primary_key", "id")

            # Adicionar campo id se não existir
            has_id = any(f["name"] == primary_key for f in fields)
            if not has_id:
                fields.insert(0, {
                    "name": primary_key,
                    "type": "uuid",
                    "required": True,
                    "unique": True,
                    "indexed": True,
                })

            entities.append({
                "name": entity_name.lower(),
                "primary_key": primary_key,
                "fields": fields,
            })

        return entities

    def _generate_fields(
        self, field_specs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Gera campos para uma entidade."""
        fields = []

        for spec in field_specs:
            field_name = spec.get("name", spec.get("field", ""))
            if not field_name:
                continue

            fields.append({
                "name": field_name,
                "type": spec.get("type", "string"),
                "required": spec.get("required", False),
                "unique": spec.get("unique", False),  # Default false
                "indexed": spec.get("indexed", False),  # Default false
            })

        return fields

    def _generate_rules(
        self, business_rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Converte business_rules do SRS em rules do IR."""
        rules = []

        for i, rule in enumerate(business_rules):
            rule_id = rule.get("id", f"BR-{i+1:03d}")
            description = rule.get("description", rule.get("rule", str(rule)))

            rules.append({
                "id": rule_id,
                "description": description,
                "severity": "ERROR",  # Default ERROR por especificação
            })

        return rules

    def _generate_ui_pages(self, entity_names: List[str]) -> List[Dict[str, Any]]:
        """Gera páginas CRUD mínimas por entidade."""
        pages = []

        for entity in entity_names:
            # Página de listagem
            pages.append({
                "path": f"/app/{entity}/list",
                "title": f"Listar {entity.title()}",
                "components": ["table", "pagination", "search"],
                "actions": ["list", "view", "delete"],
            })

            # Página de criação
            pages.append({
                "path": f"/app/{entity}/new",
                "title": f"Novo {entity.title()}",
                "components": ["form"],
                "actions": ["create"],
            })

            # Página de detalhes/edição
            pages.append({
                "path": f"/app/{entity}/:id",
                "title": f"Detalhes {entity.title()}",
                "components": ["form"],
                "actions": ["view", "update", "delete"],
            })

        return pages

    def _extract_nfr(self, srs: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai Non-Functional Requirements do SRS."""
        nfr = srs.get("non_functional_requirements", {})
        security = nfr.get("security", {})

        return {
            "security": {
                "auth_required": security.get("auth_required", True),
                "audit_log_required": security.get("audit_log_required", False),
            },
        }
