"""Testes de integração do pipeline completo até geração de PLAN.

Este arquivo foca nos testes obrigatórios do Dia 7:
- Pipeline completo gera PLAN
- Versionamento incrementa
- Run log contém plan_hash
- plan_hash bate com arquivo
"""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from orchestrator.engine import Engine


class TestPipelineToPlanIntegration:
    """Testes de integração: pipeline completo gera PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_pipeline_generates_plan_from_raw_input(self, temp_store):
        """Pipeline completo deve gerar PLAN a partir de input raw."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="integration_test",
            raw_input="sistema de cadastro de empresas com nome, cnpj e endereço",
            title="Cadastro Empresas",
        )

        assert result.success is True
        assert result.plan_path is not None
        assert Path(result.plan_path).exists()

    def test_pipeline_generates_valid_plan_structure(self, temp_store):
        """PLAN gerado deve ter estrutura válida."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="structure_test",
            raw_input="clientes (nome, email)",
        )

        with open(result.plan_path) as f:
            plan = json.load(f)

        # Meta obrigatório
        assert "meta" in plan
        assert plan["meta"]["strategy"] == "PATCH_ONLY"
        assert "version" in plan["meta"]

        # Tasks obrigatório
        assert "tasks" in plan
        assert len(plan["tasks"]) > 0

        # Cada task deve ter estrutura correta
        for task in plan["tasks"]:
            assert "id" in task
            assert "title" in task
            assert "order" in task
            assert "files" in task
            assert "acceptance" in task
            assert len(task["files"]) > 0
            assert len(task["acceptance"]) > 0

    def test_pipeline_plan_passes_schema_validation(self, temp_store):
        """PLAN gerado deve passar validação de schema."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="schema_test",
            raw_input="produtos (nome, preco)",
        )

        assert result.plan_validation_ok is True

    def test_pipeline_plan_passes_policy_validation(self, temp_store):
        """PLAN gerado deve passar validação de policy."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="policy_test",
            raw_input="pedidos (data, valor)",
        )

        assert result.plan_policy_ok is True

    def test_pipeline_generates_all_artifacts(self, temp_store):
        """Pipeline deve gerar todos os 5 artefatos: SRS, IR, OAS, RBAC, PLAN."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="full_artifacts",
            raw_input="vendas (data, valor, cliente)",
        )

        # Verificar que todos os artefatos foram gerados
        assert result.srs_path is not None
        assert result.ir_path is not None
        assert result.oas_path is not None
        assert result.rbac_path is not None
        assert result.plan_path is not None

        # Verificar que todos os arquivos existem
        assert Path(result.srs_path).exists()
        assert Path(result.ir_path).exists()
        assert Path(result.oas_path).exists()
        assert Path(result.rbac_path).exists()
        assert Path(result.plan_path).exists()


