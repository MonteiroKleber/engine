"""Backend Compiler - Gera código Java/Spring Boot a partir do IR + OAS + RBAC.

Gera:
- JPA Entity completa com validações
- Repository funcional com Spring Data
- Service com CRUD real e transações
- Controller com validação, DTO mapping e @PreAuthorize

Entrada:
- IR: Intermediate Representation com entidades e campos
- OAS: OpenAPI Specification com endpoints
- RBAC: Roles e permissões

Saída:
- Código Java pronto para compilar
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from config import get_config


@dataclass
class GeneratedFile:
    """Arquivo Java gerado."""

    path: str  # Caminho relativo ao projeto (ex: src/main/java/.../Entity.java)
    content: str
    file_type: str  # "entity", "dto", "repository", "service", "controller"

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "path": self.path,
            "content": self.content,
            "file_type": self.file_type,
        }


@dataclass
class BackendOutput:
    """Saída do BackendCompiler."""

    files: List[GeneratedFile] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)  # Nomes das entidades
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "files": [f.to_dict() for f in self.files],
            "entities": self.entities,
            "warnings": self.warnings,
            "file_count": len(self.files),
        }


class BackendCompiler:
    """Compila artefatos para código Java/Spring Boot.

    Gera código funcional que:
    - JPA Entity com @Entity, @Table, validações Bean Validation
    - Repository com JpaRepository e métodos custom
    - Service com @Service, @Transactional, CRUD completo
    - Controller com @RestController, @PreAuthorize, DTOs

    Attributes:
        base_package: Pacote base Java (ex: com.example.app)
        project_root: Caminho raiz do projeto
    """

    # Type mappings
    TYPE_MAP_JAVA = {
        "uuid": "UUID",
        "string": "String",
        "text": "String",
        "integer": "Integer",
        "long": "Long",
        "boolean": "Boolean",
        "date": "LocalDate",
        "datetime": "LocalDateTime",
        "decimal": "BigDecimal",
        "email": "String",
        "phone": "String",
        "url": "String",
    }

    # Validation annotations por tipo
    VALIDATION_ANNOTATIONS = {
        "email": "@Email",
        "url": "@URL",
    }

    def __init__(
        self,
        base_package: str = "com.example.app",
        project_root: Optional[str] = None,
    ) -> None:
        """Inicializa o BackendCompiler.

        Args:
            base_package: Pacote base Java
            project_root: Diretório raiz do projeto (from config if None)
        """
        self.base_package = base_package
        self.project_root = Path(project_root or get_config().generated_root)
        self._permission_map: Dict[str, str] = {}

    # ==================== UTILITIES ====================

    def _normalize_name(self, name: str) -> str:
        """Remove acentos e caracteres especiais."""
        normalized = unicodedata.normalize("NFD", name)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    def _to_snake_case(self, name: str) -> str:
        """Converte para snake_case."""
        name = self._normalize_name(name)
        result = []
        for i, c in enumerate(name):
            if c.isupper() and i > 0:
                result.append("_")
            result.append(c.lower())
        return "".join(result).replace(" ", "_").replace("-", "_")

    def _to_pascal_case(self, name: str) -> str:
        """Converte para PascalCase."""
        name = self._normalize_name(name)
        words = name.replace("_", " ").replace("-", " ").split()
        return "".join(word.capitalize() for word in words)

    def _to_camel_case(self, name: str) -> str:
        """Converte para camelCase."""
        pascal = self._to_pascal_case(name)
        return pascal[0].lower() + pascal[1:] if pascal else ""

    def _java_path(self, *parts: str) -> str:
        """Constrói caminho Java a partir do pacote."""
        package_path = self.base_package.replace(".", "/")
        return f"src/main/java/{package_path}/{'/'.join(parts)}"

    def _build_permission_map(self, rbac: Dict[str, Any]) -> None:
        """Constrói mapa de operationId -> required_role."""
        self._permission_map = {}
        for perm in rbac.get("permissions", []):
            op_id = perm.get("operation_id", "")
            role = perm.get("required_role", "authenticated")
            self._permission_map[op_id] = role

    def _get_role_for_operation(self, operation_id: str) -> str:
        """Retorna a role necessária para uma operação."""
        return self._permission_map.get(operation_id, "authenticated")

    # ==================== COMPILE ====================

    def compile(
        self,
        ir: Dict[str, Any],
        oas: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> BackendOutput:
        """Compila IR + OAS + RBAC para código Java.

        Args:
            ir: Intermediate Representation
            oas: OpenAPI Specification
            rbac: Role-Based Access Control

        Returns:
            BackendOutput com todos os arquivos gerados
        """
        output = BackendOutput()
        self._build_permission_map(rbac)

        entities = ir.get("domain", {}).get("entities", [])
        relations = ir.get("domain", {}).get("relations", [])

        # Extrair operações do OAS por entidade
        operations_map = self._extract_operations(oas)

        for entity in entities:
            entity_name = self._to_pascal_case(entity["name"])
            output.entities.append(entity_name)

            # Encontrar relações desta entidade
            entity_relations = self._find_relations(entity["name"], relations)

            # Gerar Entity
            entity_file = self._generate_entity(entity, entity_relations)
            output.files.append(entity_file)

            # Gerar DTOs (Request/Response)
            dto_files = self._generate_dtos(entity)
            output.files.extend(dto_files)

            # Gerar Repository
            repo_file = self._generate_repository(entity)
            output.files.append(repo_file)

            # Gerar Service
            service_file = self._generate_service(entity)
            output.files.append(service_file)

            # Gerar Controller com @PreAuthorize
            snake_name = self._to_snake_case(entity["name"])
            entity_ops = operations_map.get(snake_name, {})
            controller_file = self._generate_controller(entity, entity_ops)
            output.files.append(controller_file)

        # Gerar SecurityConfig atualizado
        security_file = self._generate_security_config(rbac)
        output.files.append(security_file)

        return output

    def _extract_operations(self, oas: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """Extrai operações do OAS organizadas por entidade.

        Returns:
            Dict[entity_name, Dict[method, operation_id]]
        """
        operations: Dict[str, Dict[str, str]] = {}

        for path, methods in oas.get("paths", {}).items():
            # /api/empresas -> empresas
            # /api/empresas/{id} -> empresas
            parts = path.strip("/").split("/")
            if len(parts) >= 2:
                entity_name = parts[1].rstrip("s")  # Remove plural 's'
            else:
                continue

            if entity_name not in operations:
                operations[entity_name] = {}

            for method, op_data in methods.items():
                if isinstance(op_data, dict) and method in ["get", "post", "put", "patch", "delete"]:
                    op_id = op_data.get("operationId", "")
                    # Determinar tipo de operação
                    if "{" in path:  # /api/empresas/{id}
                        if method == "get":
                            operations[entity_name]["getById"] = op_id
                        elif method == "put":
                            operations[entity_name]["update"] = op_id
                        elif method == "delete":
                            operations[entity_name]["delete"] = op_id
                    else:  # /api/empresas
                        if method == "get":
                            operations[entity_name]["list"] = op_id
                        elif method == "post":
                            operations[entity_name]["create"] = op_id

        return operations

    def _find_relations(
        self,
        entity_name: str,
        relations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Encontra relações onde esta entidade participa."""
        result = []
        snake_name = self._to_snake_case(entity_name)

        for rel in relations:
            from_entity = self._to_snake_case(rel.get("from", ""))
            to_entity = self._to_snake_case(rel.get("to", ""))

            if from_entity == snake_name or to_entity == snake_name:
                result.append(rel)

        return result

    # ==================== ENTITY GENERATION ====================

    def _generate_entity(
        self,
        entity: Dict[str, Any],
        relations: List[Dict[str, Any]],
    ) -> GeneratedFile:
        """Gera JPA Entity com validações completas."""
        name = self._to_pascal_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])
        fields = entity.get("fields", [])

        # Imports
        imports = self._collect_entity_imports(fields, relations)

        # Fields
        field_defs = []
        for fld in fields:
            field_def = self._generate_field(fld, entity.get("primary_key", "id"))
            field_defs.append(field_def)

        # Relation fields
        for rel in relations:
            rel_field = self._generate_relation_field(entity["name"], rel)
            if rel_field:
                field_defs.append(rel_field)

        fields_str = "\n\n".join(field_defs)
        imports_str = "\n".join(sorted(imports))

        content = f"""package {self.base_package}.domain;

{imports_str}

/**
 * Entidade JPA para {name}.
 * Gerado automaticamente pelo Bazari Engine.
 */
@Entity
@Table(name = "{snake_name}")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class {name} {{

{fields_str}

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {{
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }}

    @PreUpdate
    protected void onUpdate() {{
        updatedAt = LocalDateTime.now();
    }}
}}
"""

        return GeneratedFile(
            path=self._java_path("domain", f"{name}.java"),
            content=content,
            file_type="entity",
        )

    def _collect_entity_imports(
        self,
        fields: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
    ) -> Set[str]:
        """Coleta imports necessários para a Entity."""
        imports = {
            "import jakarta.persistence.*;",
            "import lombok.Data;",
            "import lombok.NoArgsConstructor;",
            "import lombok.AllArgsConstructor;",
            "import lombok.Builder;",
            "import java.time.LocalDateTime;",
        }

        for fld in fields:
            fld_type = fld.get("type", "string")
            if fld_type == "uuid":
                imports.add("import java.util.UUID;")
            elif fld_type == "date":
                imports.add("import java.time.LocalDate;")
            elif fld_type == "decimal":
                imports.add("import java.math.BigDecimal;")

            # Bean Validation
            if fld.get("required"):
                imports.add("import jakarta.validation.constraints.NotNull;")
            if fld_type == "email":
                imports.add("import jakarta.validation.constraints.Email;")
            if fld.get("min_length") or fld.get("max_length"):
                imports.add("import jakarta.validation.constraints.Size;")

        # Relations
        if relations:
            imports.add("import java.util.List;")
            imports.add("import java.util.ArrayList;")

        return imports

    def _generate_field(self, fld: Dict[str, Any], primary_key: str) -> str:
        """Gera definição de campo JPA."""
        field_name = self._to_camel_case(fld["name"])
        java_type = self.TYPE_MAP_JAVA.get(fld.get("type", "string"), "String")
        fld_type = fld.get("type", "string")

        annotations = []

        # Primary key
        if fld["name"] == primary_key:
            annotations.append("    @Id")
            if fld_type == "uuid":
                annotations.append("    @GeneratedValue(strategy = GenerationType.UUID)")
            else:
                annotations.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")

        # Column constraints
        column_attrs = []
        if fld.get("unique"):
            column_attrs.append("unique = true")
        if fld.get("required") and fld["name"] != primary_key:
            column_attrs.append("nullable = false")
        if fld.get("max_length"):
            column_attrs.append(f"length = {fld['max_length']}")

        if column_attrs:
            annotations.append(f"    @Column({', '.join(column_attrs)})")

        # Bean Validation
        if fld.get("required") and fld["name"] != primary_key:
            annotations.append("    @NotNull")
        if fld_type == "email":
            annotations.append("    @Email")
        if fld.get("min_length") and fld.get("max_length"):
            annotations.append(f"    @Size(min = {fld['min_length']}, max = {fld['max_length']})")
        elif fld.get("max_length"):
            annotations.append(f"    @Size(max = {fld['max_length']})")

        annotations_str = "\n".join(annotations)
        if annotations_str:
            return f"{annotations_str}\n    private {java_type} {field_name};"
        else:
            return f"    private {java_type} {field_name};"

    def _generate_relation_field(
        self,
        entity_name: str,
        relation: Dict[str, Any],
    ) -> Optional[str]:
        """Gera campo de relacionamento JPA."""
        from_entity = self._to_snake_case(relation.get("from", ""))
        to_entity = self._to_snake_case(relation.get("to", ""))
        rel_type = relation.get("type", "")
        snake_name = self._to_snake_case(entity_name)

        if rel_type == "many_to_one" and from_entity == snake_name:
            # Esta entidade tem ManyToOne para outra
            target = self._to_pascal_case(to_entity)
            field_name = self._to_camel_case(to_entity)
            return f"""    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "{to_entity}_id")
    private {target} {field_name};"""

        elif rel_type == "one_to_many" and from_entity == snake_name:
            # Esta entidade tem OneToMany
            target = self._to_pascal_case(to_entity)
            field_name = self._to_camel_case(to_entity) + "s"
            mapped_by = self._to_camel_case(from_entity)
            return f"""    @OneToMany(mappedBy = "{mapped_by}", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private List<{target}> {field_name} = new ArrayList<>();"""

        elif rel_type == "many_to_one" and to_entity == snake_name:
            # Outra entidade referencia esta - gerar OneToMany inverso
            target = self._to_pascal_case(from_entity)
            field_name = self._to_camel_case(from_entity) + "s"
            mapped_by = self._to_camel_case(snake_name)
            return f"""    @OneToMany(mappedBy = "{mapped_by}", cascade = CascadeType.ALL)
    @Builder.Default
    private List<{target}> {field_name} = new ArrayList<>();"""

        return None

    # ==================== DTO GENERATION ====================

    def _generate_dtos(self, entity: Dict[str, Any]) -> List[GeneratedFile]:
        """Gera DTOs de Request e Response."""
        name = self._to_pascal_case(entity["name"])
        fields = entity.get("fields", [])
        pk = entity.get("primary_key", "id")

        files = []

        # Request DTO (sem ID, para criação)
        request_dto = self._generate_request_dto(name, fields, pk)
        files.append(request_dto)

        # Response DTO (com ID e timestamps)
        response_dto = self._generate_response_dto(name, fields)
        files.append(response_dto)

        return files

    def _generate_request_dto(
        self,
        name: str,
        fields: List[Dict[str, Any]],
        pk: str,
    ) -> GeneratedFile:
        """Gera DTO de Request."""
        imports = {
            "import lombok.Data;",
            "import lombok.NoArgsConstructor;",
            "import lombok.AllArgsConstructor;",
        }

        field_defs = []
        for fld in fields:
            if fld["name"] == pk:
                continue  # Não incluir PK no request

            field_name = self._to_camel_case(fld["name"])
            java_type = self.TYPE_MAP_JAVA.get(fld.get("type", "string"), "String")
            fld_type = fld.get("type", "string")

            annotations = []
            if fld.get("required"):
                imports.add("import jakarta.validation.constraints.NotNull;")
                annotations.append("    @NotNull")
            if fld_type == "email":
                imports.add("import jakarta.validation.constraints.Email;")
                annotations.append("    @Email")
            if fld.get("max_length"):
                imports.add("import jakarta.validation.constraints.Size;")
                annotations.append(f"    @Size(max = {fld['max_length']})")

            if java_type == "UUID":
                imports.add("import java.util.UUID;")
            elif java_type == "LocalDate":
                imports.add("import java.time.LocalDate;")
            elif java_type == "LocalDateTime":
                imports.add("import java.time.LocalDateTime;")
            elif java_type == "BigDecimal":
                imports.add("import java.math.BigDecimal;")

            annotations_str = "\n".join(annotations)
            if annotations_str:
                field_defs.append(f"{annotations_str}\n    private {java_type} {field_name};")
            else:
                field_defs.append(f"    private {java_type} {field_name};")

        imports_str = "\n".join(sorted(imports))
        fields_str = "\n\n".join(field_defs)

        content = f"""package {self.base_package}.dto;

{imports_str}

/**
 * DTO de Request para {name}.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class {name}Request {{

{fields_str}
}}
"""

        return GeneratedFile(
            path=self._java_path("dto", f"{name}Request.java"),
            content=content,
            file_type="dto",
        )

    def _generate_response_dto(
        self,
        name: str,
        fields: List[Dict[str, Any]],
    ) -> GeneratedFile:
        """Gera DTO de Response."""
        imports = {
            "import lombok.Data;",
            "import lombok.NoArgsConstructor;",
            "import lombok.AllArgsConstructor;",
            "import lombok.Builder;",
            "import java.time.LocalDateTime;",
        }

        field_defs = []
        for fld in fields:
            field_name = self._to_camel_case(fld["name"])
            java_type = self.TYPE_MAP_JAVA.get(fld.get("type", "string"), "String")

            if java_type == "UUID":
                imports.add("import java.util.UUID;")
            elif java_type == "LocalDate":
                imports.add("import java.time.LocalDate;")
            elif java_type == "BigDecimal":
                imports.add("import java.math.BigDecimal;")

            field_defs.append(f"    private {java_type} {field_name};")

        # Add timestamps
        field_defs.append("    private LocalDateTime createdAt;")
        field_defs.append("    private LocalDateTime updatedAt;")

        imports_str = "\n".join(sorted(imports))
        fields_str = "\n".join(field_defs)

        content = f"""package {self.base_package}.dto;

{imports_str}

/**
 * DTO de Response para {name}.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class {name}Response {{

{fields_str}
}}
"""

        return GeneratedFile(
            path=self._java_path("dto", f"{name}Response.java"),
            content=content,
            file_type="dto",
        )

    # ==================== REPOSITORY GENERATION ====================

    def _generate_repository(self, entity: Dict[str, Any]) -> GeneratedFile:
        """Gera Spring Data Repository."""
        name = self._to_pascal_case(entity["name"])
        pk_type = "UUID"

        for fld in entity.get("fields", []):
            if fld["name"] == entity.get("primary_key", "id"):
                pk_type = self.TYPE_MAP_JAVA.get(fld.get("type", "uuid"), "UUID")
                break

        # Métodos custom baseados em campos únicos/indexados
        custom_methods = []
        for fld in entity.get("fields", []):
            if fld.get("unique") and fld["name"] != entity.get("primary_key", "id"):
                field_name = self._to_pascal_case(fld["name"])
                java_type = self.TYPE_MAP_JAVA.get(fld.get("type", "string"), "String")
                custom_methods.append(
                    f"    Optional<{name}> findBy{field_name}({java_type} {self._to_camel_case(fld['name'])});"
                )

        custom_methods_str = "\n\n".join(custom_methods) if custom_methods else ""

        content = f"""package {self.base_package}.repo;

import {self.base_package}.domain.{name};
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

/**
 * Repository para {name}.
 */
@Repository
public interface {name}Repository extends JpaRepository<{name}, {pk_type}> {{

{custom_methods_str}
}}
"""

        return GeneratedFile(
            path=self._java_path("repo", f"{name}Repository.java"),
            content=content,
            file_type="repository",
        )

    # ==================== SERVICE GENERATION ====================

    def _generate_service(self, entity: Dict[str, Any]) -> GeneratedFile:
        """Gera Service com CRUD completo."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        pk_type = "UUID"

        for fld in entity.get("fields", []):
            if fld["name"] == entity.get("primary_key", "id"):
                pk_type = self.TYPE_MAP_JAVA.get(fld.get("type", "uuid"), "UUID")
                break

        content = f"""package {self.base_package}.service;

