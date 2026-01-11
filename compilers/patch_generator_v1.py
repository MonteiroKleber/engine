"""Patch Generator v1 - Gera patches determinísticos a partir dos artefatos.

Entrada:
- PLAN: Plano de execução com tasks ordenadas
- IR: Intermediate Representation com entidades e campos
- OAS: OpenAPI Specification com endpoints
- RBAC: Roles e permissões

Saída:
- Lista de patches apontando para <generated_root>/<project>/...

Regras:
- Mesma entrada → mesmos patches (determinístico)
- Nenhum patch fora de generated/
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from config import get_config


# ==================== SLOT SYSTEM ====================

def get_template_root() -> Path:
    """Get template root from config."""
    return Path(get_config().templates_root) / "react-vite"

# Definição dos slots suportados
# JSX comment syntax para arquivos .tsx dentro de JSX
# JS comment syntax para arquivos .tsx fora de JSX (como imports)
SLOT_MARKERS = {
    "nav": ("{/* @engine:nav:start */}", "{/* @engine:nav:end */}"),
    "routes": ("{/* @engine:routes:start */}", "{/* @engine:routes:end */}"),
    "entities": ("{/* @engine:entities:start */}", "{/* @engine:entities:end */}"),
    "imports": ("// @engine:imports:start", "// @engine:imports:end"),
    "routes-array": ("// @engine:routes-array:start", "// @engine:routes-array:end"),
}


def replace_slot(content: str, slot_name: str, new_block: str, file_path: str = "") -> str:
    """Substitui o conteúdo entre marcadores de slot.

    Args:
        content: Conteúdo original do arquivo
        slot_name: Nome do slot (ex: "nav", "routes", "entities", "imports", "routes-array")
        new_block: Novo conteúdo a inserir entre os marcadores
        file_path: Caminho do arquivo (para mensagem de erro)

    Returns:
        Conteúdo com o slot substituído

    Raises:
        ValueError: Se o slot não for encontrado no conteúdo
    """
    if slot_name not in SLOT_MARKERS:
        raise ValueError(f"Slot desconhecido: '{slot_name}'. Slots válidos: {list(SLOT_MARKERS.keys())}")

    start_marker, end_marker = SLOT_MARKERS[slot_name]

    # Verificar se os marcadores existem
    if start_marker not in content:
        raise ValueError(
            f"Slot '{slot_name}' não encontrado em {file_path or 'arquivo'}: "
            f"marcador '{start_marker}' ausente"
        )
    if end_marker not in content:
        raise ValueError(
            f"Slot '{slot_name}' não encontrado em {file_path or 'arquivo'}: "
            f"marcador '{end_marker}' ausente"
        )

    # Escapar caracteres especiais no padrão regex
    start_escaped = re.escape(start_marker)
    end_escaped = re.escape(end_marker)

    # Padrão para capturar:
    # - linha do marcador start (com indentação original)
    # - conteúdo entre os marcadores (qualquer coisa)
    # - linha do marcador end (com indentação original)
    pattern = (
        rf"(^[ \t]*{start_escaped}[ \t]*\r?\n)"
        rf"(.*?)"
        rf"(^[ \t]*{end_escaped}[ \t]*\r?$)"
    )

    # Construir novo bloco preservando as linhas dos marcadores exatamente
    # como estão no arquivo (sem alterar indentação fora do slot).
    insertion = ""
    if new_block.strip():
        insertion = new_block.rstrip("\n") + "\n"

    def _replacer(match: "re.Match[str]") -> str:
        return match.group(1) + insertion + match.group(3)

    result, count = re.subn(pattern, _replacer, content, flags=re.DOTALL | re.MULTILINE, count=1)

    if count == 0:
        raise ValueError(
            f"Falha ao substituir slot '{slot_name}' em {file_path or 'arquivo'}: "
            f"padrão não correspondeu"
        )

    return result


def read_template(relative_path: str) -> str:
    """Lê conteúdo de um template.

    Args:
        relative_path: Caminho relativo ao template root (ex: "src/App.tsx")

    Returns:
        Conteúdo do template

    Raises:
        FileNotFoundError: Se o template não existir
    """
    template_path = get_template_root() / relative_path
    if not template_path.exists():
        raise FileNotFoundError(f"Template não encontrado: {template_path}")
    return template_path.read_text(encoding="utf-8")


@dataclass
class Patch:
    """Um patch de código a ser aplicado."""

    file_path: str  # Caminho relativo ao projeto
    operation: str  # "create", "modify", "append"
    content: str
    task_id: str  # ID da task que gerou este patch
    order: int  # Ordem de aplicação

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "file_path": self.file_path,
            "operation": self.operation,
            "content": self.content,
            "task_id": self.task_id,
            "order": self.order,
        }


@dataclass
class PatchSet:
    """Conjunto de patches gerados."""

    project: str
    patches: List[Patch] = field(default_factory=list)
    generated_at: str = ""
    input_hash: str = ""  # Hash dos inputs para determinismo

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "project": self.project,
            "patches": [p.to_dict() for p in self.patches],
            "generated_at": self.generated_at,
            "input_hash": self.input_hash,
            "patch_count": len(self.patches),
        }

    def get_absolute_paths(self, generated_root: Optional[str] = None) -> List[str]:
        """Retorna paths absolutos dos patches."""
        root = generated_root or get_config().generated_root
        return [f"{root}/{self.project}/{p.file_path}" for p in self.patches]


class PatchGenerator:
    """Gera patches determinísticos a partir dos artefatos do pipeline.

    A geração é determinística: mesma entrada sempre produz mesma saída.
    Todos os patches apontam apenas para <generated_root>/<project>/.

    Attributes:
        project: Nome do projeto
        generated_root: Diretório raiz para projetos gerados
    """

    @property
    def GENERATED_ROOT(self) -> str:
        """Get generated root from config or instance."""
        return self._generated_root

    # Type mappings para SQL e Java
    TYPE_MAP_SQL = {
        "uuid": "UUID",
        "string": "VARCHAR(255)",
        "text": "TEXT",
        "integer": "INTEGER",
        "long": "BIGINT",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "datetime": "TIMESTAMP",
        "decimal": "DECIMAL(19,4)",
    }

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
    }

    TYPE_MAP_TS = {
        "uuid": "string",
        "string": "string",
        "text": "string",
        "integer": "number",
        "long": "number",
        "boolean": "boolean",
        "date": "string",
        "datetime": "string",
        "decimal": "number",
    }

    def __init__(
        self,
        project: str,
        generated_root: Optional[str] = None,
    ) -> None:
        """Inicializa o PatchGenerator.

        Args:
            project: Nome do projeto
            generated_root: Diretório raiz para projetos gerados (from config if None)
        """
        self.project = project
        self._generated_root = generated_root or get_config().generated_root
        self.generated_root = Path(self._generated_root)
        self._order_counter = 0

    def _normalize_name(self, name: str) -> str:
        """Remove acentos e caracteres especiais."""
        normalized = unicodedata.normalize("NFD", name)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    def _to_snake_case(self, name: str) -> str:
        """Converte para snake_case (ASCII only)."""
        name = self._normalize_name(name)
        result = []
        for i, c in enumerate(name):
            if c.isupper() and i > 0:
                result.append("_")
            result.append(c.lower())
        return "".join(result).replace(" ", "_").replace("-", "_")

    def _to_pascal_case(self, name: str) -> str:
        """Converte para PascalCase (ASCII only)."""
        name = self._normalize_name(name)
        words = name.replace("_", " ").replace("-", " ").split()
        return "".join(word.capitalize() for word in words)

    def _to_camel_case(self, name: str) -> str:
        """Converte para camelCase (ASCII only)."""
        pascal = self._to_pascal_case(name)
        return pascal[0].lower() + pascal[1:] if pascal else ""

    def _compute_input_hash(
        self,
        plan: Dict[str, Any],
        ir: Dict[str, Any],
        oas: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> str:
        """Calcula hash determinístico dos inputs."""
        # Serializar de forma ordenada para determinismo
        combined = json.dumps(
            {"plan": plan, "ir": ir, "oas": oas, "rbac": rbac},
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _next_order(self) -> int:
        """Retorna próximo número de ordem."""
        self._order_counter += 1
        return self._order_counter

    # ==================== CODE GENERATORS ====================

    def _generate_migration(
        self,
        entity: Dict[str, Any],
        order: int,
    ) -> str:
        """Gera SQL de migração para uma entidade."""
        name = self._to_snake_case(entity["name"])
        fields = entity.get("fields", [])

        columns = []
        for field in fields:
            field_name = self._to_snake_case(field["name"])
            field_type = self.TYPE_MAP_SQL.get(field.get("type", "string"), "VARCHAR(255)")

            constraints = []
            if field.get("required"):
                constraints.append("NOT NULL")
            if field.get("unique"):
                constraints.append("UNIQUE")

            constraint_str = " ".join(constraints)
            columns.append(f"    {field_name} {field_type} {constraint_str}".rstrip())

        # Primary key
        pk = entity.get("primary_key", "id")
        columns_str = ",\n".join(columns)

        return f"""-- Migration V{order}: Create table {name}