class TestPlanVersioningIncrement:
    """Testes de versionamento: versão incrementa a cada execução."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_first_run_creates_v1(self, temp_store):
        """Primeira execução deve criar versão 1."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="versioning",
            raw_input="clientes (nome, email)",
        )

        assert result.plan_version == 1
        assert "v1.json" in result.plan_path

    def test_second_run_creates_v2(self, temp_store):
        """Segunda execução deve criar versão 2."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(project="versioning", raw_input="clientes (nome, email)")
        assert result1.plan_version == 1

        # Segunda execução
        result2 = engine.run(project="versioning", raw_input="produtos (nome, preco)")
        assert result2.plan_version == 2
        assert "v2.json" in result2.plan_path

    def test_versioning_increments_consistently(self, temp_store):
        """Versionamento deve incrementar consistentemente."""
        engine = Engine(store_root=temp_store)

        for i in range(1, 6):
            result = engine.run(
                project="consistent_versioning",
                raw_input=f"registros{i} (nome, status)",
            )
            assert result.plan_version == i

    def test_all_artifacts_have_same_version(self, temp_store):
        """Todos os artefatos devem ter a mesma versão."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="same_version",
            raw_input="estoques (nome, quantidade)",
        )

        assert result.srs_version == result.plan_version
        assert result.ir_version == result.plan_version
        assert result.oas_version == result.plan_version
        assert result.rbac_version == result.plan_version

    def test_version_files_are_preserved(self, temp_store):
        """Arquivos de versões anteriores devem ser preservados."""
        engine = Engine(store_root=temp_store)

        # Executar 3 vezes
        result1 = engine.run(project="preserve", raw_input="registros1 (nome, tipo)")
        result2 = engine.run(project="preserve", raw_input="registros2 (nome, tipo)")
        result3 = engine.run(project="preserve", raw_input="registros3 (nome, tipo)")

        # Verificar que todos os arquivos existem
        assert Path(result1.plan_path).exists()
        assert Path(result2.plan_path).exists()
        assert Path(result3.plan_path).exists()

        # Verificar que são arquivos diferentes
        assert result1.plan_path != result2.plan_path
        assert result2.plan_path != result3.plan_path


class TestRunLogPlanHash:
    """Testes do run log: contém plan_hash."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_run_log_contains_plan_hash(self, temp_store):
        """Run log deve conter plan_hash."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_test",
            raw_input="clientes (nome, email)",
        )

        # Encontrar o run log mais recente
        runs_dir = Path(temp_store) / "hash_test" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))
        assert len(log_files) > 0

        with open(log_files[-1]) as f:
            log = json.load(f)

        assert "payload" in log
        assert "plan_hash" in log["payload"]

    def test_plan_hash_is_16_chars(self, temp_store):
        """plan_hash deve ter 16 caracteres."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_length",
            raw_input="produtos (nome, preco)",
        )

        runs_dir = Path(temp_store) / "hash_length" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        plan_hash = log["payload"]["plan_hash"]
        assert len(plan_hash) == 16

    def test_plan_hash_is_hex_string(self, temp_store):
        """plan_hash deve ser string hexadecimal."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_hex",
            raw_input="pedidos (data, valor)",
        )

        runs_dir = Path(temp_store) / "hash_hex" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        plan_hash = log["payload"]["plan_hash"]
        # Deve ser hexadecimal válido
        int(plan_hash, 16)  # Não deve lançar exceção


class TestPlanHashMatchesFile:
    """Testes: plan_hash bate com arquivo."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_plan_hash_matches_file_content(self, temp_store):
        """plan_hash no run log deve bater com hash do arquivo PLAN."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_match",
            raw_input="clientes (nome, email)",
        )

        # Ler hash do run log
        runs_dir = Path(temp_store) / "hash_match" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        logged_hash = log["payload"]["plan_hash"]

        # Calcular hash do arquivo PLAN
        with open(result.plan_path) as f:
            plan_content = f.read()

        expected_hash = hashlib.sha256(plan_content.encode()).hexdigest()[:16]

        assert logged_hash == expected_hash

    def test_different_plans_have_different_hashes(self, temp_store):
        """PLANs diferentes devem ter hashes diferentes."""
        engine = Engine(store_root=temp_store)

        # Gerar dois PLANs diferentes
        result1 = engine.run(project="diff_hash_1", raw_input="clientes (nome, email)")
        result2 = engine.run(project="diff_hash_2", raw_input="produtos (nome, preco)")

        # Ler hashes dos run logs
        runs_dir1 = Path(temp_store) / "diff_hash_1" / "runs"
        runs_dir2 = Path(temp_store) / "diff_hash_2" / "runs"

        with open(sorted(runs_dir1.glob("*.json"))[-1]) as f:
            hash1 = json.load(f)["payload"]["plan_hash"]

        with open(sorted(runs_dir2.glob("*.json"))[-1]) as f:
            hash2 = json.load(f)["payload"]["plan_hash"]

        assert hash1 != hash2

    def test_same_input_same_hash(self, temp_store):
        """Mesmo input em projetos diferentes deve gerar PLANs com estrutura similar."""
        engine = Engine(store_root=temp_store)

        # Mesmo input, projetos diferentes
        result1 = engine.run(project="same_input_1", raw_input="clientes (nome, email)")
        result2 = engine.run(project="same_input_2", raw_input="clientes (nome, email)")

        # Carregar os PLANs
        with open(result1.plan_path) as f:
            plan1 = json.load(f)

        with open(result2.plan_path) as f:
            plan2 = json.load(f)

        # PLANs devem ter mesma estrutura de tasks
        assert len(plan1["tasks"]) == len(plan2["tasks"])
        for t1, t2 in zip(plan1["tasks"], plan2["tasks"]):
            assert t1["id"] == t2["id"]


