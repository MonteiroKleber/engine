"""Testes para o Registry de Blueprints.

Verifica:
- Lógica fechada (sem heurística, sem inferência)
- FORCED_GENERIC quando não registrado
- Registro e desregistro de blueprints
"""

import pytest

from blueprints.generic_blueprint import GenericBlueprint
from blueprints.registry import (
    REGISTRY,
    resolve_blueprint,
    get_registered_types,
    is_registered,
    register_blueprint,
    unregister_blueprint,
    clear_registry,
    get_blueprint_info,
)


# ==================== FIXTURES ====================


@pytest.fixture(autouse=True)
def clean_registry():
    """Limpa o registry antes e depois de cada teste."""
    # Salvar estado original
    original_registry = dict(REGISTRY)

    # Limpar para teste
    clear_registry()

    yield

    # Restaurar estado original
    clear_registry()
    REGISTRY.update(original_registry)


@pytest.fixture
def custom_blueprint():
    """Blueprint customizado para testes."""

    class CustomBlueprint(GenericBlueprint):
        """Blueprint customizado de teste."""
        pass

    return CustomBlueprint


# ==================== TESTS: RESOLVE_BLUEPRINT ====================


class TestResolveBlueprint:
    """Testes da função resolve_blueprint."""

    def test_returns_generic_for_unknown_type(self):
        """Tipo desconhecido deve retornar GenericBlueprint."""
        result = resolve_blueprint("unknown_type")

        assert result == GenericBlueprint

    def test_returns_generic_for_empty_string(self):
        """String vazia deve retornar GenericBlueprint."""
        result = resolve_blueprint("")

        assert result == GenericBlueprint

    def test_returns_generic_for_none_like(self):
        """None-like deve retornar GenericBlueprint."""
        result = resolve_blueprint(None)

        assert result == GenericBlueprint

    def test_returns_registered_blueprint(self, custom_blueprint):
        """Deve retornar blueprint registrado."""
        register_blueprint("custom", custom_blueprint)

        result = resolve_blueprint("custom")

        assert result == custom_blueprint

    def test_case_insensitive(self, custom_blueprint):
        """Lookup deve ser case-insensitive."""
        register_blueprint("custom", custom_blueprint)

        assert resolve_blueprint("CUSTOM") == custom_blueprint
        assert resolve_blueprint("Custom") == custom_blueprint
        assert resolve_blueprint("cUsToM") == custom_blueprint

    def test_strips_whitespace(self, custom_blueprint):
        """Deve ignorar espaços em branco."""
        register_blueprint("custom", custom_blueprint)

        assert resolve_blueprint("  custom  ") == custom_blueprint
        assert resolve_blueprint("\tcustom\n") == custom_blueprint

    def test_no_heuristics(self):
        """Não deve usar heurísticas."""
        # Mesmo que o nome seja similar, não deve inferir
        assert resolve_blueprint("crud") == GenericBlueprint
        assert resolve_blueprint("crud_app") == GenericBlueprint
        assert resolve_blueprint("my_crud") == GenericBlueprint

    def test_no_inference(self):
        """Não deve fazer inferência."""
        # Não deve tentar "adivinhar" baseado em padrões
        assert resolve_blueprint("user_management") == GenericBlueprint
        assert resolve_blueprint("authentication") == GenericBlueprint


# ==================== TESTS: REGISTRY MANAGEMENT ====================


class TestRegistryManagement:
    """Testes de gerenciamento do registry."""

    def test_register_blueprint(self, custom_blueprint):
        """Deve registrar blueprint corretamente."""
        register_blueprint("test_type", custom_blueprint)

        assert "test_type" in REGISTRY
        assert REGISTRY["test_type"] == custom_blueprint

    def test_register_blueprint_normalizes_type(self, custom_blueprint):
        """Deve normalizar o tipo ao registrar."""
        register_blueprint("  TEST_TYPE  ", custom_blueprint)

        assert "test_type" in REGISTRY
        assert "  TEST_TYPE  " not in REGISTRY

    def test_register_empty_type_raises(self, custom_blueprint):
        """Deve falhar ao registrar tipo vazio."""
        with pytest.raises(ValueError, match="cannot be empty"):
            register_blueprint("", custom_blueprint)

        with pytest.raises(ValueError, match="cannot be empty"):
            register_blueprint("   ", custom_blueprint)

    def test_register_non_class_raises(self):
        """Deve falhar ao registrar não-classe."""
        with pytest.raises(TypeError, match="must be a class"):
            register_blueprint("test", "not a class")

        with pytest.raises(TypeError, match="must be a class"):
            register_blueprint("test", GenericBlueprint())  # instância, não classe

    def test_register_non_blueprint_raises(self):
        """Deve falhar ao registrar classe que não é blueprint."""

        class NotABlueprint:
            pass

        with pytest.raises(TypeError, match="must be subclass"):
            register_blueprint("test", NotABlueprint)

    def test_unregister_blueprint(self, custom_blueprint):
        """Deve desregistrar blueprint corretamente."""
        register_blueprint("test_type", custom_blueprint)
        assert "test_type" in REGISTRY

        result = unregister_blueprint("test_type")

        assert result is True
        assert "test_type" not in REGISTRY

    def test_unregister_nonexistent(self):
        """Desregistrar tipo inexistente deve retornar False."""
        result = unregister_blueprint("nonexistent")

        assert result is False

    def test_clear_registry(self, custom_blueprint):
        """clear_registry deve limpar todos os registros."""
        register_blueprint("type1", custom_blueprint)
        register_blueprint("type2", custom_blueprint)
        assert len(REGISTRY) == 2

        clear_registry()

        assert len(REGISTRY) == 0


