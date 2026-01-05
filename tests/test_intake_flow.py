"""Testes para o fluxo de intake e engine completo."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from intake.normalizer import Normalizer
from intake.blueprint_classifier import BlueprintClassifier, ClassificationResult
from intake.req_analyst import RequirementsAnalyst
from orchestrator.engine import Engine
from store.artifacts_store import ArtifactsStore


class TestNormalizer:
    """Testes do Normalizer."""

    def test_normalize_strips_whitespace(self):
        """Normalização deve remover espaços extras."""
        normalizer = Normalizer()
        result = normalizer.normalize("  texto com espaços  ")
        assert result["normalized"] == "texto com espaços"

    def test_normalize_removes_duplicate_spaces(self):
        """Normalização deve remover espaços duplicados."""
        normalizer = Normalizer()
        result = normalizer.normalize("texto   com    muitos   espaços")
        assert result["normalized"] == "texto com muitos espaços"

    def test_normalize_preserves_original(self):
        """Normalização deve preservar texto original."""
        normalizer = Normalizer()
        original = "  texto original  "
        result = normalizer.normalize(original)
        assert result["original"] == original

    def test_normalize_sets_language(self):
        """Normalização deve definir idioma padrão."""
        normalizer = Normalizer()
        result = normalizer.normalize("qualquer texto")
        assert result["language"] == "pt-BR"

    def test_normalize_creates_bullets(self):
        """Normalização deve criar bullets por linha."""
        normalizer = Normalizer()
        result = normalizer.normalize("linha1\nlinha2\nlinha3")
        assert result["bullets"] == ["linha1", "linha2", "linha3"]

    def test_normalize_truncates_long_input(self):
        """Normalização deve truncar input muito longo."""
        normalizer = Normalizer(max_size=100)
        long_text = "x" * 200
        result = normalizer.normalize(long_text)
        assert len(result["normalized"]) == 100
        assert result["truncated"] is True


class TestBlueprintClassifier:
    """Testes do BlueprintClassifier."""

    def test_default_confidence_threshold(self):
        """Threshold padrão deve ser 0.85."""
        classifier = BlueprintClassifier()
        assert classifier.confidence_threshold == 0.85

    def test_custom_confidence_threshold(self):
        """Deve aceitar threshold customizado."""
        classifier = BlueprintClassifier(confidence_threshold=0.9)
        assert classifier.confidence_threshold == 0.9

    def test_classify_returns_classification_result(self):
        """Classificação deve retornar ClassificationResult."""
        classifier = BlueprintClassifier()
        result = classifier.classify({"normalized": "texto"})
        assert isinstance(result, ClassificationResult)

    def test_classify_returns_generic_by_default(self):
        """Classificação padrão deve ser generic (v1 forced)."""
        classifier = BlueprintClassifier()
        result = classifier.classify({"normalized": "texto"})
        assert result.selected_blueprint == "generic"
        assert result.mode == "FORCED_GENERIC"
        assert result.confidence == 0.0


class TestRequirementsAnalyst:
    """Testes do RequirementsAnalyst."""

    def test_default_max_questions(self):
        """Máximo de perguntas padrão deve ser 7."""
        analyst = RequirementsAnalyst()
        assert analyst.max_questions_per_round == 7

    def test_custom_max_questions(self):
        """Deve aceitar máximo customizado."""
        analyst = RequirementsAnalyst(max_questions_per_round=5)
        assert analyst.max_questions_per_round == 5

    def test_analyze_returns_dict(self):
        """Análise deve retornar dicionário."""
        analyst = RequirementsAnalyst()
        result = analyst.analyze({"normalized": "texto"})
        assert isinstance(result, dict)
        assert "requirements" in result
        assert "open_questions" in result

    def test_analyze_creates_admin_actor(self):
        """Análise deve criar ator admin."""
        analyst = RequirementsAnalyst()
        result = analyst.analyze({"normalized": "texto"})
        assert "actors" in result
        assert result["actors"][0]["id"] == "admin"

    def test_generate_srs_creates_valid_structure(self):
        """generate_srs deve criar estrutura SRS válida."""
        analyst = RequirementsAnalyst()
        normalizer = Normalizer()

        normalized = normalizer.normalize("cadastrar produtos")
        srs = analyst.generate_srs(normalized, "Sistema Teste")

        assert "id" in srs
        assert "title" in srs
        assert "requirements" in srs
        assert srs["title"] == "Sistema Teste"


class TestEngineIntegration:
    """Testes de integração do Engine completo."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_engine_generates_srs(self, temp_store):
        """Engine deve gerar SRS com sucesso."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_project",
            raw_input="produtos (nome, preco)",
        )

        assert result.success is True
        assert result.srs_validation_ok is True
        assert result.requirements_count >= 3

    def test_engine_versions_srs_in_store(self, temp_store):
        """Engine deve versionar SRS no store."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_project",
            raw_input="cadastros (nome, tipo)",
        )

        # Verificar que SRS foi salvo
        assert result.srs_version == 1
        assert result.srs_path is not None

        # Verificar arquivo existe
        srs_path = Path(result.srs_path)
        assert srs_path.exists()

        # Verificar conteúdo
        with open(srs_path) as f:
            srs = json.load(f)
        assert "id" in srs
        assert "requirements" in srs

    def test_engine_creates_run_log(self, temp_store):
        """Engine deve criar log de execução."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_project",
            raw_input="registros (nome, data)",
        )

        # Verificar que log foi criado
        runs_dir = Path(temp_store) / "test_project" / "runs"
        assert runs_dir.exists()

        log_files = list(runs_dir.glob("*.json"))
        assert len(log_files) >= 1

        # Verificar conteúdo do log
        with open(log_files[0]) as f:
            log = json.load(f)
        assert "execution_id" in log
        assert "payload" in log

    def test_engine_increments_version(self, temp_store):
        """Engine deve incrementar versão a cada execução."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(
            project="test_project",
            raw_input="versao1 (nome, tipo)",
        )
        assert result1.srs_version == 1

        # Segunda execução
        result2 = engine.run(
            project="test_project",
            raw_input="versao2 (nome, tipo)",
        )
        assert result2.srs_version == 2

        # Verificar ambos os arquivos existem
        store = ArtifactsStore(temp_store)
        artifacts = store.list_artifacts("test_project", "SRS")
        assert len(artifacts) == 2

    def test_engine_with_custom_title(self, temp_store):
        """Engine deve aceitar título customizado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="meu_projeto",
            raw_input="vendas (data, valor)",
            title="CRM de Vendas",
        )

        assert result.success is True

        # Verificar título no SRS
        with open(result.srs_path) as f:
            srs = json.load(f)
        assert srs["title"] == "CRM de Vendas"

    def test_engine_blueprint_is_generic(self, temp_store):
        """Engine deve usar blueprint genérico (v1)."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test",
            raw_input="sistemas (nome, tipo)",
        )

        assert result.blueprint_type == "generic"

    def test_full_pipeline_flow(self, temp_store):
        """Teste completo do fluxo do pipeline até IR."""
        engine = Engine(store_root=temp_store)

        # Executar com input usando mini-gramatica
        result = engine.run(
            project="loja_virtual",
            raw_input="produtos (nome, preco, descricao); pedidos (data, valor, cliente)",
            title="Sistema Loja Virtual",
        )

        # Verificar sucesso
        assert result.success is True
        assert result.srs_validation_ok is True
        assert result.ir_validation_ok is True
        assert result.policy_ok is True
        assert result.project == "loja_virtual"

        # Verificar SRS gerado
        assert result.srs_version == 1
        srs_path = Path(result.srs_path)
        assert srs_path.exists()

        with open(srs_path) as f:
            srs = json.load(f)

        assert srs["title"] == "Sistema Loja Virtual"
        assert len(srs["requirements"]) >= 3

        # Verificar IR gerado
        assert result.ir_version == 1
        ir_path = Path(result.ir_path)
        assert ir_path.exists()

        with open(ir_path) as f:
            ir = json.load(f)

        assert "domain" in ir
        assert "entities" in ir["domain"]
        assert len(ir["domain"]["entities"]) >= 1

        # Verificar log criado
        runs_dir = Path(temp_store) / "loja_virtual" / "runs"
        assert len(list(runs_dir.glob("*.json"))) >= 1

        # Verificar estrutura do store
        store_path = Path(temp_store) / "loja_virtual"
        assert (store_path / "SRS").exists()
        assert (store_path / "IR").exists()
        assert (store_path / "logs").exists()
        assert (store_path / "runs").exists()
