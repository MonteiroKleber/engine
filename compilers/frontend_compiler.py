"""Frontend Compiler - Gera código React/TypeScript a partir do IR + OAS.

Gera:
- TypeScript API client tipado (gerado do OpenAPI)
- Tipos/interfaces TypeScript
- Páginas CRUD funcionais (List, Form, Detail)
- Formulários tipados com validação
- Router config

Entrada:
- IR: Intermediate Representation com entidades e campos
- OAS: OpenAPI Specification com endpoints

Saída:
- Código TypeScript/React pronto para compilar
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class GeneratedFile:
    """Arquivo TypeScript/React gerado."""

    path: str  # Caminho relativo ao projeto (ex: src/api/client.ts)
    content: str
    file_type: str  # "types", "client", "page", "component", "config"

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "path": self.path,
            "content": self.content,
            "file_type": self.file_type,
        }


@dataclass
class FrontendOutput:
    """Saída do FrontendCompiler."""

    files: List[GeneratedFile] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "files": [f.to_dict() for f in self.files],
            "entities": self.entities,
            "warnings": self.warnings,
            "file_count": len(self.files),
        }


class FrontendCompiler:
    """Compila artefatos para código React/TypeScript.

    Gera código funcional que:
    - Types para entidades e DTOs
    - API client tipado gerado do OpenAPI
    - Páginas CRUD com React Query
    - Formulários tipados

    Attributes:
        project_root: Caminho raiz do projeto
    """

    # Mapeamento de tipos IR para TypeScript
    TYPE_MAP_TS = {
        "uuid": "string",
        "string": "string",
        "text": "string",
        "integer": "number",
        "long": "number",
        "boolean": "boolean",
        "date": "string",  # ISO date string
        "datetime": "string",  # ISO datetime string
        "decimal": "number",
        "email": "string",
        "phone": "string",
        "url": "string",
    }

    # Input types para formulários
    INPUT_TYPE_MAP = {
        "uuid": "text",
        "string": "text",
        "text": "textarea",
        "integer": "number",
        "long": "number",
        "boolean": "checkbox",
        "date": "date",
        "datetime": "datetime-local",
        "decimal": "number",
        "email": "email",
        "phone": "tel",
        "url": "url",
    }

    def __init__(
        self,
        project_root: str = "/home/bazari/generated",
    ) -> None:
        """Inicializa o FrontendCompiler.

        Args:
            project_root: Diretório raiz do projeto
        """
        self.project_root = Path(project_root)

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

    def _to_kebab_case(self, name: str) -> str:
        """Converte para kebab-case."""
        return self._to_snake_case(name).replace("_", "-")

    # ==================== COMPILE ====================

    def compile(
        self,
        ir: Dict[str, Any],
        oas: Dict[str, Any],
    ) -> FrontendOutput:
        """Compila IR + OAS para código React/TypeScript.

        Args:
            ir: Intermediate Representation
            oas: OpenAPI Specification

        Returns:
            FrontendOutput com todos os arquivos gerados
        """
        output = FrontendOutput()
        entities = ir.get("domain", {}).get("entities", [])

        # Extrair operações do OAS
        operations = self._extract_operations(oas)

        # 1. Gerar tipos TypeScript
        types_file = self._generate_types(entities)
        output.files.append(types_file)

        # 2. Gerar API client tipado
        client_file = self._generate_api_client(entities, operations)
        output.files.append(client_file)

        # 3. Gerar páginas CRUD para cada entidade
        for entity in entities:
            entity_name = self._to_pascal_case(entity["name"])
            output.entities.append(entity_name)

            # List page
            list_page = self._generate_list_page(entity)
            output.files.append(list_page)

            # Form page (create/edit)
            form_page = self._generate_form_page(entity)
            output.files.append(form_page)

            # Detail page
            detail_page = self._generate_detail_page(entity)
            output.files.append(detail_page)

        # 4. Gerar hooks customizados
        hooks_file = self._generate_hooks(entities)
        output.files.append(hooks_file)

        # 5. Gerar router config
        router_file = self._generate_router(entities)
        output.files.append(router_file)

        # 6. Gerar App.tsx atualizado
        app_file = self._generate_app(entities)
        output.files.append(app_file)

        return output

    def _extract_operations(self, oas: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extrai operações do OAS organizadas por entidade."""
        operations: Dict[str, Dict[str, Any]] = {}

        for path, methods in oas.get("paths", {}).items():
            # /api/empresas -> empresas
            parts = path.strip("/").split("/")
            if len(parts) >= 2:
                resource = parts[1]
                entity_name = resource.rstrip("s")  # Remove plural
            else:
                continue

            if entity_name not in operations:
                operations[entity_name] = {"path": f"/api/{resource}", "methods": {}}

            for method, op_data in methods.items():
                if isinstance(op_data, dict) and method in ["get", "post", "put", "patch", "delete"]:
                    op_id = op_data.get("operationId", "")
                    has_id = "{" in path

                    op_info = {
                        "operationId": op_id,
                        "path": path,
                        "hasId": has_id,
                    }

                    if has_id:
                        if method == "get":
                            operations[entity_name]["methods"]["getById"] = op_info
                        elif method == "put":
                            operations[entity_name]["methods"]["update"] = op_info
                        elif method == "delete":
                            operations[entity_name]["methods"]["delete"] = op_info
                    else:
                        if method == "get":
                            operations[entity_name]["methods"]["list"] = op_info
                        elif method == "post":
                            operations[entity_name]["methods"]["create"] = op_info

        return operations

    # ==================== TYPES GENERATION ====================

    def _generate_types(self, entities: List[Dict[str, Any]]) -> GeneratedFile:
        """Gera arquivo de tipos TypeScript."""
        type_defs = []

        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            fields = entity.get("fields", [])

            # Interface principal
            field_defs = []
            for fld in fields:
                field_name = self._to_camel_case(fld["name"])
                ts_type = self.TYPE_MAP_TS.get(fld.get("type", "string"), "string")
                optional = "" if fld.get("required") else "?"
                field_defs.append(f"  {field_name}{optional}: {ts_type};")

            # Adicionar timestamps
            field_defs.append("  createdAt?: string;")
            field_defs.append("  updatedAt?: string;")

            type_defs.append(f"""/**
 * Entidade {name}
 */
export interface {name} {{
{chr(10).join(field_defs)}
}}""")

            # Request type (sem id e timestamps)
            request_fields = []
            for fld in fields:
                if fld["name"] == entity.get("primary_key", "id"):
                    continue
                field_name = self._to_camel_case(fld["name"])
                ts_type = self.TYPE_MAP_TS.get(fld.get("type", "string"), "string")
                optional = "" if fld.get("required") else "?"
                request_fields.append(f"  {field_name}{optional}: {ts_type};")

            type_defs.append(f"""/**
 * Request para criar/atualizar {name}
 */
export interface {name}Request {{
{chr(10).join(request_fields)}
}}""")

        content = f"""/**
 * Tipos TypeScript gerados automaticamente pelo Bazari Engine.
 * NÃO EDITE MANUALMENTE - será sobrescrito na próxima geração.
 */

{chr(10).join(type_defs)}

/**
 * Response padrão de API
 */
export interface ApiResponse<T> {{
  data: T;
  message?: string;
}}

/**
 * Response de lista paginada
 */
export interface PagedResponse<T> {{
  content: T[];
  totalElements: number;
  totalPages: number;
  page: number;
  size: number;
}}

/**
 * Erro de API
 */
export interface ApiError {{
  message: string;
  code?: string;
  details?: Record<string, string>;
}}
"""

        return GeneratedFile(
            path="src/types/index.ts",
            content=content,
            file_type="types",
        )

    # ==================== API CLIENT GENERATION ====================

    def _generate_api_client(
        self,
        entities: List[Dict[str, Any]],
        operations: Dict[str, Dict[str, Any]],
    ) -> GeneratedFile:
        """Gera API client tipado."""
        entity_clients = []

        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            snake_name = self._to_snake_case(entity["name"])
            var_name = self._to_camel_case(entity["name"])

            ops = operations.get(snake_name, {})
            base_path = ops.get("path", f"/api/{snake_name}s")

            entity_clients.append(f"""/**
 * API client para {name}
 */
export const {var_name}Api = {{
  /**
   * Lista todos os registros
   */
  list: async (): Promise<{name}[]> => {{
    const response = await apiClient.get<{name}[]>('{base_path}');
    return response.data;
  }},

  /**
   * Busca por ID
   */
  getById: async (id: string): Promise<{name}> => {{
    const response = await apiClient.get<{name}>(`{base_path}/${{id}}`);
    return response.data;
  }},

  /**
   * Cria novo registro
   */
  create: async (data: {name}Request): Promise<{name}> => {{
    const response = await apiClient.post<{name}>('{base_path}', data);
    return response.data;
  }},

  /**
   * Atualiza registro existente
   */
  update: async (id: string, data: {name}Request): Promise<{name}> => {{
    const response = await apiClient.put<{name}>(`{base_path}/${{id}}`, data);
    return response.data;
  }},

  /**
   * Remove registro por ID
   */
  delete: async (id: string): Promise<void> => {{
    await apiClient.delete(`{base_path}/${{id}}`);
  }},
}};""")

        imports = ", ".join([self._to_pascal_case(e["name"]) for e in entities])
        request_imports = ", ".join([f"{self._to_pascal_case(e['name'])}Request" for e in entities])

        content = f"""/**
 * API Client tipado gerado automaticamente do OpenAPI.
 * NÃO EDITE MANUALMENTE - será sobrescrito na próxima geração.
 */

import axios from 'axios';
import type {{ {imports}, {request_imports} }} from '../types';

/**
 * Instância do axios configurada
 */
const apiClient = axios.create({{
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: {{
    'Content-Type': 'application/json',
  }},
}});

/**
 * Interceptor para adicionar token de autenticação
 */
apiClient.interceptors.request.use((config) => {{
  const token = localStorage.getItem('token');
  if (token) {{
    config.headers.Authorization = `Bearer ${{token}}`;
  }}
  return config;
}});

/**
 * Interceptor para tratamento de erros
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {{
    if (error.response?.status === 401) {{
      localStorage.removeItem('token');
      window.location.href = '/login';
    }}
    return Promise.reject(error);
  }}
);

{chr(10).join(entity_clients)}

export default apiClient;
"""

        return GeneratedFile(
            path="src/api/client.ts",
            content=content,
            file_type="client",
        )

    # ==================== HOOKS GENERATION ====================

    def _generate_hooks(self, entities: List[Dict[str, Any]]) -> GeneratedFile:
        """Gera React Query hooks."""
        hook_defs = []

        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            var_name = self._to_camel_case(entity["name"])

            hook_defs.append(f"""// ==================== {name.upper()} HOOKS ====================

/**
 * Hook para listar {name}
 */
export function use{name}List() {{
  return useQuery({{
    queryKey: ['{var_name}s'],
    queryFn: () => {var_name}Api.list(),
  }});
}}

/**
 * Hook para buscar {name} por ID
 */
export function use{name}(id: string | undefined) {{
  return useQuery({{
    queryKey: ['{var_name}', id],
    queryFn: () => {var_name}Api.getById(id!),
    enabled: !!id,
  }});
}}

/**
 * Hook para criar {name}
 */
export function useCreate{name}() {{
  const queryClient = useQueryClient();

  return useMutation({{
    mutationFn: (data: {name}Request) => {var_name}Api.create(data),
    onSuccess: () => {{
      queryClient.invalidateQueries({{ queryKey: ['{var_name}s'] }});
    }},
  }});
}}

/**
 * Hook para atualizar {name}
 */
export function useUpdate{name}() {{
  const queryClient = useQueryClient();

  return useMutation({{
    mutationFn: ({{ id, data }}: {{ id: string; data: {name}Request }}) =>
      {var_name}Api.update(id, data),
    onSuccess: (_, {{ id }}) => {{
      queryClient.invalidateQueries({{ queryKey: ['{var_name}s'] }});
      queryClient.invalidateQueries({{ queryKey: ['{var_name}', id] }});
    }},
  }});
}}

/**
 * Hook para deletar {name}
 */
export function useDelete{name}() {{
  const queryClient = useQueryClient();

  return useMutation({{
    mutationFn: (id: string) => {var_name}Api.delete(id),
    onSuccess: () => {{
      queryClient.invalidateQueries({{ queryKey: ['{var_name}s'] }});
    }},
  }});
}}""")

        imports = ", ".join([self._to_pascal_case(e["name"]) + "Request" for e in entities])
        api_imports = ", ".join([self._to_camel_case(e["name"]) + "Api" for e in entities])

        content = f"""/**
 * React Query hooks gerados automaticamente.
 * NÃO EDITE MANUALMENTE - será sobrescrito na próxima geração.
 */

import {{ useQuery, useMutation, useQueryClient }} from '@tanstack/react-query';
import {{ {api_imports} }} from '../api/client';
import type {{ {imports} }} from '../types';

{chr(10).join(hook_defs)}
"""

        return GeneratedFile(
            path="src/hooks/index.ts",
            content=content,
            file_type="hooks",
        )

    # ==================== LIST PAGE GENERATION ====================

    def _generate_list_page(self, entity: Dict[str, Any]) -> GeneratedFile:
        """Gera página de listagem."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        kebab_name = self._to_kebab_case(entity["name"])
        fields = entity.get("fields", [])

        # Colunas da tabela (primeiros 4-5 campos)
        display_fields = [f for f in fields if f["name"] != "id"][:4]

        headers = "\n".join([
            f"            <th>{self._to_pascal_case(f['name'])}</th>"
            for f in display_fields
        ])

        cells = "\n".join([
            f"              <td>{{item.{self._to_camel_case(f['name'])}}}</td>"
            for f in display_fields
        ])

        content = f"""/**
 * Página de listagem de {name}
 */

