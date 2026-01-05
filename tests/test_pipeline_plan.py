"""Testes de integração do pipeline completo até PLAN."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from orchestrator.engine import Engine


class TestPipelinePlan:
    """Testes do pipeline completo até geração de PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_pipeline_generates_plan(self, temp_store):
        """Pipeline deve gerar PLAN a partir de input válido."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_plan",
            raw_input="sistema de cadastro de clientes com nome e email",
            title="Sistema CRM",
        )

        assert result.success is True
        assert result.plan_validation_ok is True
        assert result.plan_version == 1
        assert result.plan_path is not None

    def test_pipeline_plan_file_exists(self, temp_store):
        """Arquivo PLAN deve ser criado no store."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_plan_file",
            raw_input="produtos (nome, preco)",
        )

        plan_path = Path(result.plan_path)
        assert plan_path.exists()
        assert plan_path.suffix == ".json"

        # Verificar conteúdo do PLAN
        with open(plan_path) as f:
            plan = json.load(f)

        assert "meta" in plan
        assert "tasks" in plan
        assert plan["meta"]["strategy"] == "PATCH_ONLY"

    def test_pipeline_plan_has_tasks(self, temp_store):
        """PLAN deve ter tasks geradas para as entidades."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="test_plan_tasks",
            raw_input="clientes (nome, email)",
        )

        assert result.tasks_count > 0

        with open(result.plan_path) as f:
            plan = json.load(f)

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

    def test_pipeline_generates_all_five_artifacts(self, temp_store):
        """Pipeline deve gerar SRS, IR, OAS, RBAC e PLAN."""
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

        # PLAN
        assert result.plan_version == 1
        assert result.plan_path is not None
        assert Path(result.plan_path).exists()

    def test_pipeline_plan_policy_ok(self, temp_store):
        """Pipeline deve validar consistência do PLAN."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="policy_test",
            raw_input="clientes (nome, email)",
        )

        assert result.success is True
        assert result.plan_policy_ok is True

    def test_pipeline_tasks_count(self, temp_store):
        """Pipeline deve contar tasks geradas."""
        engine = Engine(store_root=temp_store)

        result = engine.run(
            project="tasks_count",
            raw_input="produtos (nome, preco)",
        )

        # Com 1 entidade, deve ter 8 tasks (conforme PlannerAgent)
        assert result.tasks_count == 8


class TestPlanVersioning:
    """Testes de versionamento de PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_plan_versioning_increments(self, temp_store):
        """PLAN deve incrementar versão a cada execução."""
        engine = Engine(store_root=temp_store)

        # Primeira execução
        result1 = engine.run(project="versioning", raw_input="clientes (nome, email)")
        assert result1.plan_version == 1

        # Segunda execução
        result2 = engine.run(project="versioning", raw_input="produtos (nome, preco)")
        assert result2.plan_version == 2

        # Terceira execução
        result3 = engine.run(project="versioning", raw_input="estoques (nome, quantidade)")
        assert result3.plan_version == 3

    def test_all_versions_match(self, temp_store):
        """Todas as versões devem ser iguais em uma execução."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="match", raw_input="documentos (nome, tipo)")

        assert result.srs_version == result.ir_version
        assert result.ir_version == result.oas_version
        assert result.oas_version == result.rbac_version
        assert result.rbac_version == result.plan_version