import {self.base_package}.domain.{name};
import {self.base_package}.dto.{name}Request;
import {self.base_package}.dto.{name}Response;
import {self.base_package}.repo.{name}Repository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Service para {name} com CRUD completo.
 */
@Service
@RequiredArgsConstructor
@Transactional
public class {name}Service {{

    private final {name}Repository {var_name}Repository;

    /**
     * Lista todos os registros.
     */
    @Transactional(readOnly = true)
    public List<{name}Response> findAll() {{
        return {var_name}Repository.findAll().stream()
            .map(this::toResponse)
            .collect(Collectors.toList());
    }}

    /**
     * Busca por ID.
     */
    @Transactional(readOnly = true)
    public Optional<{name}Response> findById({pk_type} id) {{
        return {var_name}Repository.findById(id)
            .map(this::toResponse);
    }}

    /**
     * Cria novo registro.
     */
    public {name}Response create({name}Request request) {{
        {name} entity = toEntity(request);
        {name} saved = {var_name}Repository.save(entity);
        return toResponse(saved);
    }}

    /**
     * Atualiza registro existente.
     */
    public Optional<{name}Response> update({pk_type} id, {name}Request request) {{
        return {var_name}Repository.findById(id)
            .map(existing -> {{
                updateEntity(existing, request);
                {name} saved = {var_name}Repository.save(existing);
                return toResponse(saved);
            }});
    }}