import {{ Link }} from 'react-router-dom';
import {{ use{name}List, useDelete{name} }} from '../../hooks';

export function {name}ListPage() {{
  const {{ data: items, isLoading, error }} = use{name}List();
  const deleteMutation = useDelete{name}();

  const handleDelete = (id: string) => {{
    if (window.confirm('Tem certeza que deseja excluir?')) {{
      deleteMutation.mutate(id);
    }}
  }};

  if (isLoading) {{
    return <div className="loading">Carregando...</div>;
  }}

  if (error) {{
    return <div className="error">Erro ao carregar dados: {{String(error)}}</div>;
  }}

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>{name}</h1>
        <Link to="/{kebab_name}/new" className="btn btn-primary">
          Novo {name}
        </Link>
      </div>

      <table className="data-table">
        <thead>
          <tr>
{headers}
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          {{items?.map((item) => (
            <tr key={{item.id}}>
{cells}
              <td className="actions">
                <Link to={{`/{kebab_name}/${{item.id}}`}} className="btn btn-sm">
                  Ver
                </Link>
                <Link to={{`/{kebab_name}/${{item.id}}/edit`}} className="btn btn-sm">
                  Editar
                </Link>
                <button
                  onClick={{() => handleDelete(item.id)}}
                  className="btn btn-sm btn-danger"
                  disabled={{deleteMutation.isPending}}
                >
                  Excluir
                </button>
              </td>
            </tr>
          ))}}
        </tbody>
      </table>

      {{items?.length === 0 && (
        <div className="empty-state">
          Nenhum registro encontrado.
        </div>
      )}}
    </div>
  );
}}