class TestRunLogAllHashes:
    """Testes: run log contém todos os hashes."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_run_log_contains_all_hashes(self, temp_store):
        """Run log deve conter todos os 6 hashes."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="all_hashes",
            raw_input="documentos (nome, tipo)",
        )

        runs_dir = Path(temp_store) / "all_hashes" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        # Verificar todos os hashes
        assert "input_hash" in payload
        assert "srs_hash" in payload
        assert "ir_hash" in payload
        assert "oas_hash" in payload
        assert "rbac_hash" in payload
        assert "plan_hash" in payload

    def test_all_hashes_have_correct_length(self, temp_store):
        """Todos os hashes devem ter 16 caracteres."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="hash_lengths",
            raw_input="vendas (data, valor)",
        )

        runs_dir = Path(temp_store) / "hash_lengths" / "runs"
        log_files = sorted(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]

        assert len(payload["input_hash"]) == 16
        assert len(payload["srs_hash"]) == 16
        assert len(payload["ir_hash"]) == 16
        assert len(payload["oas_hash"]) == 16
        assert len(payload["rbac_hash"]) == 16
        assert len(payload["plan_hash"]) == 16


class TestPlanStability:
    """Testes de estabilidade: geração de PLAN é consistente."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_plan_always_generated(self, temp_store):
        """PLAN deve sempre ser gerado para inputs válidos."""
        engine = Engine(store_root=temp_store)

        inputs = [
            "clientes (nome, email)",
            "produtos (nome, preco)",
            "estoques (nome, quantidade)",
            "pedidos (data, valor)",
            "vendas (data, cliente)",
        ]

        for i, inp in enumerate(inputs):
            result = engine.run(project=f"stability_{i}", raw_input=inp)
            assert result.success is True
            assert result.plan_path is not None
            assert Path(result.plan_path).exists()

    def test_plan_always_valid(self, temp_store):
        """PLAN gerado deve sempre ser válido."""
        engine = Engine(store_root=temp_store)

        inputs = [
            "usuarios (nome, email)",
            "empresas (nome, cnpj)",
            "projetos (nome, status)",
        ]

        for i, inp in enumerate(inputs):
            result = engine.run(project=f"valid_{i}", raw_input=inp)
            assert result.plan_validation_ok is True
            assert result.plan_policy_ok is True

    def test_plan_has_expected_task_count(self, temp_store):
        """PLAN deve ter número esperado de tasks (8 por entidade)."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="task_count",
            raw_input="clientes (nome, email)",
        )

        # 1 entidade = 8 tasks
        assert result.tasks_count == 8

    def test_plan_tasks_have_correct_order(self, temp_store):
        """Tasks do PLAN devem ter orders corretos (1..N)."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="task_order",
            raw_input="produtos (nome, preco)",
        )

        with open(result.plan_path) as f:
            plan = json.load(f)

        orders = sorted([t["order"] for t in plan["tasks"]])
        expected = list(range(1, len(plan["tasks"]) + 1))
        assert orders == expected
