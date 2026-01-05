"""Testes de integração do pipeline completo até Contracts (OAS + RBAC)."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from orchestrator.engine import Engine
from store.artifacts_store import ArtifactsStore


class TestPipelineContracts:
    """Testes do pipeline completo até geração de OAS e RBAC."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_pipeline_generates_oas(self, temp_store):
        """Pipeline deve gerar OpenAPI a partir de input válido."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_oas",
            raw_input="sistema de cadastro de clientes com nome e email",
            title="Sistema CRM",
        )

        assert result.success is True
        assert result.oas_validation_ok is True
        assert result.oas_version == 1
        assert result.oas_path is not None

    def test_pipeline_generates_rbac(self, temp_store):
        """Pipeline deve gerar RBAC a partir de input válido."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_rbac",
            raw_input="produtos (nome, preco)",
        )

        assert result.success is True
        assert result.rbac_validation_ok is True
        assert result.rbac_version == 1
        assert result.rbac_path is not None

    def test_pipeline_oas_file_exists(self, temp_store):
        """Arquivo OAS deve ser criado no store."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_oas_file",
            raw_input="produtos (nome, preco)",
        )

        oas_path = Path(result.oas_path)
        assert oas_path.exists()
        assert oas_path.suffix == ".yaml"

        # Verificar conteúdo do OAS
        with open(oas_path) as f:
            oas = yaml.safe_load(f)

        assert "openapi" in oas
        assert "paths" in oas
        assert oas["openapi"] == "3.0.0"

    def test_pipeline_rbac_file_exists(self, temp_store):
        """Arquivo RBAC deve ser criado no store."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_rbac_file",
            raw_input="pedidos (data, valor)",
        )

        rbac_path = Path(result.rbac_path)
        assert rbac_path.exists()
        assert rbac_path.suffix == ".json"

        # Verificar conteúdo do RBAC
        with open(rbac_path) as f:
            rbac = json.load(f)

        assert "roles" in rbac
        assert "permissions" in rbac
        assert "authenticated" in rbac["roles"]

    def test_pipeline_generates_all_four_artifacts(self, temp_store):
        """Pipeline deve gerar SRS, IR, OAS e RBAC."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="full_pipeline",
            raw_input="clientes (nome, email); produtos (nome, preco)",
        )

        assert result.success is True

        # SRS
        assert result.srs_version == 1
        assert result.srs_path is not None
        assert Path(result.srs_path).exists()

        # IR
        assert result.ir_version == 1
        assert result.ir_path is not None
        assert Path(result.ir_path).exists()

        # OAS
        assert result.oas_version == 1
        assert result.oas_path is not None
        assert Path(result.oas_path).exists()

        # RBAC
        assert result.rbac_version == 1
        assert result.rbac_path is not None
        assert Path(result.rbac_path).exists()

    def test_pipeline_operations_count(self, temp_store):
        """Pipeline deve contar operações geradas."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="ops_count",
            raw_input="produtos (nome, preco)",
        )

        # Com 1 entidade, deve ter 5 operações CRUD
        assert result.operations_count >= 5

    def test_pipeline_contracts_policy_ok(self, temp_store):
        """Pipeline deve validar consistência OAS/RBAC."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="policy_test",
            raw_input="clientes (nome, email)",
        )

        assert result.success is True
        assert result.contracts_policy_ok is True


class TestContractsVersioning:
    """Testes de versionamento de OAS e RBAC."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_oas_versioning_increments(self, temp_store):
        """OAS deve incrementar versão a cada execução."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(project="versioning", raw_input="clientes (nome, email)")
        assert result1.oas_version == 1

        # Segunda execução
        result2 = engine.run(project="versioning", raw_input="produtos (nome, preco)")
        assert result2.oas_version == 2

        # Terceira execução
        result3 = engine.run(project="versioning", raw_input="estoques (nome, quantidade)")
        assert result3.oas_version == 3

    def test_rbac_versioning_increments(self, temp_store):
        """RBAC deve incrementar versão a cada execução."""
        engine = Engine(store_root=temp_store)

        result1 = engine.run(project="rbac_ver", raw_input="itens1 (nome, valor)")
        assert result1.rbac_version == 1

        result2 = engine.run(project="rbac_ver", raw_input="itens2 (nome, valor)")
        assert result2.rbac_version == 2

    def test_all_versions_match(self, temp_store):
        """Todas as versões devem ser iguais em uma execução."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="match", raw_input="documentos (nome, tipo)")

        assert result.srs_version == result.ir_version
        assert result.ir_version == result.oas_version
        assert result.oas_version == result.rbac_version