CREATE TABLE {name} (
{columns_str},
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ({pk})
);

-- Add indexes
CREATE INDEX idx_{name}_created_at ON {name}(created_at);
"""

    def _generate_entity(self, entity: Dict[str, Any]) -> str:
        """Gera JPA Entity Java."""
        name = self._to_pascal_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])
        fields = entity.get("fields", [])

        field_defs = []
        for field in fields:
            field_name = self._to_camel_case(field["name"])
            java_type = self.TYPE_MAP_JAVA.get(field.get("type", "string"), "String")

            annotations = []
            if field["name"] == entity.get("primary_key", "id"):
                annotations.append("    @Id")
                if field.get("type") == "uuid":
                    annotations.append("    @GeneratedValue(strategy = GenerationType.UUID)")
            if field.get("unique"):
                annotations.append(f'    @Column(unique = true)')
            elif field.get("required"):
                annotations.append(f'    @Column(nullable = false)')

            annotations_str = "\n".join(annotations)
            if annotations_str:
                field_defs.append(f"{annotations_str}\n    private {java_type} {field_name};")
            else:
                field_defs.append(f"    private {java_type} {field_name};")

        fields_str = "\n\n".join(field_defs)

        return f"""package com.example.app.domain;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "{snake_name}")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class {name} {{

{fields_str}

    @Column(name = "created_at")
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

    def _generate_repository(self, entity: Dict[str, Any]) -> str:
        """Gera Spring Data Repository."""
        name = self._to_pascal_case(entity["name"])
        pk_type = "UUID"  # Default
        for field in entity.get("fields", []):
            if field["name"] == entity.get("primary_key", "id"):
                pk_type = self.TYPE_MAP_JAVA.get(field.get("type", "uuid"), "UUID")
                break

        return f"""package com.example.app.repo;

import com.example.app.domain.{name};
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface {name}Repository extends JpaRepository<{name}, {pk_type}> {{
}}
"""

    def _generate_service(self, entity: Dict[str, Any]) -> str:
        """Gera Service class."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])

        return f"""package com.example.app.service;

import com.example.app.domain.{name};
import com.example.app.repo.{name}Repository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional
public class {name}Service {{

    private final {name}Repository {var_name}Repository;

    public List<{name}> findAll() {{
        return {var_name}Repository.findAll();
    }}

    public Optional<{name}> findById(UUID id) {{
        return {var_name}Repository.findById(id);
    }}

    public {name} save({name} {var_name}) {{
        return {var_name}Repository.save({var_name});
    }}

    public void deleteById(UUID id) {{
        {var_name}Repository.deleteById(id);
    }}

    public boolean existsById(UUID id) {{
        return {var_name}Repository.existsById(id);
    }}
}}
"""

    def _generate_controller(
        self,
        entity: Dict[str, Any],
        operations: List[str],
        permissions: Dict[str, str],
    ) -> str:
        """Gera REST Controller."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])
        path = f"/api/{snake_name}s"

        return f"""package com.example.app.api;

import com.example.app.domain.{name};
import com.example.app.service.{name}Service;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("{path}")
@RequiredArgsConstructor
public class {name}Controller {{

    private final {name}Service {var_name}Service;

    @GetMapping
    public ResponseEntity<List<{name}>> list{name}() {{
        return ResponseEntity.ok({var_name}Service.findAll());
    }}

    @PostMapping
    public ResponseEntity<{name}> create{name}(@RequestBody {name} {var_name}) {{
        {name} saved = {var_name}Service.save({var_name});
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }}

    @GetMapping("/{{id}}")
    public ResponseEntity<{name}> get{name}(@PathVariable UUID id) {{
        return {var_name}Service.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }}

    @PutMapping("/{{id}}")
    public ResponseEntity<{name}> update{name}(@PathVariable UUID id, @RequestBody {name} {var_name}) {{
        if (!{var_name}Service.existsById(id)) {{
            return ResponseEntity.notFound().build();
        }}
        {name} saved = {var_name}Service.save({var_name});
        return ResponseEntity.ok(saved);
    }}

    @DeleteMapping("/{{id}}")
    public ResponseEntity<Void> delete{name}(@PathVariable UUID id) {{
        if (!{var_name}Service.existsById(id)) {{
            return ResponseEntity.notFound().build();
        }}
        {var_name}Service.deleteById(id);
        return ResponseEntity.ok().build();
    }}
}}
"""

    def _generate_tsx_list_page(self, entity: Dict[str, Any]) -> str:
        """Gera página de listagem React/TypeScript."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])

        fields = entity.get("fields", [])
        # Deduplica campos (evita id duplicado)
        seen_fields: Set[str] = set()
        unique_fields = []
        for f in fields:
            field_key = self._to_camel_case(f["name"])
            if field_key not in seen_fields:
                seen_fields.add(field_key)
                unique_fields.append(f)

        display_fields = [f for f in unique_fields if f["name"] != "id"][:4]
        headers = [f"            <th>{self._to_pascal_case(f['name'])}</th>" for f in display_fields]
        headers_str = "\n".join(headers)

        cells = [f"              <td>{{item.{self._to_camel_case(f['name'])}}}</td>" for f in display_fields]
        cells_str = "\n".join(cells)

        # Gera interface com campos únicos
        interface_fields = "\n".join(
            f"  {self._to_camel_case(f['name'])}: {self.TYPE_MAP_TS.get(f.get('type', 'string'), 'string')};"
            for f in unique_fields
        )

        return f"""import {{ useQuery }} from '@tanstack/react-query';
import {{ Link }} from 'react-router-dom';
import {{ api }} from '../../api/client';
import type {{ AxiosResponse }} from 'axios';

interface {name} {{
{interface_fields}
}}

export function {name}List() {{
  const {{ data: {var_name}s, isLoading, error }} = useQuery({{
    queryKey: ['{var_name}s'],
    queryFn: () => api.get<{name}[]>('/{snake_name}s').then((res: AxiosResponse<{name}[]>) => res.data),
  }});

  if (isLoading) return <div>Carregando...</div>;
  if (error) return <div>Erro ao carregar dados</div>;

  return (
    <div className="container">
      <h1>Lista de {name}</h1>
      <Link to="/{snake_name}/new" className="btn btn-primary mb-3">
        Novo {name}
      </Link>
      <table className="table">
        <thead>
          <tr>
{headers_str}
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          {{{var_name}s?.map((item) => (
            <tr key={{item.id}}>
{cells_str}
              <td>
                <Link to={{`/{snake_name}/${{item.id}}`}} className="btn btn-sm btn-info">
                  Ver
                </Link>
              </td>
            </tr>
          ))}}
        </tbody>
      </table>
    </div>
  );
}}

export default {name}List;
"""

    def _generate_tsx_new_page(self, entity: Dict[str, Any]) -> str:
        """Gera página de criação React/TypeScript."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])

        # Deduplica e exclui id
        seen_fields: Set[str] = set()
        unique_fields = []
        for f in entity.get("fields", []):
            field_key = self._to_camel_case(f["name"])
            if field_key not in seen_fields and f["name"] != "id":
                seen_fields.add(field_key)
                unique_fields.append(f)

        form_fields = []
        for f in unique_fields:
            field_name = self._to_camel_case(f["name"])
            label = self._to_pascal_case(f["name"])
            required = "required" if f.get("required") else ""
            form_fields.append(f"""        <div className="mb-3">
          <label className="form-label">{label}</label>
          <input
            type="text"
            className="form-control"
            value={{formData.{field_name}}}
            onChange={{(e) => setFormData({{...formData, {field_name}: e.target.value}})}}
            {required}
          />
        </div>""")
        form_fields_str = "\n".join(form_fields)

        initial_state = ", ".join([f"{self._to_camel_case(f['name'])}: ''" for f in unique_fields])

        if unique_fields:
            state_hook = f"  const [formData, setFormData] = useState({{ {initial_state} }});"
        else:
            state_hook = "  const [formData] = useState({});"

        return f"""import {{ useState, FormEvent }} from 'react';
import {{ useMutation, useQueryClient }} from '@tanstack/react-query';
import {{ useNavigate }} from 'react-router-dom';
import {{ api }} from '../../api/client';

export function {name}New() {{
  const navigate = useNavigate();
  const queryClient = useQueryClient();
{state_hook}

  const mutation = useMutation({{
    mutationFn: (data: typeof formData) => api.post('/{snake_name}s', data),
    onSuccess: () => {{
      queryClient.invalidateQueries({{ queryKey: ['{var_name}s'] }});
      navigate('/{snake_name}');
    }},
  }});

  const handleSubmit = (e: FormEvent) => {{
    e.preventDefault();
    mutation.mutate(formData);
  }};

  return (
    <div className="container">
      <h1>Novo {name}</h1>
      <form onSubmit={{handleSubmit}}>
{form_fields_str}
        <button type="submit" className="btn btn-primary" disabled={{mutation.isPending}}>
          {{mutation.isPending ? 'Salvando...' : 'Salvar'}}
        </button>
      </form>
    </div>
  );
}}

export default {name}New;
"""

    def _generate_tsx_detail_page(self, entity: Dict[str, Any]) -> str:
        """Gera página de detalhes React/TypeScript."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        snake_name = self._to_snake_case(entity["name"])

        # Deduplica campos
        seen_fields: Set[str] = set()
        unique_fields = []
        for f in entity.get("fields", []):
            field_key = self._to_camel_case(f["name"])
            if field_key not in seen_fields:
                seen_fields.add(field_key)
                unique_fields.append(f)

        detail_fields = []
        for f in unique_fields:
            field_name = self._to_camel_case(f["name"])
            label = self._to_pascal_case(f["name"])
            detail_fields.append(f"""        <p><strong>{label}:</strong> {{{var_name}?.{field_name}}}</p>""")
        detail_fields_str = "\n".join(detail_fields)

        # Gera interface com campos únicos
        interface_fields = "\n".join(
            f"  {self._to_camel_case(f['name'])}: {self.TYPE_MAP_TS.get(f.get('type', 'string'), 'string')};"
            for f in unique_fields
        )

        return f"""import {{ useQuery, useMutation, useQueryClient }} from '@tanstack/react-query';
import {{ useParams, useNavigate, Link }} from 'react-router-dom';
import {{ api }} from '../../api/client';
import type {{ AxiosResponse }} from 'axios';

interface {name} {{
{interface_fields}
}}

export function {name}Detail() {{
  const {{ id }} = useParams<{{ id: string }}>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {{ data: {var_name}, isLoading, error }} = useQuery({{
    queryKey: ['{var_name}', id],
    queryFn: () => api.get<{name}>(`/{snake_name}s/${{id}}`).then((res: AxiosResponse<{name}>) => res.data),
  }});

  const deleteMutation = useMutation({{
    mutationFn: () => api.delete(`/{snake_name}s/${{id}}`),
    onSuccess: () => {{
      queryClient.invalidateQueries({{ queryKey: ['{var_name}s'] }});
      navigate('/{snake_name}');
    }},
  }});

  if (isLoading) return <div>Carregando...</div>;
  if (error) return <div>Erro ao carregar dados</div>;

  return (
    <div className="container">
      <h1>Detalhes de {name}</h1>
      <div className="card">
        <div className="card-body">
{detail_fields_str}
        </div>
      </div>
      <div className="mt-3">
        <Link to="/{snake_name}" className="btn btn-secondary me-2">Voltar</Link>
        <button
          className="btn btn-danger"
          onClick={{() => deleteMutation.mutate()}}
          disabled={{deleteMutation.isPending}}
        >
          {{deleteMutation.isPending ? 'Excluindo...' : 'Excluir'}}
        </button>
      </div>
    </div>
  );
}}

export default {name}Detail;
"""

    def _generate_api_client_entry(self, entities: List[Dict[str, Any]]) -> str:
        """Gera entrada do API client para todas as entidades."""
        imports = []
        exports = []

        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            snake_name = self._to_snake_case(entity["name"])

            exports.append(f"""
// {name} API
export const {snake_name}Api = {{
  list: () => api.get('/{snake_name}s'),
  get: (id: string) => api.get(`/{snake_name}s/${{id}}`),
  create: (data: any) => api.post('/{snake_name}s', data),
  update: (id: string, data: any) => api.put(`/{snake_name}s/${{id}}`, data),
  delete: (id: string) => api.delete(`/{snake_name}s/${{id}}`),
}};""")

        return f"""import axios from 'axios';

export const api = axios.create({{
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8080/api',
  headers: {{
    'Content-Type': 'application/json',
  }},
}});

// Add auth token interceptor
api.interceptors.request.use((config) => {{
  const token = localStorage.getItem('token');
  if (token) {{
    config.headers.Authorization = `Bearer ${{token}}`;
  }}
  return config;
}});
{"".join(exports)}
"""

    # ==================== ROUTES.TSX GENERATION ====================

    def _generate_routes_tsx(self, entities: List[Dict[str, Any]]) -> str:
        """Gera routes.tsx preenchendo slots do template.

        Usa o template base e substitui apenas o conteúdo dos slots:
        - imports: Imports das páginas de cada entidade
        - routes-array: Array de rotas para cada entidade

        Args:
            entities: Lista de entidades do IR

        Returns:
            Conteúdo completo do routes.tsx com slots preenchidos
        """
        # Ler template base
        template_content = read_template("src/routes.tsx")

        # Gerar conteúdo do slot IMPORTS (ordem alfabética por entity.name)
        sorted_entities = sorted(entities, key=lambda e: e["name"])
        imports = []
        routes = []

        for entity in sorted_entities:
            name = self._to_pascal_case(entity["name"])
            snake_name = self._to_snake_case(entity["name"])

            imports.append(f"import {name}List from './pages/{snake_name}/List';")
            imports.append(f"import {name}New from './pages/{snake_name}/New';")
            imports.append(f"import {name}Detail from './pages/{snake_name}/Detail';")

            routes.append(f"  {{ path: '/{snake_name}', element: <{name}List /> }},")
            routes.append(f"  {{ path: '/{snake_name}/new', element: <{name}New /> }},")
            routes.append(f"  {{ path: '/{snake_name}/:id', element: <{name}Detail /> }},")

        imports_content = "\n".join(imports)
        routes_content = "\n".join(routes)

        # Substituir slots
        result = replace_slot(template_content, "imports", imports_content, "routes.tsx")
        result = replace_slot(result, "routes-array", routes_content, "routes.tsx")

        return result

    # ==================== APP.TSX GENERATION (SLOT-BASED) ====================

    def _generate_app_tsx(self, entities: List[Dict[str, Any]]) -> str:
        """Gera App.tsx preenchendo slots do template.

        Usa o template base e substitui apenas o conteúdo dos slots:
        - nav: Links de navegação para cada entidade
        - routes: Mapeamento de rotas usando array importado

        Args:
            entities: Lista de entidades do IR

        Returns:
            Conteúdo completo do App.tsx com slots preenchidos
        """
        # Ler template base
        template_content = read_template("src/App.tsx")

        # Gerar conteúdo do slot NAV (ordem alfabética por entity.name)
        sorted_entities = sorted(entities, key=lambda e: e["name"])
        nav_links = []
        for entity in sorted_entities:
            name = self._to_pascal_case(entity["name"])
            snake_name = self._to_snake_case(entity["name"])
            nav_links.append(f'          <Link to="/{snake_name}" className="nav-link">{name}</Link>')

        nav_content = "\n".join(nav_links)

        # Gerar conteúdo do slot ROUTES
        routes_content = """          {routes.map((route, index) => (
            <Route key={index} path={route.path} element={route.element} />
          ))}"""

        # Substituir slots
        result = replace_slot(template_content, "nav", nav_content, "App.tsx")
        result = replace_slot(result, "routes", routes_content, "App.tsx")

        return result

    # ==================== HOMEPAGE.TSX GENERATION (SLOT-BASED) ====================

    def _generate_homepage_tsx(self, entities: List[Dict[str, Any]]) -> str:
        """Gera HomePage.tsx preenchendo slots do template.

        Usa o template base e substitui apenas o conteúdo do slot:
        - entities: Lista de links para cada entidade

        Args:
            entities: Lista de entidades do IR

        Returns:
            Conteúdo completo do HomePage.tsx com slot preenchido
        """
        # Ler template base
        template_content = read_template("src/pages/HomePage.tsx")

        # Gerar conteúdo do slot ENTITIES (ordem alfabética por entity.name)
        sorted_entities = sorted(entities, key=lambda e: e["name"])
        entity_links = []
        for entity in sorted_entities:
            # Title Case simples: primeira letra maiúscula
            name = self._to_pascal_case(entity["name"])
            snake_name = self._to_snake_case(entity["name"])
            entity_links.append(f'          <li><Link to="/{snake_name}">{name}</Link></li>')

        entities_content = "\n".join(entity_links)

        # Substituir slot
        result = replace_slot(template_content, "entities", entities_content, "HomePage.tsx")

        return result

    # ==================== MAIN GENERATION ====================

    def generate(
        self,
        plan: Dict[str, Any],
        ir: Dict[str, Any],
        oas: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> PatchSet:
        """Gera patches a partir dos artefatos.

        Args:
            plan: Plano de execução
            ir: Intermediate Representation
            oas: OpenAPI Specification
            rbac: Role-Based Access Control

        Returns:
            PatchSet com todos os patches gerados
        """
        self._order_counter = 0
        input_hash = self._compute_input_hash(plan, ir, oas, rbac)

        patches: List[Patch] = []
        entities = ir.get("domain", {}).get("entities", [])

        # Build permission map from RBAC
        permissions = {}
        for perm in rbac.get("permissions", []):
            permissions[perm["operation_id"]] = perm.get("required_role", "authenticated")

        # Process each task from PLAN
        for task in sorted(plan.get("tasks", []), key=lambda t: t.get("order", 0)):
            task_id = task["id"]
            task_patches = self._generate_task_patches(
                task, entities, oas, permissions
            )
            patches.extend(task_patches)

        # Generate global frontend patches (routes, App, HomePage)
        # These depend on all entities and must be generated after entity pages
        if entities:
            global_patches = self._generate_global_frontend_patches(entities)
            patches.extend(global_patches)

        return PatchSet(
            project=self.project,
            patches=patches,
            input_hash=input_hash,
        )

    def _generate_global_frontend_patches(
        self,
        entities: List[Dict[str, Any]],
    ) -> List[Patch]:
        """Gera patches globais do frontend: routes.tsx, App.tsx, HomePage.tsx."""
        patches = []

        # 1. routes.tsx - Define todas as rotas das entidades
        # Usa "modify" pois o template ja copia um routes.tsx basico
        routes_content = self._generate_routes_tsx(entities)
        patches.append(Patch(
            file_path="frontend/src/routes.tsx",
            operation="modify",
            content=routes_content,
            task_id="global_frontend_routes",
            order=self._next_order(),
        ))

        # 2. App.tsx - Componente principal com navegacao e rotas
        # Usa "modify" pois o template ja copia um App.tsx basico
        app_content = self._generate_app_tsx(entities)
        patches.append(Patch(
            file_path="frontend/src/App.tsx",
            operation="modify",
            content=app_content,
            task_id="global_frontend_app",
            order=self._next_order(),
        ))

        # 3. HomePage.tsx - Pagina inicial com links para entidades
        # Usa "modify" pois o template ja copia um HomePage.tsx basico
        homepage_content = self._generate_homepage_tsx(entities)
        patches.append(Patch(
            file_path="frontend/src/pages/HomePage.tsx",
            operation="modify",
            content=homepage_content,
            task_id="global_frontend_homepage",
            order=self._next_order(),
        ))

        return patches

    def _generate_task_patches(
        self,
        task: Dict[str, Any],
        entities: List[Dict[str, Any]],
        oas: Dict[str, Any],
        permissions: Dict[str, str],
    ) -> List[Patch]:
        """Gera patches para uma task específica."""
        patches = []
        task_id = task["id"]
        files = task.get("files", [])

        for file_path in files:
            # Determine entity from task_id
            entity_name = self._extract_entity_from_task(task_id)
            entity = self._find_entity(entities, entity_name)

            if not entity:
                continue

            content = self._generate_file_content(
                file_path, entity, oas, permissions
            )

            if content:
                patches.append(Patch(
                    file_path=file_path,
                    operation="create",
                    content=content,
                    task_id=task_id,
                    order=self._next_order(),
                ))

        return patches

    def _extract_entity_from_task(self, task_id: str) -> str:
        """Extrai nome da entidade do task_id."""
        # task_empresa_migration -> empresa
        # task_endereco_model -> endereco
        parts = task_id.split("_")
        if len(parts) >= 2:
            return parts[1]
        return ""

    def _find_entity(
        self,
        entities: List[Dict[str, Any]],
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Encontra entidade pelo nome (normalizado)."""
        for entity in entities:
            normalized = self._to_snake_case(entity["name"])
            if normalized == name:
                return entity
        return None

    def _generate_file_content(
        self,
        file_path: str,
        entity: Dict[str, Any],
        oas: Dict[str, Any],
        permissions: Dict[str, str],
    ) -> str:
        """Gera conteúdo do arquivo baseado no tipo."""
        if file_path.endswith(".sql"):
            # Extract version number from path
            # V1__create_empresa.sql -> order 1
            import re
            match = re.search(r"V(\d+)__", file_path)
            order = int(match.group(1)) if match else 1
            return self._generate_migration(entity, order)

        elif "domain/" in file_path and file_path.endswith(".java"):
            return self._generate_entity(entity)

        elif "repo/" in file_path and file_path.endswith(".java"):
            return self._generate_repository(entity)

        elif "service/" in file_path and file_path.endswith(".java"):
            return self._generate_service(entity)

        elif "api/" in file_path and file_path.endswith("Controller.java"):
            operations = self._get_entity_operations(entity, oas)
            return self._generate_controller(entity, operations, permissions)

        elif "pages/" in file_path and "List.tsx" in file_path:
            return self._generate_tsx_list_page(entity)

        elif "pages/" in file_path and "New.tsx" in file_path:
            return self._generate_tsx_new_page(entity)

        elif "pages/" in file_path and "Detail.tsx" in file_path:
            return self._generate_tsx_detail_page(entity)

        elif "api/client.ts" in file_path:
            # API client needs all entities
            return ""  # Will be generated separately

        return ""

    def _get_entity_operations(
        self,
        entity: Dict[str, Any],
        oas: Dict[str, Any],
    ) -> List[str]:
        """Extrai operações da entidade do OAS."""
        name = self._to_pascal_case(entity["name"])
        operations = []

        for path, methods in oas.get("paths", {}).items():
            for method, op in methods.items():
                if isinstance(op, dict):
                    op_id = op.get("operationId", "")
                    if name.lower() in op_id.lower():
                        operations.append(op_id)

        return operations


def generate_patches(
    project: str,
    plan: Dict[str, Any],
    ir: Dict[str, Any],
    oas: Dict[str, Any],
    rbac: Dict[str, Any],
    generated_root: Optional[str] = None,
) -> PatchSet:
    """Função de conveniência para gerar patches.

    Args:
        project: Nome do projeto
        plan: Plano de execução
        ir: Intermediate Representation
        oas: OpenAPI Specification
        rbac: Role-Based Access Control
        generated_root: Diretório raiz para projetos gerados (from config if None)

    Returns:
        PatchSet com todos os patches gerados
    """
    generator = PatchGenerator(project, generated_root)
    return generator.generate(plan, ir, oas, rbac)
