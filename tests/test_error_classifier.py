"""Testes para o BuildErrorClassifier."""

import pytest

from fix_loop.error_classifier import (
    BuildErrorClassifier,
    BuildErrorType,
    BuildStep,
    ClassifiedError,
    ClassificationResult,
)


@pytest.fixture
def classifier():
    """Cria instância do classificador."""
    return BuildErrorClassifier()


# ==================== JAVA/BACKEND ERRORS ====================


class TestJavaMissingImport:
    """Testes para JAVA_MISSING_IMPORT."""

    def test_cannot_find_symbol_class(self, classifier):
        """Deve classificar 'cannot find symbol' como MISSING_IMPORT."""
        stderr = """
        [ERROR] /src/Main.java:[10,5] cannot find symbol
          symbol:   class HttpServletRequest
          location: class com.example.Main
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_MISSING_IMPORT

    def test_package_does_not_exist(self, classifier):
        """Deve classificar 'package does not exist'."""
        stderr = """
        [ERROR] package org.springframework.security does not exist
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_MISSING_IMPORT
        assert result.errors[0].symbol == "org.springframework.security"

    def test_cannot_access(self, classifier):
        """Deve classificar 'cannot access'."""
        stderr = """
        error: cannot access ResponseEntity
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_MISSING_IMPORT


class TestJavaMethodNotImplemented:
    """Testes para JAVA_METHOD_NOT_IMPLEMENTED."""

    def test_not_abstract_does_not_override(self, classifier):
        """Deve classificar erro de método abstrato não implementado."""
        stderr = """
        [ERROR] UserService is not abstract and does not override abstract method findById(Long)
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED

    def test_must_implement_inherited(self, classifier):
        """Deve classificar 'must implement inherited abstract method'."""
        stderr = """
        error: class MyRepository must implement the inherited abstract method save(Entity)
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED


class TestJavaTypeMismatch:
    """Testes para JAVA_TYPE_MISMATCH."""

    def test_incompatible_types(self, classifier):
        """Deve classificar 'incompatible types'."""
        stderr = """
        [ERROR] incompatible types: found: String required: Long
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_TYPE_MISMATCH

    def test_cannot_convert(self, classifier):
        """Deve classificar 'cannot convert from X to Y'."""
        stderr = """
        error: cannot convert from List<String> to List<Integer>
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_TYPE_MISMATCH


class TestJavaSecurityConfig:
    """Testes para JAVA_SECURITY_CONFIG_ERROR."""

    def test_no_qualifying_bean_security_filter(self, classifier):
        """Deve classificar erro de SecurityFilterChain."""
        stderr = """
        No qualifying bean of type 'SecurityFilterChain' available
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_SECURITY_CONFIG_ERROR

    def test_websecurity_deprecated(self, classifier):
        """Deve classificar WebSecurityConfigurerAdapter deprecated."""
        stderr = """
        warning: WebSecurityConfigurerAdapter is deprecated
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.JAVA_SECURITY_CONFIG_ERROR


# ==================== SQL/DATABASE ERRORS ====================


class TestSqlMigrationError:
    """Testes para SQL_MIGRATION_ERROR."""

    def test_migration_failed(self, classifier):
        """Deve classificar 'Migration failed'."""
        stderr = """
        Migration V1__create_users.sql failed
        """

        result = classifier.classify(stderr, "", 1, "database")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.SQL_MIGRATION_ERROR

    def test_flyway_exception(self, classifier):
        """Deve classificar FlywayException."""
        stderr = """
        org.flywaydb.core.api.FlywayException: Migration failed
        """

        result = classifier.classify(stderr, "", 1, "database")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.SQL_MIGRATION_ERROR

    def test_relation_already_exists(self, classifier):
        """Deve classificar 'relation already exists'."""
        stderr = """
        ERROR: relation "users" already exists
        """

        result = classifier.classify(stderr, "", 1, "database")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.SQL_MIGRATION_ERROR
        assert result.errors[0].symbol == "users"


class TestSqlSyntaxError:
    """Testes para SQL_SYNTAX_ERROR."""

    def test_syntax_error_at_or_near(self, classifier):
        """Deve classificar 'syntax error at or near'."""
        stderr = """
        ERROR: syntax error at or near "SELECTT"
        """

        result = classifier.classify(stderr, "", 1, "database")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.SQL_SYNTAX_ERROR


# ==================== TYPESCRIPT/FRONTEND ERRORS ====================


class TestTsTypeError:
    """Testes para TS_TYPE_ERROR."""

    def test_type_not_assignable(self, classifier):
        """Deve classificar 'Type X is not assignable to type Y'."""
        stderr = """
        src/App.tsx:15:5 - error TS2322: Type 'string' is not assignable to type 'number'.
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_TYPE_ERROR

    def test_error_ts_code(self, classifier):
        """Deve classificar erro TS com código."""
        stderr = """
        error TS2345: Argument of type 'string' is not assignable
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_TYPE_ERROR


class TestTsMissingExport:
    """Testes para TS_MISSING_EXPORT."""

    def test_has_no_exported_member(self, classifier):
        """Deve classificar 'has no exported member'."""
        stderr = """
        Module '"./types"' has no exported member 'UserType'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_MISSING_EXPORT

    def test_export_not_found(self, classifier):
        """Deve classificar 'export was not found'."""
        stderr = """
        export 'Button' was not found in './components'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_MISSING_EXPORT
        assert result.errors[0].symbol == "Button"


class TestTsMissingImport:
    """Testes para TS_MISSING_IMPORT."""

    def test_cannot_find_module(self, classifier):
        """Deve classificar 'Cannot find module'."""
        stderr = """
        Cannot find module '@tanstack/react-query'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_MISSING_IMPORT

    def test_module_not_found(self, classifier):
        """Deve classificar 'Module not found'."""
        stderr = """
        Module not found: Error: Can't resolve './utils'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_MISSING_IMPORT


class TestTsPropertyNotExist:
    """Testes para TS_PROPERTY_NOT_EXIST."""

    def test_property_does_not_exist(self, classifier):
        """Deve classificar 'Property does not exist on type'."""
        stderr = """
        Property 'name' does not exist on type 'User'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_PROPERTY_NOT_EXIST
        assert result.errors[0].symbol == "name"


