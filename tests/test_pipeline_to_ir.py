"""Testes de integração do pipeline completo até IR."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from orchestrator.engine import Engine
from store.artifacts_store import ArtifactsStore


class TestPipelineToIR:
    """Testes do pipeline completo até geração de IR."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_pipeline_generates_ir(self, temp_store):
        """Pipeline deve gerar IR a partir de input válido."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_ir",
            raw_input="sistema de cadastro de clientes com nome e email",
            title="Sistema CRM",
        )

        assert result.success is True
        assert result.ir_validation_ok is True
        assert result.ir_version == 1
        assert result.ir_path is not None

    def test_pipeline_ir_file_exists(self, temp_store):
        """Arquivo IR deve ser criado no store."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_ir",
            raw_input="produtos (nome, preco)",
        )

        ir_path = Path(result.ir_path)
        assert ir_path.exists()

        # Verificar conteúdo do IR
        with open(ir_path) as f:
            ir = json.load(f)

        assert "meta" in ir
        assert "domain" in ir
        assert "api_intent" in ir
        assert "ui" in ir
        assert "nfr" in ir

    def test_pipeline_ir_has_entities(self, temp_store):
        """IR gerado deve ter entidades."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_entities",
            raw_input="produtos (nome, preco); pedidos (data, valor)",
        )

        assert result.success is True
        assert result.entities_count >= 1

        # Verificar entities no arquivo
        with open(result.ir_path) as f:
            ir = json.load(f)

        assert len(ir["domain"]["entities"]) >= 1

    def test_pipeline_ir_versioning_increments(self, temp_store):
        """IR deve incrementar versão a cada execução."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(
            project="versioning_test",
            raw_input="clientes (nome, email)",
        )
        assert result1.ir_version == 1

        # Segunda execução
        result2 = engine.run(
            project="versioning_test",
            raw_input="fornecedores (nome, cnpj)",
        )
        assert result2.ir_version == 2

        # Terceira execução
        result3 = engine.run(
            project="versioning_test",
            raw_input="estoques (nome, quantidade)",
        )
        assert result3.ir_version == 3

        # Verificar todos os arquivos existem
        store = ArtifactsStore(temp_store)
        artifacts = store.list_artifacts("versioning_test", "IR")
        assert len(artifacts) == 3

    def test_pipeline_ir_has_srs_reference(self, temp_store):
        """IR deve ter referência à versão do SRS usado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="ref_test",
            raw_input="produtos (nome, tipo)",
        )

        with open(result.ir_path) as f:
            ir = json.load(f)

        # IR deve ter referência ao SRS version
        assert "srs_version" in ir["meta"]
        assert ir["meta"]["srs_version"] == f"v{result.srs_version}"

    def test_pipeline_srs_and_ir_versions_match(self, temp_store):
        """Versões de SRS e IR devem corresponder em cada run."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(
            project="match_test",
            raw_input="itens (nome, valor)",
        )
        assert result1.srs_version == 1
        assert result1.ir_version == 1

        # Segunda execução
        result2 = engine.run(
            project="match_test",
            raw_input="servicos (nome, preco)",
        )
        assert result2.srs_version == 2
        assert result2.ir_version == 2


class TestRunLogWithIR:
    """Testes do run log com referências ao IR."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_run_log_includes_ir_reference(self, temp_store):
        """Run log deve incluir referência ao IR gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="log_test",
            raw_input="controles (nome, status)",
        )

        # Encontrar o log mais recente
        runs_dir = Path(temp_store) / "log_test" / "runs"
        log_files = list(runs_dir.glob("*.json"))
        assert len(log_files) >= 1

        # Verificar conteúdo do log
        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert "result" in payload
        assert payload["result"]["ir_version"] == 1
        assert payload["result"]["ir_path"] is not None

    def test_run_log_includes_ir_hash(self, temp_store):
        """Run log deve incluir hash do IR gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_test",
            raw_input="registros (nome, hash)",
        )

        # Encontrar o log mais recente
        runs_dir = Path(temp_store) / "hash_test" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        # Verificar que ir_hash existe no log
        assert "ir_hash" in payload, "Run log deve incluir ir_hash"

        # Verificar que hash corresponde ao IR salvo
        with open(result.ir_path) as f:
            ir_content = f.read()

        expected_hash = hashlib.sha256(ir_content.encode()).hexdigest()[:16]
        assert payload["ir_hash"] == expected_hash

    def test_run_log_includes_all_hashes(self, temp_store):
        """Run log deve incluir input_hash, srs_hash e ir_hash."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="all_hashes_test",
            raw_input="documentos (nome, tipo, status)",
        )

        # Encontrar o log mais recente
        runs_dir = Path(temp_store) / "all_hashes_test" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        # Verificar que todos os hashes existem
        assert "input_hash" in payload, "Run log deve incluir input_hash"
        assert "srs_hash" in payload, "Run log deve incluir srs_hash"
        assert "ir_hash" in payload, "Run log deve incluir ir_hash"

        # Verificar que hashes têm 16 caracteres
        assert len(payload["input_hash"]) == 16
        assert len(payload["srs_hash"]) == 16
        assert len(payload["ir_hash"]) == 16

    def test_run_log_srs_hash_matches_file(self, temp_store):
        """srs_hash no run log deve corresponder ao arquivo SRS."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="srs_hash_test",
            raw_input="verificacoes (nome, resultado)",
        )

        runs_dir = Path(temp_store) / "srs_hash_test" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        # Calcular hash esperado do SRS
        with open(result.srs_path) as f:
            srs_content = f.read()

        expected_hash = hashlib.sha256(srs_content.encode()).hexdigest()[:16]
        assert payload["srs_hash"] == expected_hash

    def test_run_log_ir_hash_is_unique_per_ir(self, temp_store):
        """Hashes de IR diferentes devem ser diferentes."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(
            project="unique_hash",
            raw_input="clientes (nome, email)",
        )

        # Segunda execução com input diferente
        result2 = engine.run(
            project="unique_hash",
            raw_input="produtos (nome, preco); estoques (quantidade)",
        )

        # Encontrar logs
        runs_dir = Path(temp_store) / "unique_hash" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        assert len(log_files) == 2

        # Extrair hashes
        with open(log_files[0]) as f:
            hash1 = json.load(f)["payload"].get("ir_hash")

        with open(log_files[1]) as f:
            hash2 = json.load(f)["payload"].get("ir_hash")

        # Hashes devem ser diferentes para IRs diferentes
        assert hash1 != hash2