# ==================== TESTS: QUERY FUNCTIONS ====================


class TestQueryFunctions:
    """Testes das funções de consulta."""

    def test_get_registered_types_empty(self):
        """Deve retornar lista vazia quando registry vazio."""
        result = get_registered_types()

        assert result == []

    def test_get_registered_types(self, custom_blueprint):
        """Deve retornar lista de tipos registrados."""
        register_blueprint("type1", custom_blueprint)
        register_blueprint("type2", custom_blueprint)

        result = get_registered_types()

        assert "type1" in result
        assert "type2" in result
        assert len(result) == 2

    def test_is_registered_true(self, custom_blueprint):
        """is_registered deve retornar True para tipo registrado."""
        register_blueprint("registered", custom_blueprint)

        assert is_registered("registered") is True

    def test_is_registered_false(self):
        """is_registered deve retornar False para tipo não registrado."""
        assert is_registered("not_registered") is False

    def test_is_registered_case_insensitive(self, custom_blueprint):
        """is_registered deve ser case-insensitive."""
        register_blueprint("registered", custom_blueprint)

        assert is_registered("REGISTERED") is True
        assert is_registered("Registered") is True


# ==================== TESTS: GET_BLUEPRINT_INFO ====================


class TestGetBlueprintInfo:
    """Testes da função get_blueprint_info."""

    def test_info_for_generic(self):
        """Deve retornar info correta para GenericBlueprint."""
        info = get_blueprint_info("unknown")

        assert info["project_type"] == "unknown"
        assert info["blueprint_class"] == "GenericBlueprint"
        assert info["is_generic"] is True
        assert info["is_registered"] is False

    def test_info_for_registered(self, custom_blueprint):
        """Deve retornar info correta para blueprint registrado."""
        register_blueprint("custom", custom_blueprint)

        info = get_blueprint_info("custom")

        assert info["project_type"] == "custom"
        assert info["blueprint_class"] == "CustomBlueprint"
        assert info["is_generic"] is False
        assert info["is_registered"] is True


# ==================== TESTS: FORCED_GENERIC BEHAVIOR ====================


class TestForcedGeneric:
    """Testes do comportamento FORCED_GENERIC."""

    def test_always_returns_generic_for_unknown(self):
        """Tipos desconhecidos SEMPRE retornam GenericBlueprint."""
        unknown_types = [
            "crud",
            "auth",
            "report",
            "dashboard",
            "api",
            "microservice",
            "monolith",
            "unknown",
            "random",
            "test123",
        ]

        for project_type in unknown_types:
            assert resolve_blueprint(project_type) == GenericBlueprint

    def test_generic_is_safe_fallback(self):
        """GenericBlueprint deve ser um fallback seguro (no-op)."""
        blueprint = resolve_blueprint("unknown")

        # Deve poder instanciar
        instance = blueprint()

        # Deve ter método apply
        assert hasattr(instance, "apply")

        # apply deve ser no-op
        ir = {"entities": []}
        oas = {"paths": {}}
        rbac = {"roles": []}
        plan = {"tasks": [{"id": "t1"}]}

        result = instance.apply(ir, oas, rbac, plan)

        # Número de tarefas não deve mudar
        assert len(result.plan["tasks"]) == 1


# ==================== TESTS: REGISTRY ISOLATION ====================


class TestRegistryIsolation:
    """Testes de isolamento do registry."""

    def test_modifications_persist_within_test(self, custom_blueprint):
        """Modificações devem persistir dentro do teste."""
        register_blueprint("temp", custom_blueprint)
        assert is_registered("temp")

        # Ainda deve estar registrado
        assert resolve_blueprint("temp") == custom_blueprint

    def test_resolve_returns_class_not_instance(self, custom_blueprint):
        """resolve_blueprint deve retornar classe, não instância."""
        register_blueprint("test", custom_blueprint)

        result = resolve_blueprint("test")

        assert isinstance(result, type)
        assert not isinstance(result, GenericBlueprint)  # Não é instância

    def test_registry_is_dict(self):
        """REGISTRY deve ser um dicionário."""
        assert isinstance(REGISTRY, dict)


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_special_characters_in_type(self, custom_blueprint):
        """Deve lidar com caracteres especiais no tipo."""
        # Underscores são válidos
        register_blueprint("my_custom_type", custom_blueprint)
        assert resolve_blueprint("my_custom_type") == custom_blueprint

    def test_numeric_type(self, custom_blueprint):
        """Deve lidar com tipos numéricos (como string)."""
        register_blueprint("type123", custom_blueprint)
        assert resolve_blueprint("type123") == custom_blueprint

    def test_overwrite_registration(self, custom_blueprint):
        """Segundo registro deve sobrescrever o primeiro."""

        class AnotherBlueprint(GenericBlueprint):
            pass

        register_blueprint("test", custom_blueprint)
        register_blueprint("test", AnotherBlueprint)

        assert resolve_blueprint("test") == AnotherBlueprint

    def test_unicode_type(self, custom_blueprint):
        """Deve lidar com caracteres unicode."""
        register_blueprint("tipo_açúcar", custom_blueprint)
        assert resolve_blueprint("tipo_açúcar") == custom_blueprint