class TestRunLogWithContracts:
    """Testes do run log com referências aos contratos."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_run_log_includes_oas_reference(self, temp_store):
        """Run log deve incluir referência ao OAS gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="log_oas", raw_input="controles (nome, status)")

        runs_dir = Path(temp_store) / "log_oas" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert payload["result"]["oas_version"] == 1
        assert payload["result"]["oas_path"] is not None

    def test_run_log_includes_rbac_reference(self, temp_store):
        """Run log deve incluir referência ao RBAC gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="log_rbac", raw_input="testes (nome, resultado)")

        runs_dir = Path(temp_store) / "log_rbac" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert payload["result"]["rbac_version"] == 1
        assert payload["result"]["rbac_path"] is not None

    def test_run_log_includes_oas_hash(self, temp_store):
        """Run log deve incluir hash do OAS gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="oas_hash", raw_input="registros (nome, hash)")

        runs_dir = Path(temp_store) / "oas_hash" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert "oas_hash" in payload, "Run log deve incluir oas_hash"

        # Verificar que hash corresponde ao OAS salvo
        with open(result.oas_path) as f:
            oas_content = f.read()

        expected_hash = hashlib.sha256(oas_content.encode()).hexdigest()[:16]
        assert payload["oas_hash"] == expected_hash

    def test_run_log_includes_rbac_hash(self, temp_store):
        """Run log deve incluir hash do RBAC gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="rbac_hash", raw_input="registros (nome, hash)")

        runs_dir = Path(temp_store) / "rbac_hash" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert "rbac_hash" in payload, "Run log deve incluir rbac_hash"

        # Verificar que hash corresponde ao RBAC salvo
        with open(result.rbac_path) as f:
            rbac_content = f.read()

        expected_hash = hashlib.sha256(rbac_content.encode()).hexdigest()[:16]
        assert payload["rbac_hash"] == expected_hash

    def test_run_log_includes_all_five_hashes(self, temp_store):
        """Run log deve incluir input_hash, srs_hash, ir_hash, oas_hash, rbac_hash."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="all_hashes",
            raw_input="itens (nome, tipo, status)",
        )

        runs_dir = Path(temp_store) / "all_hashes" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        # Verificar que todos os hashes existem
        assert "input_hash" in payload, "Run log deve incluir input_hash"
        assert "srs_hash" in payload, "Run log deve incluir srs_hash"
        assert "ir_hash" in payload, "Run log deve incluir ir_hash"
        assert "oas_hash" in payload, "Run log deve incluir oas_hash"
        assert "rbac_hash" in payload, "Run log deve incluir rbac_hash"

        # Verificar que todos os hashes têm 16 caracteres
        assert len(payload["input_hash"]) == 16
        assert len(payload["srs_hash"]) == 16
        assert len(payload["ir_hash"]) == 16
        assert len(payload["oas_hash"]) == 16
        assert len(payload["rbac_hash"]) == 16


class TestContractsContent:
    """Testes do conteúdo dos contratos gerados."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_oas_has_crud_for_entity(self, temp_store):
        """OAS deve ter operações CRUD para cada entidade."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="crud", raw_input="produtos (nome, preco)")

        with open(result.oas_path) as f:
            oas = yaml.safe_load(f)

        paths = oas["paths"]

        # Deve ter paths (collection e item)
        assert len(paths) >= 2

        # Verificar operações
        operations = []
        for path_item in paths.values():
            operations.extend(path_item.keys())

        # Deve ter GET, POST, PUT, DELETE
        assert "get" in operations
        assert "post" in operations

    def test_rbac_has_permissions_for_all_operations(self, temp_store):
        """RBAC deve ter permissões para todas as operações do OAS."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="perms", raw_input="clientes (nome, email)")

        with open(result.oas_path) as f:
            oas = yaml.safe_load(f)

        with open(result.rbac_path) as f:
            rbac = json.load(f)

        # Extrair operationIds do OAS
        oas_op_ids = set()
        for path_item in oas["paths"].values():
            for method, op in path_item.items():
                if isinstance(op, dict) and "operationId" in op:
                    oas_op_ids.add(op["operationId"])

        # Extrair operationIds do RBAC
        rbac_op_ids = set()
        for perm in rbac["permissions"]:
            rbac_op_ids.add(perm["operation_id"])

        # RBAC deve cobrir todas as operações do OAS
        assert oas_op_ids == rbac_op_ids

    def test_oas_has_schemas_for_entities(self, temp_store):
        """OAS deve ter schemas para cada entidade."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="schemas", raw_input="produtos (nome, preco)")

        with open(result.oas_path) as f:
            oas = yaml.safe_load(f)

        # Deve ter components/schemas
        assert "components" in oas
        assert "schemas" in oas["components"]
        assert len(oas["components"]["schemas"]) >= 1


class TestContractsPolicyValidator:
    """Testes do policy validator de contracts."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_contracts_policy_validates_consistency(self, temp_store):
        """Contracts policy deve validar consistência OAS/RBAC."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="consistency", raw_input="testes (nome, status)")

        # Deve ter passado validação de contracts policy
        assert result.contracts_policy_ok is True


class TestRunResultSummary:
    """Testes do summary do RunResult."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_summary_includes_oas_info(self, temp_store):
        """Summary deve incluir informações do OAS."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="summary", raw_input="testes (nome, resultado)")

        summary = result.summary()

        assert "OAS Validation: OK" in summary
        assert "OAS Version: v1" in summary
        assert "OAS Path:" in summary

    def test_summary_includes_rbac_info(self, temp_store):
        """Summary deve incluir informações do RBAC."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="summary2", raw_input="testes (nome, resultado)")

        summary = result.summary()

        assert "RBAC Validation: OK" in summary
        assert "RBAC Version: v1" in summary
        assert "RBAC Path:" in summary

    def test_summary_includes_operations_count(self, temp_store):
        """Summary deve incluir contagem de operações."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="ops", raw_input="produtos (nome, preco)")

        summary = result.summary()

        assert "Operations:" in summary

    def test_to_dict_includes_contracts_fields(self, temp_store):
        """to_dict deve incluir campos de contracts."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="dict", raw_input="testes (nome, resultado)")

        result_dict = result.to_dict()

        assert "oas_version" in result_dict
        assert "oas_path" in result_dict
        assert "rbac_version" in result_dict
        assert "rbac_path" in result_dict
        assert "operations_count" in result_dict
        assert "oas_validation_ok" in result_dict
        assert "rbac_validation_ok" in result_dict
        assert "contracts_policy_ok" in result_dict