    /**
     * Remove registro por ID.
     */
    public boolean deleteById({pk_type} id) {{
        if ({var_name}Repository.existsById(id)) {{
            {var_name}Repository.deleteById(id);
            return true;
        }}
        return false;
    }}

    /**
     * Verifica se existe por ID.
     */
    @Transactional(readOnly = true)
    public boolean existsById({pk_type} id) {{
        return {var_name}Repository.existsById(id);
    }}

    // ==================== MAPPING ====================

    private {name} toEntity({name}Request request) {{
        return {name}.builder()
{self._generate_request_to_entity_mappings(entity)}
            .build();
    }}

    private void updateEntity({name} entity, {name}Request request) {{
{self._generate_update_entity_mappings(entity)}
    }}

    private {name}Response toResponse({name} entity) {{
        return {name}Response.builder()
{self._generate_entity_to_response_mappings(entity)}
            .createdAt(entity.getCreatedAt())
            .updatedAt(entity.getUpdatedAt())
            .build();
    }}
}}
"""

        return GeneratedFile(
            path=self._java_path("service", f"{name}Service.java"),
            content=content,
            file_type="service",
        )

    def _generate_request_to_entity_mappings(self, entity: Dict[str, Any]) -> str:
        """Gera mapeamento de request para entity."""
        pk = entity.get("primary_key", "id")
        mappings = []
        for fld in entity.get("fields", []):
            if fld["name"] == pk:
                continue
            field_name = self._to_camel_case(fld["name"])
            getter = f"get{self._to_pascal_case(fld['name'])}()"
            mappings.append(f"            .{field_name}(request.{getter})")
        return "\n".join(mappings)

    def _generate_update_entity_mappings(self, entity: Dict[str, Any]) -> str:
        """Gera mapeamento de update."""
        pk = entity.get("primary_key", "id")
        mappings = []
        for fld in entity.get("fields", []):
            if fld["name"] == pk:
                continue
            setter = f"set{self._to_pascal_case(fld['name'])}"
            getter = f"get{self._to_pascal_case(fld['name'])}()"
            mappings.append(f"        entity.{setter}(request.{getter});")
        return "\n".join(mappings)

    def _generate_entity_to_response_mappings(self, entity: Dict[str, Any]) -> str:
        """Gera mapeamento de entity para response."""
        mappings = []
        for fld in entity.get("fields", []):
            field_name = self._to_camel_case(fld["name"])
            getter = f"get{self._to_pascal_case(fld['name'])}()"
            mappings.append(f"            .{field_name}(entity.{getter})")
        return "\n".join(mappings)

    # ==================== CONTROLLER GENERATION ====================

    def _generate_controller(
        self,
        entity: Dict[str, Any],
        operations: Dict[str, str],
    ) -> GeneratedFile:
        """Gera REST Controller com @PreAuthorize."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])
        path = f"/api/{snake_name}s"

        pk_type = "UUID"
        for fld in entity.get("fields", []):
            if fld["name"] == entity.get("primary_key", "id"):
                pk_type = self.TYPE_MAP_JAVA.get(fld.get("type", "uuid"), "UUID")
                break

        # Gerar @PreAuthorize para cada operação
        list_role = self._get_role_for_operation(operations.get("list", ""))
        create_role = self._get_role_for_operation(operations.get("create", ""))
        get_role = self._get_role_for_operation(operations.get("getById", ""))
        update_role = self._get_role_for_operation(operations.get("update", ""))
        delete_role = self._get_role_for_operation(operations.get("delete", ""))

        content = f"""package {self.base_package}.api;

import {self.base_package}.dto.{name}Request;
import {self.base_package}.dto.{name}Response;
import {self.base_package}.service.{name}Service;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * REST Controller para {name}.
 * Endpoints protegidos com @PreAuthorize.
 */
@RestController
@RequestMapping("{path}")
@RequiredArgsConstructor
public class {name}Controller {{

    private final {name}Service {var_name}Service;

    /**
     * Lista todos os registros.
     */
    @GetMapping
    @PreAuthorize("hasRole('{list_role.upper()}')")
    public ResponseEntity<List<{name}Response>> list{name}() {{
        List<{name}Response> result = {var_name}Service.findAll();
        return ResponseEntity.ok(result);
    }}

    /**
     * Cria novo registro.
     */
    @PostMapping
    @PreAuthorize("hasRole('{create_role.upper()}')")
    public ResponseEntity<{name}Response> create{name}(@Valid @RequestBody {name}Request request) {{
        {name}Response created = {var_name}Service.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }}

    /**
     * Busca por ID.
     */
    @GetMapping("/{{id}}")
    @PreAuthorize("hasRole('{get_role.upper()}')")
    public ResponseEntity<{name}Response> get{name}(@PathVariable {pk_type} id) {{
        return {var_name}Service.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }}

    /**
     * Atualiza registro existente.
     */
    @PutMapping("/{{id}}")
    @PreAuthorize("hasRole('{update_role.upper()}')")
    public ResponseEntity<{name}Response> update{name}(
            @PathVariable {pk_type} id,
            @Valid @RequestBody {name}Request request) {{
        return {var_name}Service.update(id, request)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }}

    /**
     * Remove registro por ID.
     */
    @DeleteMapping("/{{id}}")
    @PreAuthorize("hasRole('{delete_role.upper()}')")
    public ResponseEntity<Void> delete{name}(@PathVariable {pk_type} id) {{
        if ({var_name}Service.deleteById(id)) {{
            return ResponseEntity.ok().build();
        }}
        return ResponseEntity.notFound().build();
    }}
}}
"""

        return GeneratedFile(
            path=self._java_path("api", f"{name}Controller.java"),
            content=content,
            file_type="controller",
        )

    # ==================== SECURITY CONFIG ====================

    def _generate_security_config(self, rbac: Dict[str, Any]) -> GeneratedFile:
        """Gera SecurityConfig com method security."""
        roles = rbac.get("roles", ["authenticated"])
        roles_str = ", ".join([f'"{r}"' for r in roles])

        content = f"""package {self.base_package}.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Configuração de segurança Spring Security.
 * Method security habilitado para @PreAuthorize.
 *
 * Roles disponíveis: {roles_str}
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true)
public class SecurityConfig {{

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {{
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .requestMatchers("/actuator/**").permitAll()
                .anyRequest().authenticated()
            );

        return http.build();
    }}
}}
"""

        return GeneratedFile(
            path=self._java_path("security", "SecurityConfig.java"),
            content=content,
            file_type="config",
        )


def compile_backend(
    ir: Dict[str, Any],
    oas: Dict[str, Any],
    rbac: Dict[str, Any],
    base_package: str = "com.example.app",
    project_root: Optional[str] = None,
) -> BackendOutput:
    """Função de conveniência para compilar backend.

    Args:
        ir: Intermediate Representation
        oas: OpenAPI Specification
        rbac: Role-Based Access Control
        base_package: Pacote base Java
        project_root: Diretório raiz do projeto (from config if None)

    Returns:
        BackendOutput com todos os arquivos gerados
    """
    compiler = BackendCompiler(base_package, project_root)
    return compiler.compile(ir, oas, rbac)