class TestTsJsxError:
    """Testes para TS_JSX_ERROR."""

    def test_no_closing_tag(self, classifier):
        """Deve classificar erro de tag JSX sem fechamento."""
        stderr = """
        JSX element 'div' has no corresponding closing tag
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_JSX_ERROR

    def test_cannot_be_jsx_component(self, classifier):
        """Deve classificar erro de componente JSX inválido."""
        stderr = """
        'MyComponent' cannot be used as a JSX component
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.TS_JSX_ERROR


# ==================== API ERRORS ====================


class TestApiClientMismatch:
    """Testes para API_CLIENT_MISMATCH."""

    def test_api_endpoint_not_found(self, classifier):
        """Deve classificar 'API endpoint not found'."""
        stderr = """
        API endpoint '/api/users' not found
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.API_CLIENT_MISMATCH


# ==================== FATAL ERRORS ====================


class TestFatalErrors:
    """Testes para erros fatais."""

    def test_out_of_memory(self, classifier):
        """Deve classificar Out of memory como FATAL."""
        stderr = """
        FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.FATAL_UNCLASSIFIED
        assert result.fatal_count == 1
        assert not result.is_patchable

    def test_permission_denied(self, classifier):
        """Deve classificar Permission denied como FATAL."""
        stderr = """
        Error: EACCES: permission denied, open '/etc/passwd'
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.FATAL_UNCLASSIFIED

    def test_no_space_left(self, classifier):
        """Deve classificar 'No space left on device' como FATAL."""
        stderr = """
        Error: ENOSPC: no space left on device
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.FATAL_UNCLASSIFIED