class TestHashStability:
    """Testes de estabilidade dos hashes (reprodutibilidade)."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_same_input_produces_same_input_hash(self, temp_store):
        """Mesmo input deve produzir mesmo input_hash."""
        engine = Engine(store_root=temp_store)
        same_input = "empresas (nome, cnpj)"

        # Primeira execução
        result1 = engine.run(project="stable1", raw_input=same_input)

        # Segunda execução com mesmo input
        result2 = engine.run(project="stable2", raw_input=same_input)

        # Extrair hashes dos logs
        runs_dir1 = Path(temp_store) / "stable1" / "runs"
        runs_dir2 = Path(temp_store) / "stable2" / "runs"

        with open(list(runs_dir1.glob("*.json"))[0]) as f:
            hash1 = json.load(f)["payload"]["input_hash"]

        with open(list(runs_dir2.glob("*.json"))[0]) as f:
            hash2 = json.load(f)["payload"]["input_hash"]

        assert hash1 == hash2, "Mesmo input deve produzir mesmo input_hash"

    def test_different_input_produces_different_input_hash(self, temp_store):
        """Inputs diferentes devem produzir input_hashes diferentes."""
        engine = Engine(store_root=temp_store)

        result1 = engine.run(project="diff1", raw_input="clientes (nome, email)")
        result2 = engine.run(project="diff2", raw_input="sistema de produtos")

        runs_dir1 = Path(temp_store) / "diff1" / "runs"
        runs_dir2 = Path(temp_store) / "diff2" / "runs"

        with open(list(runs_dir1.glob("*.json"))[0]) as f:
            hash1 = json.load(f)["payload"]["input_hash"]

        with open(list(runs_dir2.glob("*.json"))[0]) as f:
            hash2 = json.load(f)["payload"]["input_hash"]

        assert hash1 != hash2, "Inputs diferentes devem produzir hashes diferentes"


class TestPipelineIRValidation:
    """Testes de validação do IR no pipeline."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_pipeline_validates_ir_before_save(self, temp_store):
        """Pipeline deve validar IR antes de salvar."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="validation_test",
            raw_input="produtos (nome, tipo)",
        )

        # Deve ter passado validação
        assert result.ir_validation_ok is True

    def test_pipeline_validates_policy_before_save(self, temp_store):
        """Pipeline deve validar policy antes de salvar IR."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="policy_test",
            raw_input="controles (nome, status)",
        )

        # Deve ter passado policy
        assert result.policy_ok is True


class TestIRContent:
    """Testes do conteúdo do IR gerado."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_ir_has_ui_pages_for_entities(self, temp_store):
        """IR deve ter páginas UI para cada entidade."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="ui_test",
            raw_input="produtos (nome, preco)",
        )

        with open(result.ir_path) as f:
            ir = json.load(f)

        # Deve ter páginas UI
        assert len(ir["ui"]["pages"]) >= 3  # list, new, :id

        # Verificar estrutura das páginas
        for page in ir["ui"]["pages"]:
            assert "path" in page
            assert "title" in page
            assert "components" in page
            assert "actions" in page

    def test_ir_has_api_resources(self, temp_store):
        """IR deve ter recursos na API."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="api_test",
            raw_input="clientes (nome, email)",
        )

        with open(result.ir_path) as f:
            ir = json.load(f)

        # Deve ter resources
        assert len(ir["api_intent"]["resources"]) >= 1

    def test_ir_has_nfr_defaults(self, temp_store):
        """IR deve ter NFR com valores padrão."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="nfr_test",
            raw_input="registros (nome, tipo)",
        )

        with open(result.ir_path) as f:
            ir = json.load(f)

        # Verificar NFR
        assert "security" in ir["nfr"]
        assert "auth_required" in ir["nfr"]["security"]