export default {name}ListPage;
"""

        return GeneratedFile(
            path=f"src/pages/{var_name}/{name}ListPage.tsx",
            content=content,
            file_type="page",
        )

    # ==================== FORM PAGE GENERATION ====================

    def _generate_form_page(self, entity: Dict[str, Any]) -> GeneratedFile:
        """Gera página de formulário (criar/editar)."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        kebab_name = self._to_kebab_case(entity["name"])
        fields = entity.get("fields", [])
        pk = entity.get("primary_key", "id")

        # Campos do formulário (excluindo PK)
        form_fields = [f for f in fields if f["name"] != pk]

        # Estado inicial
        initial_state = ", ".join([
            f"{self._to_camel_case(f['name'])}: ''"
            for f in form_fields
        ])

        # Campos do formulário
        field_inputs = []
        for fld in form_fields:
            field_name = self._to_camel_case(fld["name"])
            label = self._to_pascal_case(fld["name"])
            input_type = self.INPUT_TYPE_MAP.get(fld.get("type", "string"), "text")
            required = "required" if fld.get("required") else ""

            if input_type == "textarea":
                field_inputs.append(f"""      <div className="form-group">
        <label htmlFor="{field_name}">{label}</label>
        <textarea
          id="{field_name}"
          name="{field_name}"
          value={{formData.{field_name}}}
          onChange={{handleChange}}
          className="form-control"
          {required}
        />
      </div>""")
            elif input_type == "checkbox":
                field_inputs.append(f"""      <div className="form-group form-check">
        <input
          type="checkbox"
          id="{field_name}"
          name="{field_name}"
          checked={{Boolean(formData.{field_name})}}
          onChange={{(e) => setFormData({{ ...formData, {field_name}: e.target.checked }})}}
          className="form-check-input"
        />
        <label htmlFor="{field_name}" className="form-check-label">{label}</label>
      </div>""")
            else:
                field_inputs.append(f"""      <div className="form-group">
        <label htmlFor="{field_name}">{label}</label>
        <input
          type="{input_type}"
          id="{field_name}"
          name="{field_name}"
          value={{formData.{field_name}}}
          onChange={{handleChange}}
          className="form-control"
          {required}
        />
      </div>""")

        fields_str = "\n\n".join(field_inputs)

        # Mapeamento de dados existentes para form
        existing_mapping = "\n".join([
            f"          {self._to_camel_case(f['name'])}: existing.{self._to_camel_case(f['name'])} ?? '',"
            for f in form_fields
        ])

        content = f"""/**
 * Página de formulário para {name} (criar/editar)
 */

import {{ useState, useEffect }} from 'react';
import {{ useNavigate, useParams }} from 'react-router-dom';
import {{ use{name}, useCreate{name}, useUpdate{name} }} from '../../hooks';
import type {{ {name}Request }} from '../../types';

export function {name}FormPage() {{
  const {{ id }} = useParams<{{ id: string }}>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const {{ data: existing, isLoading }} = use{name}(id);
  const createMutation = useCreate{name}();
  const updateMutation = useUpdate{name}();

  const [formData, setFormData] = useState<{name}Request>({{
    {initial_state}
  }});

  useEffect(() => {{
    if (existing) {{
      setFormData({{
{existing_mapping}
      }});
    }}
  }}, [existing]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {{
    const {{ name, value }} = e.target;
    setFormData((prev) => ({{ ...prev, [name]: value }}));
  }};

  const handleSubmit = async (e: React.FormEvent) => {{
    e.preventDefault();

    try {{
      if (isEdit && id) {{
        await updateMutation.mutateAsync({{ id, data: formData }});
      }} else {{
        await createMutation.mutateAsync(formData);
      }}
      navigate('/{kebab_name}');
    }} catch (error) {{
      console.error('Erro ao salvar:', error);
    }}
  }};

  if (isEdit && isLoading) {{
    return <div className="loading">Carregando...</div>;
  }}

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>{{isEdit ? 'Editar' : 'Novo'}} {name}</h1>
      </div>

      <form onSubmit={{handleSubmit}} className="form">
{fields_str}

        <div className="form-actions">
          <button
            type="button"
            onClick={{() => navigate('/{kebab_name}')}}
            className="btn btn-secondary"
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={{isPending}}
          >
            {{isPending ? 'Salvando...' : 'Salvar'}}
          </button>
        </div>
      </form>
    </div>
  );
}}

export default {name}FormPage;
"""

        return GeneratedFile(
            path=f"src/pages/{var_name}/{name}FormPage.tsx",
            content=content,
            file_type="page",
        )

    # ==================== DETAIL PAGE GENERATION ====================

    def _generate_detail_page(self, entity: Dict[str, Any]) -> GeneratedFile:
        """Gera página de detalhes."""
        name = self._to_pascal_case(entity["name"])
        var_name = self._to_camel_case(entity["name"])
        kebab_name = self._to_kebab_case(entity["name"])
        fields = entity.get("fields", [])

        # Campos de exibição
        field_displays = []
        for fld in fields:
            field_name = self._to_camel_case(fld["name"])
            label = self._to_pascal_case(fld["name"])
            fld_type = fld.get("type", "string")

            if fld_type == "boolean":
                field_displays.append(f"""        <div className="detail-field">
          <span className="label">{label}:</span>
          <span className="value">{{item.{field_name} ? 'Sim' : 'Não'}}</span>
        </div>""")
            else:
                field_displays.append(f"""        <div className="detail-field">
          <span className="label">{label}:</span>
          <span className="value">{{item.{field_name}}}</span>
        </div>""")

        fields_str = "\n".join(field_displays)

        content = f"""/**
 * Página de detalhes de {name}
 */

import {{ Link, useParams, useNavigate }} from 'react-router-dom';
import {{ use{name}, useDelete{name} }} from '../../hooks';

export function {name}DetailPage() {{
  const {{ id }} = useParams<{{ id: string }}>();
  const navigate = useNavigate();
  const {{ data: item, isLoading, error }} = use{name}(id);
  const deleteMutation = useDelete{name}();

  const handleDelete = async () => {{
    if (window.confirm('Tem certeza que deseja excluir?')) {{
      try {{
        await deleteMutation.mutateAsync(id!);
        navigate('/{kebab_name}');
      }} catch (error) {{
        console.error('Erro ao excluir:', error);
      }}
    }}
  }};

  if (isLoading) {{
    return <div className="loading">Carregando...</div>;
  }}

  if (error || !item) {{
    return <div className="error">Erro ao carregar dados</div>;
  }}

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Detalhes de {name}</h1>
        <div className="header-actions">
          <Link to="/{kebab_name}" className="btn btn-secondary">
            Voltar
          </Link>
          <Link to={{`/{kebab_name}/${{id}}/edit`}} className="btn btn-primary">
            Editar
          </Link>
          <button
            onClick={{handleDelete}}
            className="btn btn-danger"
            disabled={{deleteMutation.isPending}}
          >
            Excluir
          </button>
        </div>
      </div>

      <div className="detail-card">
{fields_str}

        <div className="detail-field">
          <span className="label">Criado em:</span>
          <span className="value">{{item.createdAt}}</span>
        </div>
        <div className="detail-field">
          <span className="label">Atualizado em:</span>
          <span className="value">{{item.updatedAt}}</span>
        </div>
      </div>
    </div>
  );
}}

export default {name}DetailPage;
"""

        return GeneratedFile(
            path=f"src/pages/{var_name}/{name}DetailPage.tsx",
            content=content,
            file_type="page",
        )

    # ==================== ROUTER GENERATION ====================

    def _generate_router(self, entities: List[Dict[str, Any]]) -> GeneratedFile:
        """Gera configuração de rotas."""
        route_imports = []
        route_defs = []

        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            var_name = self._to_camel_case(entity["name"])
            kebab_name = self._to_kebab_case(entity["name"])

            route_imports.append(
                f"import {{ {name}ListPage, {name}FormPage, {name}DetailPage }} from './pages/{var_name}';"
            )

            route_defs.append(f"""  // Rotas de {name}
  {{ path: '/{kebab_name}', element: <{name}ListPage /> }},
  {{ path: '/{kebab_name}/new', element: <{name}FormPage /> }},
  {{ path: '/{kebab_name}/:id', element: <{name}DetailPage /> }},
  {{ path: '/{kebab_name}/:id/edit', element: <{name}FormPage /> }},""")

        # Index exports para cada entidade
        index_exports = []
        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            var_name = self._to_camel_case(entity["name"])
            index_exports.append(f"export {{ {name}ListPage }} from './{name}ListPage';")
            index_exports.append(f"export {{ {name}FormPage }} from './{name}FormPage';")
            index_exports.append(f"export {{ {name}DetailPage }} from './{name}DetailPage';")

            # Criar index.ts para cada pasta de entidade
            # (Será gerado separadamente)

        content = f"""/**
 * Configuração de rotas gerada automaticamente.
 * NÃO EDITE MANUALMENTE - será sobrescrito na próxima geração.
 */

import type {{ RouteObject }} from 'react-router-dom';

{chr(10).join(route_imports)}

export const routes: RouteObject[] = [
{chr(10).join(route_defs)}
];

export default routes;
"""

        return GeneratedFile(
            path="src/routes.tsx",
            content=content,
            file_type="config",
        )

    # ==================== APP GENERATION ====================

    def _generate_app(self, entities: List[Dict[str, Any]]) -> GeneratedFile:
        """Gera App.tsx atualizado."""
        nav_links = []
        for entity in entities:
            name = self._to_pascal_case(entity["name"])
            kebab_name = self._to_kebab_case(entity["name"])
            nav_links.append(f'          <NavLink to="/{kebab_name}">{name}</NavLink>')

        content = f"""/**
 * Componente principal da aplicação.
 * Gerado automaticamente pelo Bazari Engine.
 */

import {{ BrowserRouter, Routes, Route, NavLink }} from 'react-router-dom';
import {{ QueryClient, QueryClientProvider }} from '@tanstack/react-query';
import routes from './routes';

const queryClient = new QueryClient({{
  defaultOptions: {{
    queries: {{
      staleTime: 5 * 60 * 1000, // 5 minutos
      retry: 1,
    }},
  }},
}});

function App() {{
  return (
    <QueryClientProvider client={{queryClient}}>
      <BrowserRouter>
        <div className="app">
          <nav className="main-nav">
            <NavLink to="/" className="nav-brand">Home</NavLink>
            <div className="nav-links">
{chr(10).join(nav_links)}
            </div>
          </nav>

          <main className="main-content">
            <Routes>
              <Route path="/" element={{<HomePage />}} />
              {{routes.map((route, index) => (
                <Route key={{index}} path={{route.path}} element={{route.element}} />
              ))}}
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}}

function HomePage() {{
  return (
    <div className="page-container">
      <h1>Bem-vindo</h1>
      <p>Selecione uma opção no menu.</p>
    </div>
  );
}}

export default App;
"""

        return GeneratedFile(
            path="src/App.tsx",
            content=content,
            file_type="config",
        )


def compile_frontend(
    ir: Dict[str, Any],
    oas: Dict[str, Any],
    project_root: str = "/home/bazari/generated",
) -> FrontendOutput:
    """Função de conveniência para compilar frontend.

    Args:
        ir: Intermediate Representation
        oas: OpenAPI Specification
        project_root: Diretório raiz do projeto

    Returns:
        FrontendOutput com todos os arquivos gerados
    """
    compiler = FrontendCompiler(project_root)
    return compiler.compile(ir, oas)