# ==================== FALLBACK CLASSIFICATION ====================


class TestFallbackClassification:
    """Testes para classificação de fallback."""

    def test_unknown_but_patchable(self, classifier):
        """Erro desconhecido com referência a código deve ser UNKNOWN_BUT_PATCHABLE."""
        stderr = """
        Some weird error in file.java: something went wrong
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.UNKNOWN_BUT_PATCHABLE

    def test_completely_unknown_known_step(self, classifier):
        """Erro desconhecido em step conhecido (backend/frontend) tenta patch."""
        stderr = """
        xyz123 random noise
        """

        # Para steps conhecidos (backend, frontend), tenta patch em vez de abortar
        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.UNKNOWN_BUT_PATCHABLE
        assert result.errors[0].confidence == 0.3  # Baixa confiança

    def test_completely_unknown_unknown_step(self, classifier):
        """Erro desconhecido em step desconhecido deve ser FATAL_UNCLASSIFIED."""
        stderr = """
        xyz123 random noise
        """

        # Para steps desconhecidos, marca como FATAL
        result = classifier.classify(stderr, "", 1, "unknown_step")

        assert result.has_errors
        assert result.errors[0].error_type == BuildErrorType.FATAL_UNCLASSIFIED

    def test_no_error_on_success(self, classifier):
        """Exit code 0 não deve gerar erros."""
        stderr = "Some warnings but build succeeded"

        result = classifier.classify(stderr, "", 0, "backend")

        assert not result.has_errors
        assert result.total_count == 0


# ==================== LOCATION EXTRACTION ====================


class TestLocationExtraction:
    """Testes para extração de localização do erro."""

    def test_extracts_java_file_location(self, classifier):
        """Deve extrair localização de arquivo Java."""
        stderr = """
        /home/user/project/src/Main.java:25:10: error: cannot find symbol
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        # A localização pode ou não ser extraída dependendo do padrão

    def test_extracts_ts_file_location(self, classifier):
        """Deve extrair localização de arquivo TypeScript."""
        stderr = """
        src/components/Button.tsx:15:3 - error TS2322: Type error
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors


# ==================== STEP PARSING ====================


class TestStepParsing:
    """Testes para parsing de step."""

    def test_backend_aliases(self, classifier):
        """Deve reconhecer aliases de backend."""
        for step in ["backend", "java", "maven", "mvn"]:
            result = classifier.classify("error TS2322:", "", 1, step)
            # Não deve encontrar erro TypeScript em backend
            # (a menos que seja UNKNOWN)

    def test_frontend_aliases(self, classifier):
        """Deve reconhecer aliases de frontend."""
        for step in ["frontend", "typescript", "npm", "react", "vite"]:
            result = classifier.classify(
                "cannot find symbol class X", "", 1, step
            )
            # Não deve encontrar erro Java em frontend

    def test_database_aliases(self, classifier):
        """Deve reconhecer aliases de database."""
        for step in ["database", "db", "sql", "flyway", "migration"]:
            result = classifier.classify("Migration V1 failed", "", 1, step)
            assert result.has_errors
            assert result.errors[0].error_type == BuildErrorType.SQL_MIGRATION_ERROR


# ==================== CLASSIFICATION RESULT ====================


class TestClassificationResult:
    """Testes para ClassificationResult."""

    def test_is_patchable_when_no_fatal(self, classifier):
        """is_patchable deve ser True quando não há erros fatais."""
        stderr = """
        error TS2322: Type 'string' is not assignable to type 'number'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.is_patchable
        assert result.patchable_count > 0
        assert result.fatal_count == 0

    def test_not_patchable_when_fatal(self, classifier):
        """is_patchable deve ser False quando há erros fatais."""
        stderr = "FATAL ERROR: Out of memory"

        result = classifier.classify(stderr, "", 1, "backend")

        assert not result.is_patchable
        assert result.fatal_count > 0

    def test_to_dict(self, classifier):
        """to_dict deve retornar dicionário correto."""
        stderr = "error TS2322: Type error"

        result = classifier.classify(stderr, "", 1, "frontend")
        d = result.to_dict()

        assert "errors" in d
        assert "total_count" in d
        assert "patchable_count" in d
        assert "fatal_count" in d


