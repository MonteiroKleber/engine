"""Fix Patch Generator - Gera patches focais mínimos para correção de erros.

Entrada:
- error_class: Tipo do erro classificado
- failing_file: Arquivo que falhou
- context: Trecho do erro + IR + OAS

Saída:
- 1 patch mínimo (add import, fix type, adjust annotation, align DTO, adjust TS client)

PROIBIDO:
- Reescrever arquivo inteiro
- Criar novas entidades
- Mudar contrato
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fix_loop.error_classifier import BuildErrorType, ClassifiedError, BuildStep


@dataclass
class PatchContext:
    """Contexto para geração de patch."""

    error: ClassifiedError
    file_content: str
    ir: Optional[Dict[str, Any]] = None
    oas: Optional[Dict[str, Any]] = None
    error_snippet: str = ""

    @property
    def file_lines(self) -> List[str]:
        """Retorna conteúdo como lista de linhas."""
        return self.file_content.split("\n")

    @property
    def line_count(self) -> int:
        """Número de linhas do arquivo."""
        return len(self.file_lines)


@dataclass
class FocalPatch:
    """Um patch focal mínimo."""

    operation: str  # "insert_line", "replace_line", "modify_region"
    file_path: str
    content: str
    line_start: int  # 1-based
    line_end: int  # 1-based, inclusive
    description: str
    error_type: BuildErrorType
    lines_changed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "operation": self.operation,
            "file_path": self.file_path,
            "content": self.content,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "error_type": self.error_type.value,
            "lines_changed": self.lines_changed,
        }

    def to_patch_dict(self) -> Dict[str, Any]:
        """Converte para formato do PatchEngine."""
        return {
            "operation": "modify",
            "file_path": self.file_path,
            "content": self.content,
        }


class FixPatchGenerator:
    """Gerador de patches focais mínimos.

    Gera patches pequenos e específicos para corrigir erros de build,
    sem reescrever arquivos inteiros ou modificar contratos.

    Attributes:
        project: Nome do projeto
        generated_root: Diretório raiz dos projetos gerados
        max_lines_changed: Máximo de linhas que um patch pode modificar
    """

    # Limite de linhas modificadas por patch
    MAX_LINES_CHANGED = 10

    # Mapeamento de imports Java comuns
    JAVA_IMPORTS: Dict[str, str] = {
        # Spring Web
        "ResponseEntity": "org.springframework.http.ResponseEntity",
        "RequestBody": "org.springframework.web.bind.annotation.RequestBody",
        "PathVariable": "org.springframework.web.bind.annotation.PathVariable",
        "RequestParam": "org.springframework.web.bind.annotation.RequestParam",
        "GetMapping": "org.springframework.web.bind.annotation.GetMapping",
        "PostMapping": "org.springframework.web.bind.annotation.PostMapping",
        "PutMapping": "org.springframework.web.bind.annotation.PutMapping",
        "DeleteMapping": "org.springframework.web.bind.annotation.DeleteMapping",
        "RequestMapping": "org.springframework.web.bind.annotation.RequestMapping",
        "RestController": "org.springframework.web.bind.annotation.RestController",
        "CrossOrigin": "org.springframework.web.bind.annotation.CrossOrigin",
        # Spring Core
        "Service": "org.springframework.stereotype.Service",
        "Repository": "org.springframework.stereotype.Repository",
        "Component": "org.springframework.stereotype.Component",
        "Autowired": "org.springframework.beans.factory.annotation.Autowired",
        "Value": "org.springframework.beans.factory.annotation.Value",
        # Spring Data
        "JpaRepository": "org.springframework.data.jpa.repository.JpaRepository",
        "Query": "org.springframework.data.jpa.repository.Query",
        "Param": "org.springframework.data.repository.query.Param",
        # JPA/Persistence
        "Entity": "javax.persistence.Entity",
        "Table": "javax.persistence.Table",
        "Id": "javax.persistence.Id",
        "GeneratedValue": "javax.persistence.GeneratedValue",
        "GenerationType": "javax.persistence.GenerationType",
        "Column": "javax.persistence.Column",
        "ManyToOne": "javax.persistence.ManyToOne",
        "OneToMany": "javax.persistence.OneToMany",
        "JoinColumn": "javax.persistence.JoinColumn",
        "Temporal": "javax.persistence.Temporal",
        "TemporalType": "javax.persistence.TemporalType",
        # Jakarta Persistence (newer)
        "jakarta.persistence.Entity": "jakarta.persistence.Entity",
        # Validation
        "Valid": "javax.validation.Valid",
        "NotNull": "javax.validation.constraints.NotNull",
        "NotBlank": "javax.validation.constraints.NotBlank",
        "Size": "javax.validation.constraints.Size",
        "Email": "javax.validation.constraints.Email",
        # Java Utils
        "List": "java.util.List",
        "ArrayList": "java.util.ArrayList",
        "Map": "java.util.Map",
        "HashMap": "java.util.HashMap",
        "Set": "java.util.Set",
        "HashSet": "java.util.HashSet",
        "Optional": "java.util.Optional",
        "Stream": "java.util.stream.Stream",
        "Collectors": "java.util.stream.Collectors",
        # Java Time
        "LocalDate": "java.time.LocalDate",
        "LocalDateTime": "java.time.LocalDateTime",
        "LocalTime": "java.time.LocalTime",
        "ZonedDateTime": "java.time.ZonedDateTime",
        "Instant": "java.time.Instant",
        # Java Math
        "BigDecimal": "java.math.BigDecimal",
        "BigInteger": "java.math.BigInteger",
        # Lombok
        "Data": "lombok.Data",
        "Getter": "lombok.Getter",
        "Setter": "lombok.Setter",
        "NoArgsConstructor": "lombok.NoArgsConstructor",
        "AllArgsConstructor": "lombok.AllArgsConstructor",
        "Builder": "lombok.Builder",
        "Slf4j": "lombok.extern.slf4j.Slf4j",
    }

    # Mapeamento de imports TypeScript comuns
    TS_IMPORTS: Dict[str, Tuple[str, str]] = {
        # React
        "React": ("react", "default"),
        "useState": ("react", "named"),
        "useEffect": ("react", "named"),
        "useContext": ("react", "named"),
        "useCallback": ("react", "named"),
        "useMemo": ("react", "named"),
        "useRef": ("react", "named"),
        "FC": ("react", "named"),
        "ReactNode": ("react", "named"),
        # React Router
        "useNavigate": ("react-router-dom", "named"),
        "useParams": ("react-router-dom", "named"),
        "Link": ("react-router-dom", "named"),
        "Route": ("react-router-dom", "named"),
        "Routes": ("react-router-dom", "named"),
        # React Query
        "useQuery": ("@tanstack/react-query", "named"),
        "useMutation": ("@tanstack/react-query", "named"),
        "QueryClient": ("@tanstack/react-query", "named"),
        # Axios
        "axios": ("axios", "default"),
        "AxiosResponse": ("axios", "named"),
        "AxiosError": ("axios", "named"),
    }

    def __init__(
        self,
        project: str,
        generated_root: str = "/home/bazari/generated",
    ) -> None:
        """Inicializa o gerador.

        Args:
            project: Nome do projeto
            generated_root: Diretório raiz dos projetos gerados
        """
        self.project = project
        self.generated_root = Path(generated_root)
        self.project_root = self.generated_root / project

    def generate(
        self,
        error: ClassifiedError,
        ir: Optional[Dict[str, Any]] = None,
        oas: Optional[Dict[str, Any]] = None,
    ) -> Optional[FocalPatch]:
        """Gera um patch focal para o erro.

        Args:
            error: Erro classificado
            ir: IR do projeto (opcional)
            oas: OpenAPI spec (opcional)

        Returns:
            FocalPatch ou None se não pode gerar
        """
        if not error.file_path:
            return None

        # Ler arquivo
        file_path = self.project_root / error.file_path
        if not file_path.exists():
            return None

        try:
            file_content = file_path.read_text()
        except Exception:
            return None

        # Criar contexto
        context = PatchContext(
            error=error,
            file_content=file_content,
            ir=ir,
            oas=oas,
            error_snippet=error.raw_output[:500] if error.raw_output else "",
        )

        # Dispatch para estratégia de patch
        return self._generate_for_type(context)

    def _generate_for_type(self, context: PatchContext) -> Optional[FocalPatch]:
        """Gera patch baseado no tipo de erro."""
        strategy_map = {
            # Java
            BuildErrorType.JAVA_MISSING_IMPORT: self._fix_java_import,
            BuildErrorType.JAVA_TYPE_MISMATCH: self._fix_java_type,
            BuildErrorType.JAVA_MISSING_ANNOTATION: self._fix_java_annotation,
            BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED: self._fix_java_method,
            BuildErrorType.JAVA_SECURITY_CONFIG_ERROR: self._fix_java_security,
            # TypeScript
            BuildErrorType.TS_MISSING_IMPORT: self._fix_ts_import,
            BuildErrorType.TS_TYPE_ERROR: self._fix_ts_type,
            BuildErrorType.TS_MISSING_EXPORT: self._fix_ts_export,
            BuildErrorType.TS_PROPERTY_NOT_EXIST: self._fix_ts_property,
            BuildErrorType.TS_JSX_ERROR: self._fix_ts_jsx,
            # SQL
            BuildErrorType.SQL_SYNTAX_ERROR: self._fix_sql_syntax,
            # API
            BuildErrorType.API_CLIENT_MISMATCH: self._fix_api_mismatch,
        }

        strategy = strategy_map.get(context.error.error_type)
        if strategy:
            return strategy(context)

        return None

    # ==================== JAVA FIXES ====================

    def _fix_java_import(self, context: PatchContext) -> Optional[FocalPatch]:
        """Adiciona import Java faltando."""
        error = context.error
        symbol = error.symbol

        if not symbol:
            # Tentar extrair do erro
            symbol = self._extract_missing_symbol(error.message)

        if not symbol or symbol not in self.JAVA_IMPORTS:
            return None

        full_import = self.JAVA_IMPORTS[symbol]
        import_line = f"import {full_import};"

        # Verificar se já existe
        if import_line in context.file_content:
            return None

        # Encontrar posição para inserir (após package, antes da classe)
        insert_pos = self._find_java_import_position(context.file_lines)

        # Gerar novo conteúdo
        lines = context.file_lines.copy()
        lines.insert(insert_pos, import_line)
        new_content = "\n".join(lines)

        return FocalPatch(
            operation="insert_line",
            file_path=error.file_path,
            content=new_content,
            line_start=insert_pos + 1,
            line_end=insert_pos + 1,
            description=f"Add import {full_import}",
            error_type=error.error_type,
            lines_changed=1,
        )

    def _find_java_import_position(self, lines: List[str]) -> int:
        """Encontra posição para inserir import Java."""
        last_import = -1
        package_line = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("package "):
                package_line = i
            elif stripped.startswith("import "):
                last_import = i

        # Se há imports, inserir após o último
        if last_import >= 0:
            return last_import + 1

        # Senão, inserir após package (com linha em branco)
        if package_line >= 0:
            return package_line + 2

        # Sem package nem imports, inserir no início
        return 0

    def _fix_java_type(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige type mismatch em Java."""
        error = context.error

        if not error.line_number:
            return None

        # Estratégia: adicionar cast ou wrapper
        # Implementação básica - pode ser expandida
        line_idx = error.line_number - 1
        lines = context.file_lines

        if line_idx >= len(lines):
            return None

        original_line = lines[line_idx]

        # Detectar tipo de mismatch e sugerir correção
        # Por exemplo: Long.valueOf() para String -> Long
        if "String" in error.message and "Long" in error.message:
            # Tentar adicionar Long.parseLong()
            new_line = self._wrap_with_parse(original_line, "Long.parseLong")
            if new_line != original_line:
                lines[line_idx] = new_line
                return FocalPatch(
                    operation="replace_line",
                    file_path=error.file_path,
                    content="\n".join(lines),
                    line_start=error.line_number,
                    line_end=error.line_number,
                    description="Add type conversion",
                    error_type=error.error_type,
                    lines_changed=1,
                )

        return None

    def _wrap_with_parse(self, line: str, wrapper: str) -> str:
        """Tenta envolver uma expressão com parser."""
        # Estratégia simplificada
        # Uma implementação real usaria AST
        return line

    def _fix_java_annotation(self, context: PatchContext) -> Optional[FocalPatch]:
        """Adiciona annotation faltando em Java."""
        error = context.error
        symbol = error.symbol

        if not symbol or not error.line_number:
            return None

        # Mapeamento de annotations comuns
        annotation_map = {
            "Entity": "@Entity",
            "Table": "@Table",
            "Id": "@Id",
            "GeneratedValue": "@GeneratedValue(strategy = GenerationType.IDENTITY)",
            "Column": "@Column",
            "Service": "@Service",
            "Repository": "@Repository",
            "RestController": "@RestController",
            "Autowired": "@Autowired",
        }

        if symbol not in annotation_map:
            return None

        annotation = annotation_map[symbol]
        lines = context.file_lines.copy()

        # Inserir annotation antes da linha do erro
        insert_pos = error.line_number - 1
        if insert_pos > 0:
            # Adicionar indentação da linha atual
            current_indent = len(lines[insert_pos]) - len(lines[insert_pos].lstrip())
            annotation_line = " " * current_indent + annotation

            lines.insert(insert_pos, annotation_line)

            return FocalPatch(
                operation="insert_line",
                file_path=error.file_path,
                content="\n".join(lines),
                line_start=error.line_number,
                line_end=error.line_number,
                description=f"Add annotation {annotation}",
                error_type=error.error_type,
                lines_changed=1,
            )

        return None

    def _fix_java_method(self, context: PatchContext) -> Optional[FocalPatch]:
        """Adiciona stub de método não implementado."""
        error = context.error

        # Esta é uma correção complexa - retornar None por segurança
        # para não gerar código incorreto
        return None

    def _fix_java_security(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige configuração de segurança Spring."""
        # Correção complexa - requer conhecimento do contexto
        return None

    # ==================== TYPESCRIPT FIXES ====================

    def _fix_ts_import(self, context: PatchContext) -> Optional[FocalPatch]:
        """Adiciona import TypeScript faltando."""
        error = context.error
        symbol = error.symbol

        if not symbol:
            # Tentar extrair do erro
            symbol = self._extract_ts_module(error.message)

        if not symbol:
            return None

        # Verificar se é módulo conhecido
        if symbol in self.TS_IMPORTS:
            module, import_type = self.TS_IMPORTS[symbol]
            if import_type == "default":
                import_line = f"import {symbol} from '{module}';"
            else:
                import_line = f"import {{ {symbol} }} from '{module}';"
        else:
            # Import genérico
            import_line = f"import {{ {symbol} }} from './{symbol}';"

        # Verificar se já existe
        if import_line in context.file_content:
            return None

        # Inserir no início do arquivo (após outros imports se houver)
        insert_pos = self._find_ts_import_position(context.file_lines)
        lines = context.file_lines.copy()
        lines.insert(insert_pos, import_line)

        return FocalPatch(
            operation="insert_line",
            file_path=error.file_path,
            content="\n".join(lines),
            line_start=insert_pos + 1,
            line_end=insert_pos + 1,
            description=f"Add import for {symbol}",
            error_type=error.error_type,
            lines_changed=1,
        )

    def _find_ts_import_position(self, lines: List[str]) -> int:
        """Encontra posição para inserir import TypeScript."""
        last_import = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import "):
                last_import = i + 1

        return last_import

    def _extract_ts_module(self, message: str) -> Optional[str]:
        """Extrai nome do módulo de mensagem de erro."""
        # Pattern: Cannot find module 'xxx'
        match = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", message)
        if match:
            return match.group(1)

        # Pattern: Module '"xxx"' has no exported member
        match = re.search(r"Module ['\"]([^'\"]+)['\"]", message)
        if match:
            return match.group(1)

        return None

    def _fix_ts_type(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige erro de tipo TypeScript."""
        error = context.error

        if not error.line_number:
            return None

        line_idx = error.line_number - 1
        lines = context.file_lines

        if line_idx >= len(lines):
            return None

        original_line = lines[line_idx]

        # Estratégia: adicionar type assertion (as any) como último recurso
        # Isso não é ideal mas pode desbloquear o build
        if " as " not in original_line and "any" not in original_line:
            # Tentar adicionar 'as any' em atribuições
            if "=" in original_line and "==" not in original_line:
                # Encontrar o valor após o =
                parts = original_line.split("=", 1)
                if len(parts) == 2:
                    value_part = parts[1].rstrip(";").strip()
                    new_line = f"{parts[0]}= ({value_part}) as any;"

                    lines[line_idx] = new_line
                    return FocalPatch(
                        operation="replace_line",
                        file_path=error.file_path,
                        content="\n".join(lines),
                        line_start=error.line_number,
                        line_end=error.line_number,
                        description="Add type assertion",
                        error_type=error.error_type,
                        lines_changed=1,
                    )

        return None

    def _fix_ts_export(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige export TypeScript faltando."""
        error = context.error
        symbol = error.symbol

        if not symbol:
            return None

        # Verificar se o símbolo existe no arquivo mas não está exportado
        if f"const {symbol}" in context.file_content:
            # Adicionar export
            old = f"const {symbol}"
            new = f"export const {symbol}"
            new_content = context.file_content.replace(old, new, 1)

            if new_content != context.file_content:
                return FocalPatch(
                    operation="modify_region",
                    file_path=error.file_path,
                    content=new_content,
                    line_start=1,
                    line_end=context.line_count,
                    description=f"Export {symbol}",
                    error_type=error.error_type,
                    lines_changed=1,
                )

        if f"function {symbol}" in context.file_content:
            old = f"function {symbol}"
            new = f"export function {symbol}"
            new_content = context.file_content.replace(old, new, 1)

            if new_content != context.file_content:
                return FocalPatch(
                    operation="modify_region",
                    file_path=error.file_path,
                    content=new_content,
                    line_start=1,
                    line_end=context.line_count,
                    description=f"Export function {symbol}",
                    error_type=error.error_type,
                    lines_changed=1,
                )

        return None

    def _fix_ts_property(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige propriedade que não existe em tipo TypeScript."""
        # Correção complexa - requer modificar interfaces
        return None

    def _fix_ts_jsx(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige erro de JSX."""
        error = context.error

        if not error.line_number:
            return None

        # Verificar se é tag não fechada
        if "no corresponding closing tag" in error.message.lower():
            symbol = error.symbol
            if symbol:
                line_idx = error.line_number - 1
                lines = context.file_lines

                if line_idx < len(lines):
                    original_line = lines[line_idx]

                    # Adicionar fechamento
                    if f"<{symbol}" in original_line and f"</{symbol}>" not in original_line:
                        if "/>" not in original_line:
                            # Transformar <Tag ...> em <Tag ... />
                            new_line = re.sub(
                                rf"(<{symbol}[^>]*)>",
                                r"\1 />",
                                original_line
                            )

                            if new_line != original_line:
                                lines[line_idx] = new_line
                                return FocalPatch(
                                    operation="replace_line",
                                    file_path=error.file_path,
                                    content="\n".join(lines),
                                    line_start=error.line_number,
                                    line_end=error.line_number,
                                    description=f"Self-close JSX tag {symbol}",
                                    error_type=error.error_type,
                                    lines_changed=1,
                                )

        return None

    # ==================== SQL FIXES ====================

    def _fix_sql_syntax(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige erro de sintaxe SQL."""
        # SQL syntax errors são complexos e arriscados de corrigir automaticamente
        return None

    # ==================== API FIXES ====================

    def _fix_api_mismatch(self, context: PatchContext) -> Optional[FocalPatch]:
        """Corrige mismatch entre cliente e API."""
        error = context.error

        # Usar OAS para alinhar tipos
        if not context.oas:
            return None

        # Implementação dependeria de parsing do OAS
        # e comparação com o código cliente
        return None

    # ==================== HELPERS ====================

    def _extract_missing_symbol(self, message: str) -> Optional[str]:
        """Extrai símbolo faltando de mensagem de erro."""
        # Pattern: cannot find symbol.*class X
        match = re.search(r"class\s+(\w+)", message)
        if match:
            return match.group(1)

        # Pattern: symbol: X
        match = re.search(r"symbol:\s*(\w+)", message)
        if match:
            return match.group(1)

        return None

    def validate_patch_size(self, patch: FocalPatch) -> bool:
        """Valida que o patch é pequeno o suficiente.

        Args:
            patch: Patch a validar

        Returns:
            True se patch é válido (pequeno)
        """
        return patch.lines_changed <= self.MAX_LINES_CHANGED

    def generate_multiple(
        self,
        errors: List[ClassifiedError],
        ir: Optional[Dict[str, Any]] = None,
        oas: Optional[Dict[str, Any]] = None,
        max_patches: int = 3,
    ) -> List[FocalPatch]:
        """Gera patches para múltiplos erros.

        Args:
            errors: Lista de erros classificados
            ir: IR do projeto
            oas: OpenAPI spec
            max_patches: Máximo de patches a gerar

        Returns:
            Lista de patches (até max_patches)
        """
        patches = []

        for error in errors[:max_patches]:
            patch = self.generate(error, ir, oas)
            if patch and self.validate_patch_size(patch):
                patches.append(patch)

        return patches