class TestRunLogWithPlan:
    """Testes do run log com referências ao PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_run_log_includes_plan_reference(self, temp_store):
        """Run log deve incluir referência ao PLAN gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="log_plan", raw_input="controles (nome, status)")

        runs_dir = Path(temp_store) / "log_plan" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert payload["result"]["plan_version"] == 1
        assert payload["result"]["plan_path"] is not None

    def test_run_log_includes_plan_hash(self, temp_store):
        """Run log deve incluir hash do PLAN gerado."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="plan_hash", raw_input="registros (nome, hash)")

        runs_dir = Path(temp_store) / "plan_hash" / "runs"
        log_files = list(runs_dir.glob("*.json"))

        with open(log_files[-1]) as f:
            log = json.load(f)

        payload = log["payload"]
        assert "plan_hash" in payload, "Run log deve incluir plan_hash"

        # Verificar que hash corresponde ao PLAN salvo
        with open(result.plan_path) as f:
            plan_content = f.read()

        expected_hash = hashlib.sha256(plan_content.encode()).hexdigest()[:16]
        assert payload["plan_hash"] == expected_hash

    def test_run_log_includes_all_six_hashes(self, temp_store):
        """Run log deve incluir input_hash, srs_hash, ir_hash, oas_hash, rbac_hash, plan_hash."""
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
        assert "plan_hash" in payload, "Run log deve incluir plan_hash"

        # Verificar que todos os hashes têm 16 caracteres
        assert len(payload["input_hash"]) == 16
        assert len(payload["srs_hash"]) == 16
        assert len(payload["ir_hash"]) == 16
        assert len(payload["oas_hash"]) == 16
        assert len(payload["rbac_hash"]) == 16
        assert len(payload["plan_hash"]) == 16


class TestPlanContent:
    """Testes do conteúdo do PLAN gerado."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_plan_has_strategy_patch_only(self, temp_store):
        """PLAN deve ter strategy PATCH_ONLY."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="strategy", raw_input="clientes (nome, email)")

        with open(result.plan_path) as f:
            plan = json.load(f)

        assert plan["meta"]["strategy"] == "PATCH_ONLY"

    def test_plan_has_version(self, temp_store):
        """PLAN deve ter version no meta."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="version", raw_input="produtos (nome, preco)")

        with open(result.plan_path) as f:
            plan = json.load(f)

        assert "version" in plan["meta"]
        assert plan["meta"]["version"] == "v1"

    def test_plan_tasks_have_sequential_order(self, temp_store):
        """PLAN tasks devem ter orders sequenciais 1..N."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="order", raw_input="estoques (nome, quantidade)")

        with open(result.plan_path) as f:
            plan = json.load(f)

        tasks = plan["tasks"]
        orders = [t["order"] for t in tasks]

        # Deve ter sequência 1..N
        expected = list(range(1, len(tasks) + 1))
        assert sorted(orders) == expected

    def test_plan_tasks_have_unique_ids(self, temp_store):
        """PLAN tasks devem ter IDs únicos."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="unique_ids", raw_input="vendas (data, valor)")

        with open(result.plan_path) as f:
            plan = json.load(f)

        task_ids = [t["id"] for t in plan["tasks"]]

        # IDs devem ser únicos
        assert len(task_ids) == len(set(task_ids))


class TestRunResultWithPlan:
    """Testes do RunResult com campos de PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_summary_includes_plan_info(self, temp_store):
        """Summary deve incluir informações do PLAN."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="summary", raw_input="testes (nome, resultado)")

        summary = result.summary()

        assert "PLAN Validation: OK" in summary
        assert "PLAN Version: v1" in summary
        assert "PLAN Path:" in summary
        assert "Tasks:" in summary

    def test_to_dict_includes_plan_fields(self, temp_store):
        """to_dict deve incluir campos de PLAN."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="dict", raw_input="testes (nome, resultado)")

        result_dict = result.to_dict()

        assert "plan_version" in result_dict
        assert "plan_path" in result_dict
        assert "tasks_count" in result_dict
        assert "plan_validation_ok" in result_dict
        assert "plan_policy_ok" in result_dict


class TestPlanPolicyValidator:
    """Testes do policy validator de PLAN."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_plan_policy_validates_strategy(self, temp_store):
        """Plan policy deve validar strategy PATCH_ONLY."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="policy_strategy", raw_input="testes (nome, resultado)")

        assert result.plan_policy_ok is True

    def test_plan_policy_validates_tasks_not_empty(self, temp_store):
        """Plan policy deve validar que tasks não está vazio."""
        engine = Engine(store_root=temp_store)

        result = engine.run(project="policy_tasks", raw_input="clientes (nome, email)")

        assert result.plan_policy_ok is True
        assert result.tasks_count > 0
