"""Build Error Classifier - Taxonomia fechada de erros de build.

Classifica erros de build em tipos fechados para permitir
correção automática via patches.

REGRA: Nada de texto livre. Classificação fechada.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class BuildErrorType(Enum):
    """Tipos fechados de erros de build.

    Cada tipo tem uma estratégia de correção associada.
    """

    # Java/Backend errors
    JAVA_MISSING_IMPORT = "java_missing_import"
    JAVA_METHOD_NOT_IMPLEMENTED = "java_method_not_implemented"
    JAVA_TYPE_MISMATCH = "java_type_mismatch"
    JAVA_SECURITY_CONFIG_ERROR = "java_security_config_error"
    JAVA_MISSING_ANNOTATION = "java_missing_annotation"
    JAVA_MISSING_DEPENDENCY = "java_missing_dependency"

    # SQL/Database errors
    SQL_MIGRATION_ERROR = "sql_migration_error"
    SQL_SYNTAX_ERROR = "sql_syntax_error"

    # TypeScript/Frontend errors
    TS_TYPE_ERROR = "ts_type_error"
    TS_MISSING_EXPORT = "ts_missing_export"
    TS_MISSING_IMPORT = "ts_missing_import"
    TS_PROPERTY_NOT_EXIST = "ts_property_not_exist"
    TS_JSX_ERROR = "ts_jsx_error"

    # API/Integration errors
    API_CLIENT_MISMATCH = "api_client_mismatch"

    # Fallback categories
    UNKNOWN_BUT_PATCHABLE = "unknown_but_patchable"
    FATAL_UNCLASSIFIED = "fatal_unclassified"


class BuildStep(Enum):
    """Etapa do build onde o erro ocorreu."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    DATABASE = "database"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """Um erro classificado com contexto."""

    error_type: BuildErrorType
    step: BuildStep
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column: Optional[int] = None
    symbol: Optional[str] = None  # Classe, método, variável faltando
    suggestion: Optional[str] = None  # Sugestão de correção extraída
    raw_output: str = ""
    confidence: float = 1.0  # 0.0-1.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "error_type": self.error_type.value,
            "step": self.step.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "symbol": self.symbol,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class ClassificationResult:
    """Resultado da classificação de erros."""

    errors: List[ClassifiedError] = field(default_factory=list)
    total_count: int = 0
    patchable_count: int = 0
    fatal_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "errors": [e.to_dict() for e in self.errors],
            "total_count": self.total_count,
            "patchable_count": self.patchable_count,
            "fatal_count": self.fatal_count,
        }

    @property
    def is_patchable(self) -> bool:
        """Retorna True se todos os erros são patcháveis."""
        return self.fatal_count == 0 and self.total_count > 0

    @property
    def has_errors(self) -> bool:
        """Retorna True se há erros."""
        return self.total_count > 0


class BuildErrorClassifier:
    """Classificador de erros de build.

    Recebe output de build (stderr, stdout) e classifica
    cada erro em um tipo fechado (BuildErrorType).

    Attributes:
        patterns: Dicionário de padrões regex para cada tipo de erro
    """

    # Padrões Java/Maven
    JAVA_PATTERNS: List[Tuple[str, BuildErrorType, str]] = [
        # Missing import
        (
            r"cannot find symbol[\s\S]*?class (\w+)",
            BuildErrorType.JAVA_MISSING_IMPORT,
            "symbol"
        ),
        (
            r"cannot find symbol",
            BuildErrorType.JAVA_MISSING_IMPORT,
            None
        ),
        (
            r"package (\S+) does not exist",
            BuildErrorType.JAVA_MISSING_IMPORT,
            "symbol"
        ),
        (
            r"cannot access (\w+)",
            BuildErrorType.JAVA_MISSING_IMPORT,
            "symbol"
        ),

        # Method not implemented
        (
            r"method (\w+)\([^)]*\) is not implemented",
            BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED,
            "symbol"
        ),
        (
            r"(\w+) is not abstract and does not override abstract method",
            BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED,
            "symbol"
        ),
        (
            r"class (\w+) must implement the inherited abstract method",
            BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED,
            "symbol"
        ),

        # Type mismatch
        (
            r"incompatible types:.*found:\s*(\S+).*required:\s*(\S+)",
            BuildErrorType.JAVA_TYPE_MISMATCH,
            "symbol"
        ),
        (
            r"cannot convert from (\S+) to (\S+)",
            BuildErrorType.JAVA_TYPE_MISMATCH,
            "symbol"
        ),
        (
            r"Type mismatch: cannot convert from (\S+) to (\S+)",
            BuildErrorType.JAVA_TYPE_MISMATCH,
            "symbol"
        ),

        # Security config
        (
            r"No qualifying bean of type.*SecurityFilterChain",
            BuildErrorType.JAVA_SECURITY_CONFIG_ERROR,
            "symbol"
        ),
        (
            r"WebSecurityConfigurerAdapter.*deprecated",
            BuildErrorType.JAVA_SECURITY_CONFIG_ERROR,
            "suggestion"
        ),
        (
            r"http\.authorizeRequests\(\).*deprecated",
            BuildErrorType.JAVA_SECURITY_CONFIG_ERROR,
            "suggestion"
        ),

        # Missing annotation
        (
            r"@(\w+) annotation is required",
            BuildErrorType.JAVA_MISSING_ANNOTATION,
            "symbol"
        ),
        (
            r"Not a managed type: class (\S+)",
            BuildErrorType.JAVA_MISSING_ANNOTATION,
            "symbol"
        ),

        # Missing dependency
        (
            r"Could not resolve dependencies",
            BuildErrorType.JAVA_MISSING_DEPENDENCY,
            None
        ),
        (
            r"Could not find artifact (\S+)",
            BuildErrorType.JAVA_MISSING_DEPENDENCY,
            "symbol"
        ),
    ]

    # Padrões SQL/Flyway
    SQL_PATTERNS: List[Tuple[str, BuildErrorType, str]] = [
        (
            r"Migration.*failed",
            BuildErrorType.SQL_MIGRATION_ERROR,
            None
        ),
        (
            r"FlywayException",
            BuildErrorType.SQL_MIGRATION_ERROR,
            None
        ),
        (
            r"syntax error at or near",
            BuildErrorType.SQL_SYNTAX_ERROR,
            None
        ),
        (
            r"ERROR:\s+syntax error",
            BuildErrorType.SQL_SYNTAX_ERROR,
            None
        ),
        (
            r"relation \"(\w+)\" already exists",
            BuildErrorType.SQL_MIGRATION_ERROR,
            "symbol"
        ),
        (
            r"relation \"(\w+)\" does not exist",
            BuildErrorType.SQL_MIGRATION_ERROR,
            "symbol"
        ),
    ]

    # Padrões TypeScript/npm
    TS_PATTERNS: List[Tuple[str, BuildErrorType, str]] = [
        # Type errors
        (
            r"TS\d+:.*Type '([^']+)' is not assignable to type '([^']+)'",
            BuildErrorType.TS_TYPE_ERROR,
            "symbol"
        ),
        (
            r"error TS\d+:",
            BuildErrorType.TS_TYPE_ERROR,
            None
        ),
        (
            r"Argument of type '([^']+)' is not assignable",
            BuildErrorType.TS_TYPE_ERROR,
            "symbol"
        ),

        # Missing export
        (
            r"has no exported member '(\w+)'",
            BuildErrorType.TS_MISSING_EXPORT,
            "symbol"
        ),
        (
            r"Module '\"([^\"]+)\"' has no exported member",
            BuildErrorType.TS_MISSING_EXPORT,
            "symbol"
        ),
        (
            r"export '(\w+)' was not found",
            BuildErrorType.TS_MISSING_EXPORT,
            "symbol"
        ),

        # Missing import
        (
            r"Cannot find module '([^']+)'",
            BuildErrorType.TS_MISSING_IMPORT,
            "symbol"
        ),
        (
            r"Module not found.*'([^']+)'",
            BuildErrorType.TS_MISSING_IMPORT,
            "symbol"
        ),

        # Property not exist
        (
            r"Property '(\w+)' does not exist on type '([^']+)'",
            BuildErrorType.TS_PROPERTY_NOT_EXIST,
            "symbol"
        ),
        (
            r"Object literal may only specify known properties",
            BuildErrorType.TS_PROPERTY_NOT_EXIST,
            None
        ),

        # JSX errors
        (
            r"JSX element '(\w+)' has no corresponding closing tag",
            BuildErrorType.TS_JSX_ERROR,
            "symbol"
        ),
        (
            r"'(\w+)' cannot be used as a JSX component",
            BuildErrorType.TS_JSX_ERROR,
            "symbol"
        ),
        (
            r"Type '.*' is not a valid JSX element",
            BuildErrorType.TS_JSX_ERROR,
            None
        ),
    ]

    # Padrões de API/Cliente
    API_PATTERNS: List[Tuple[str, BuildErrorType, str]] = [
        (
            r"API endpoint '([^']+)' not found",
            BuildErrorType.API_CLIENT_MISMATCH,
            "symbol"
        ),
        (
            r"Expected response type.*but got",
            BuildErrorType.API_CLIENT_MISMATCH,
            None
        ),
        (
            r"openapi-generator.*error",
            BuildErrorType.API_CLIENT_MISMATCH,
            None
        ),
        (
            r"swagger.*validation failed",
            BuildErrorType.API_CLIENT_MISMATCH,
            None
        ),
    ]

    # Padrões fatais (não patcháveis)
    FATAL_PATTERNS: List[str] = [
        r"Out of memory",
        r"FATAL ERROR",
        r"Killed",
        r"Segmentation fault",
        r"Permission denied",
        r"disk space",
        r"No space left on device",
        r"Connection refused",
        r"Network unreachable",
    ]

    def __init__(self) -> None:
        """Inicializa o classificador."""
        # Compilar padrões para melhor performance
        self._java_compiled = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), t, g)
            for p, t, g in self.JAVA_PATTERNS
        ]
        self._sql_compiled = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), t, g)
            for p, t, g in self.SQL_PATTERNS
        ]
        self._ts_compiled = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), t, g)
            for p, t, g in self.TS_PATTERNS
        ]
        self._api_compiled = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), t, g)
            for p, t, g in self.API_PATTERNS
        ]
        self._fatal_compiled = [
            re.compile(p, re.IGNORECASE)
            for p in self.FATAL_PATTERNS
        ]

        # Padrão para extrair localização do erro
        self._location_pattern = re.compile(
            r"(?:^|\s)([^\s:]+\.(java|ts|tsx|sql)):(\d+)(?::(\d+))?",
            re.MULTILINE
        )

    def classify(
        self,
        stderr: str,
        stdout: str,
        exit_code: int,
        step: str,
    ) -> ClassificationResult:
        """Classifica erros de build.

        Args:
            stderr: Saída de erro do build
            stdout: Saída padrão do build
            exit_code: Código de saída do processo
            step: Etapa do build ("backend", "frontend", "database")

        Returns:
            ClassificationResult com erros classificados
        """
        result = ClassificationResult()

        # Se exit_code é 0, não há erros
        if exit_code == 0:
            return result

        # Combinar outputs para análise
        combined = f"{stdout}\n{stderr}"

        # Determinar step
        build_step = self._parse_step(step)

        # Verificar erros fatais primeiro
        for pattern in self._fatal_compiled:
            if pattern.search(combined):
                error = ClassifiedError(
                    error_type=BuildErrorType.FATAL_UNCLASSIFIED,
                    step=build_step,
                    message=f"Fatal error detected: {pattern.pattern}",
                    raw_output=combined[:500],
                    confidence=1.0,
                )
                result.errors.append(error)
                result.total_count += 1
                result.fatal_count += 1
                return result  # Fatal é terminal

        # Classificar por tipo de step
        if build_step == BuildStep.BACKEND:
            self._classify_backend(combined, result, build_step)
        elif build_step == BuildStep.FRONTEND:
            self._classify_frontend(combined, result, build_step)
        elif build_step == BuildStep.DATABASE:
            self._classify_database(combined, result, build_step)
        else:
            # Tentar todos os padrões
            self._classify_backend(combined, result, build_step)
            self._classify_frontend(combined, result, build_step)
            self._classify_database(combined, result, build_step)

        # Se não classificou nada mas tem exit_code != 0
        if result.total_count == 0 and exit_code != 0:
            # Verificar se parece patchável
            if self._looks_patchable(combined):
                error = ClassifiedError(
                    error_type=BuildErrorType.UNKNOWN_BUT_PATCHABLE,
                    step=build_step,
                    message="Unknown error but potentially patchable",
                    raw_output=combined[:500],
                    confidence=0.5,
                )
                result.errors.append(error)
                result.total_count += 1
                result.patchable_count += 1
            elif build_step in (BuildStep.BACKEND, BuildStep.FRONTEND):
                # Para steps conhecidos (BACKEND/FRONTEND), dar chance ao Fix Loop
                # em vez de abortar imediatamente como FATAL
                # Justificativa: MAX_FIX_ATTEMPTS=3, patches limitados, regras absolutas
                # Melhor tentar e falhar do que abortar sem tentar
                error = ClassifiedError(
                    error_type=BuildErrorType.UNKNOWN_BUT_PATCHABLE,
                    step=build_step,
                    message="Unknown build error - attempting fix",
                    raw_output=combined[:500],
                    confidence=0.3,  # Baixa confiança
                )
                result.errors.append(error)
                result.total_count += 1
                result.patchable_count += 1
            else:
                # Step desconhecido ou erro explicitamente perigoso → FATAL
                error = ClassifiedError(
                    error_type=BuildErrorType.FATAL_UNCLASSIFIED,
                    step=build_step,
                    message="Unclassified error",
                    raw_output=combined[:500],
                    confidence=0.3,
                )
                result.errors.append(error)
                result.total_count += 1
                result.fatal_count += 1

        return result

    def _parse_step(self, step: str) -> BuildStep:
        """Converte string para BuildStep."""
        step_lower = step.lower()
        if step_lower in ("backend", "java", "maven", "mvn"):
            return BuildStep.BACKEND
        elif step_lower in ("frontend", "typescript", "npm", "react", "vite"):
            return BuildStep.FRONTEND
        elif step_lower in ("database", "db", "sql", "flyway", "migration"):
            return BuildStep.DATABASE
        return BuildStep.UNKNOWN

    def _classify_backend(
        self,
        output: str,
        result: ClassificationResult,
        step: BuildStep,
    ) -> None:
        """Classifica erros de backend (Java/Maven)."""
        for pattern, error_type, group_name in self._java_compiled:
            for match in pattern.finditer(output):
                error = self._create_error(
                    error_type, step, match, output, group_name
                )
                result.errors.append(error)
                result.total_count += 1
                if error_type != BuildErrorType.FATAL_UNCLASSIFIED:
                    result.patchable_count += 1

    def _classify_frontend(
        self,
        output: str,
        result: ClassificationResult,
        step: BuildStep,
    ) -> None:
        """Classifica erros de frontend (TypeScript/npm)."""
        for pattern, error_type, group_name in self._ts_compiled:
            for match in pattern.finditer(output):
                error = self._create_error(
                    error_type, step, match, output, group_name
                )
                result.errors.append(error)
                result.total_count += 1
                if error_type != BuildErrorType.FATAL_UNCLASSIFIED:
                    result.patchable_count += 1

        # API patterns também se aplicam ao frontend
        for pattern, error_type, group_name in self._api_compiled:
            for match in pattern.finditer(output):
                error = self._create_error(
                    error_type, step, match, output, group_name
                )
                result.errors.append(error)
                result.total_count += 1
                result.patchable_count += 1

    def _classify_database(
        self,
        output: str,
        result: ClassificationResult,
        step: BuildStep,
    ) -> None:
        """Classifica erros de database (SQL/Flyway)."""
        for pattern, error_type, group_name in self._sql_compiled:
            for match in pattern.finditer(output):
                error = self._create_error(
                    error_type, step, match, output, group_name
                )
                result.errors.append(error)
                result.total_count += 1
                if error_type != BuildErrorType.FATAL_UNCLASSIFIED:
                    result.patchable_count += 1

    def _create_error(
        self,
        error_type: BuildErrorType,
        step: BuildStep,
        match: re.Match,
        output: str,
        group_name: Optional[str],
    ) -> ClassifiedError:
        """Cria um ClassifiedError a partir de um match."""
        # Extrair símbolo se houver
        symbol = None
        if group_name == "symbol" and match.groups():
            symbol = match.group(1)

        # Extrair localização
        file_path, line_number, column = self._extract_location(
            output, match.start()
        )

        return ClassifiedError(
            error_type=error_type,
            step=step,
            message=match.group(0)[:200],  # Limitar tamanho
            file_path=file_path,
            line_number=line_number,
            column=column,
            symbol=symbol,
            raw_output=output[max(0, match.start()-100):match.end()+100],
            confidence=0.9,
        )

    def _extract_location(
        self,
        output: str,
        error_pos: int,
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """Extrai localização do erro (arquivo, linha, coluna)."""
        # Procurar padrão de localização próximo ao erro
        search_start = max(0, error_pos - 200)
        search_end = min(len(output), error_pos + 200)
        search_text = output[search_start:search_end]

        match = self._location_pattern.search(search_text)
        if match:
            file_path = match.group(1)
            line_number = int(match.group(3)) if match.group(3) else None
            column = int(match.group(4)) if match.group(4) else None
            return file_path, line_number, column

        return None, None, None

    def _looks_patchable(self, output: str) -> bool:
        """Verifica se o erro parece ser patchável.

        Heurística: Se contém referência a arquivos de código,
        provavelmente é um erro de código que pode ser corrigido.
        """
        code_file_patterns = [
            r"\.(java|ts|tsx|sql|json|xml|yml|yaml):",
            r"error in",
            r"failed to compile",
            r"compilation error",
            r"syntax error",
            r"type error",
        ]

        for pattern in code_file_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        return False

    def classify_single(
        self,
        error_message: str,
        step: str = "unknown",
    ) -> ClassifiedError:
        """Classifica uma única mensagem de erro.

        Útil para classificar erros individuais extraídos de logs.

        Args:
            error_message: Mensagem de erro
            step: Etapa do build

        Returns:
            ClassifiedError classificado
        """
        result = self.classify(error_message, "", 1, step)
        if result.errors:
            return result.errors[0]

        return ClassifiedError(
            error_type=BuildErrorType.UNKNOWN_BUT_PATCHABLE,
            step=self._parse_step(step),
            message=error_message[:200],
            raw_output=error_message,
            confidence=0.5,
        )