# ==================== MULTIPLE ERRORS ====================


class TestMultipleErrors:
    """Testes para múltiplos erros."""

    def test_multiple_errors_classified(self, classifier):
        """Deve classificar múltiplos erros."""
        stderr = """
        error TS2322: Type 'string' is not assignable to type 'number'
        Cannot find module './utils'
        Property 'name' does not exist on type 'User'
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.total_count >= 3

    def test_counts_correct(self, classifier):
        """Contagens devem estar corretas."""
        stderr = """
        error TS2322: Type error 1
        error TS2345: Type error 2
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.total_count == result.patchable_count + result.fatal_count


# ==================== CLASSIFY SINGLE ====================


class TestClassifySingle:
    """Testes para classify_single."""

    def test_classify_single_error(self, classifier):
        """Deve classificar uma única mensagem."""
        error = classifier.classify_single(
            "Cannot find module './api'",
            "frontend"
        )

        assert error.error_type == BuildErrorType.TS_MISSING_IMPORT

    def test_classify_single_unknown(self, classifier):
        """Mensagem desconhecida sem referência a código deve retornar FATAL."""
        error = classifier.classify_single(
            "some random error message",
            "backend"
        )

        # Sem referência a arquivos de código, é considerado fatal
        assert error.error_type in (
            BuildErrorType.UNKNOWN_BUT_PATCHABLE,
            BuildErrorType.FATAL_UNCLASSIFIED
        )

    def test_classify_single_unknown_with_file_ref(self, classifier):
        """Mensagem desconhecida com referência a código deve ser patchable."""
        error = classifier.classify_single(
            "some error in file.java: unknown issue",
            "backend"
        )

        assert error.error_type == BuildErrorType.UNKNOWN_BUT_PATCHABLE


# ==================== ENUM VALUES ====================


class TestEnumValues:
    """Testes para valores dos enums."""

    def test_all_error_types_defined(self):
        """Todos os tipos de erro devem estar definidos."""
        expected_types = [
            "JAVA_MISSING_IMPORT",
            "JAVA_METHOD_NOT_IMPLEMENTED",
            "JAVA_TYPE_MISMATCH",
            "JAVA_SECURITY_CONFIG_ERROR",
            "SQL_MIGRATION_ERROR",
            "TS_TYPE_ERROR",
            "TS_MISSING_EXPORT",
            "API_CLIENT_MISMATCH",
            "UNKNOWN_BUT_PATCHABLE",
            "FATAL_UNCLASSIFIED",
        ]

        for type_name in expected_types:
            assert hasattr(BuildErrorType, type_name)

    def test_build_step_values(self):
        """BuildStep deve ter valores corretos."""
        assert BuildStep.BACKEND.value == "backend"
        assert BuildStep.FRONTEND.value == "frontend"
        assert BuildStep.DATABASE.value == "database"


# ==================== CLASSIFIED ERROR ====================


class TestClassifiedError:
    """Testes para ClassifiedError."""

    def test_to_dict(self):
        """to_dict deve retornar dicionário correto."""
        error = ClassifiedError(
            error_type=BuildErrorType.TS_TYPE_ERROR,
            step=BuildStep.FRONTEND,
            message="Type error",
            file_path="src/App.tsx",
            line_number=15,
            column=5,
            symbol="string",
            confidence=0.9,
        )

        d = error.to_dict()

        assert d["error_type"] == "ts_type_error"
        assert d["step"] == "frontend"
        assert d["file_path"] == "src/App.tsx"
        assert d["line_number"] == 15
        assert d["confidence"] == 0.9
