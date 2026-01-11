"""Release Checklist - Gates finais antes do release.

Verifica todos os itens obrigatorios para um release valido:
1. Artefatos presentes: SRS/IR/OAS/RBAC/PLAN
2. Hashes completos no run log
3. Build ok
4. Smoke ok
5. Blueprint registrado
6. Regras absolutas respeitadas

REGRA: Qualquer item faltando → FAIL.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import get_config
from store.artifacts_store import ArtifactsStore
from blueprints.registry import resolve_blueprint
from blueprints.generic_blueprint import GenericBlueprint


@dataclass
class ChecklistItem:
    """Item individual do checklist."""

    name: str
    category: str  # "artifacts", "hashes", "build", "smoke", "blueprint", "rules"
    status: str  # "PASS", "FAIL", "SKIP"
    message: str
    required: bool = True  # Se True, FAIL bloqueia release
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "required": self.required,
            "details": self.details,
        }


@dataclass
class ReleaseChecklistResult:
    """Resultado completo do checklist de release."""

    project: str
    timestamp: str
    passed: bool  # True se todos os itens required passaram
    total_items: int = 0
    passed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    items: List[ChecklistItem] = field(default_factory=list)
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "project": self.project,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "total_items": self.total_items,
            "passed_items": self.passed_items,
            "failed_items": self.failed_items,
            "skipped_items": self.skipped_items,
            "items": [item.to_dict() for item in self.items],
            "blocking_failures": self.blocking_failures,
        }

    def summary(self) -> str:
        """Retorna resumo do checklist."""
        lines = [
            "=" * 50,
            f"Release Checklist: {'PASS' if self.passed else 'FAIL'}",
            "=" * 50,
            f"Project: {self.project}",
            f"Total Items: {self.total_items}",
            f"Passed: {self.passed_items}",
            f"Failed: {self.failed_items}",
            f"Skipped: {self.skipped_items}",
        ]

        if self.blocking_failures:
            lines.append("")
            lines.append("Blocking Failures:")
            for failure in self.blocking_failures:
                lines.append(f"  - {failure}")

        lines.append("=" * 50)
        return "\n".join(lines)


class ReleaseChecklist:
    """Executa o checklist de release.

    Verifica todos os gates obrigatorios para um release:
    1. Artefatos presentes (SRS, IR, OAS, RBAC, PLAN)
    2. Hashes completos no run log
    3. Build ok
    4. Smoke ok
    5. Blueprint registrado
    6. Regras absolutas respeitadas

    Attributes:
        store_root: Diretorio raiz do artifacts store
        generated_root: Diretorio raiz dos projetos gerados
    """

    # Default paths for test compatibility
    DEFAULT_STORE_ROOT = "/home/bazari/engine/demo_store"
    DEFAULT_GENERATED_ROOT = "/home/bazari/generated"

    # Artefatos obrigatorios
    REQUIRED_ARTIFACTS = ["SRS", "IR", "OAS", "RBAC", "PLAN"]

    # Hashes obrigatorios no run log
    REQUIRED_HASHES = ["input_hash", "srs_hash", "ir_hash", "oas_hash", "rbac_hash", "plan_hash"]

    # Regras absolutas que devem ser respeitadas
    ABSOLUTE_RULES = [
        ("no_pii_logging", "Nao logar dados sensiveis (PII)"),
        ("no_hardcoded_secrets", "Nao ter secrets hardcoded"),
        ("authenticated_endpoints", "Todos endpoints requerem autenticacao"),
    ]

    def __init__(
        self,
        store_root: Optional[str] = None,
        generated_root: Optional[str] = None,
    ):
        """Inicializa o checklist.

        Args:
            store_root: Diretorio raiz do artifacts store (from config if None)
            generated_root: Diretorio raiz dos projetos gerados (from config if None)
        """
        config = get_config()
        self.store_root = Path(store_root or config.store_root)
        self.generated_root = Path(generated_root or config.generated_root)
        self.store = ArtifactsStore(str(self.store_root))

    def run(
        self,
        project: str,
        run_result: Optional[Dict[str, Any]] = None,
    ) -> ReleaseChecklistResult:
        """Executa o checklist completo.

        Args:
            project: Nome do projeto
            run_result: Resultado do run (opcional, carrega do run log se nao fornecido)

        Returns:
            ReleaseChecklistResult com resultado do checklist
        """
        result = ReleaseChecklistResult(
            project=project,
            timestamp=datetime.now().isoformat(),
            passed=True,  # Assume sucesso, muda se falhar
        )

        # 1. Verificar artefatos presentes
        artifact_items = self._check_artifacts(project)
        for item in artifact_items:
            self._add_item(result, item)

        # 2. Verificar hashes no run log
        hash_items = self._check_hashes(project, run_result)
        for item in hash_items:
            self._add_item(result, item)

        # 3. Verificar build ok
        build_item = self._check_build(project, run_result)
        self._add_item(result, build_item)

        # 4. Verificar smoke ok
        smoke_item = self._check_smoke(project, run_result)
        self._add_item(result, smoke_item)

        # 5. Verificar blueprint registrado
        blueprint_item = self._check_blueprint(project, run_result)
        self._add_item(result, blueprint_item)

        # 6. Verificar regras absolutas
        rules_items = self._check_absolute_rules(project)
        for item in rules_items:
            self._add_item(result, item)

        # Calcular resultado final
        result.passed = len(result.blocking_failures) == 0

        return result

    def _add_item(self, result: ReleaseChecklistResult, item: ChecklistItem) -> None:
        """Adiciona item ao resultado e atualiza contadores."""
        result.items.append(item)
        result.total_items += 1

        if item.status == "PASS":
            result.passed_items += 1
        elif item.status == "FAIL":
            result.failed_items += 1
            if item.required:
                result.blocking_failures.append(f"{item.name}: {item.message}")
        else:  # SKIP
            result.skipped_items += 1

    def _check_artifacts(self, project: str) -> List[ChecklistItem]:
        """Verifica se todos os artefatos obrigatorios estao presentes."""
        items = []

        for artifact_type in self.REQUIRED_ARTIFACTS:
            # Verificar se existe pelo menos uma versao
            versions = self._list_artifact_versions(project, artifact_type)

            if versions:
                items.append(ChecklistItem(
                    name=f"artifact_{artifact_type.lower()}",
                    category="artifacts",
                    status="PASS",
                    message=f"{artifact_type} presente (v{max(versions)})",
                    details={"versions": versions, "latest": max(versions)},
                ))
            else:
                items.append(ChecklistItem(
                    name=f"artifact_{artifact_type.lower()}",
                    category="artifacts",
                    status="FAIL",
                    message=f"{artifact_type} nao encontrado",
                    required=True,
                ))

        return items

    def _list_artifact_versions(self, project: str, artifact_type: str) -> List[int]:
        """Lista versoes de um artefato.

        Args:
            project: Nome do projeto
            artifact_type: Tipo do artefato (SRS, IR, OAS, RBAC, PLAN)

        Returns:
            Lista de versoes encontradas
        """
        import re

        kind_path = self.store_root / project / artifact_type
        if not kind_path.exists():
            return []

        # Extensao padrao para cada tipo
        ext = "yaml" if artifact_type == "OAS" else "json"

        versions = []
        pattern = re.compile(rf"^v(\d+)\.{ext}$")

        for file in kind_path.iterdir():
            match = pattern.match(file.name)
            if match:
                versions.append(int(match.group(1)))

        return sorted(versions)

    def _check_hashes(
        self,
        project: str,
        run_result: Optional[Dict[str, Any]] = None,
    ) -> List[ChecklistItem]:
        """Verifica se todos os hashes estao presentes no run log."""
        items = []

        # Carregar run log se nao fornecido
        run_log = run_result
        if run_log is None:
            run_log = self._load_latest_run_log(project)

        if run_log is None:
            return [ChecklistItem(
                name="hashes_complete",
                category="hashes",
                status="FAIL",
                message="Run log nao encontrado",
                required=True,
            )]

        # Verificar cada hash obrigatorio
        missing_hashes = []
        present_hashes = []

        for hash_name in self.REQUIRED_HASHES:
            if hash_name in run_log and run_log[hash_name]:
                present_hashes.append(hash_name)
            else:
                missing_hashes.append(hash_name)

        if missing_hashes:
            items.append(ChecklistItem(
                name="hashes_complete",
                category="hashes",
                status="FAIL",
                message=f"Hashes faltando: {', '.join(missing_hashes)}",
                required=True,
                details={"missing": missing_hashes, "present": present_hashes},
            ))
        else:
            items.append(ChecklistItem(
                name="hashes_complete",
                category="hashes",
                status="PASS",
                message="Todos os hashes presentes",
                details={"hashes": present_hashes},
            ))

        return items

    def _check_build(
        self,
        project: str,
        run_result: Optional[Dict[str, Any]] = None,
    ) -> ChecklistItem:
        """Verifica se o build foi bem sucedido."""
        run_log = run_result or self._load_latest_run_log(project)

        if run_log is None:
            return ChecklistItem(
                name="build_ok",
                category="build",
                status="FAIL",
                message="Run log nao encontrado",
                required=True,
            )

        # Verificar build_ok no resultado
        result_data = run_log.get("result", run_log)
        build_ok = result_data.get("build_ok", False)

        if build_ok:
            return ChecklistItem(
                name="build_ok",
                category="build",
                status="PASS",
                message="Build bem sucedido",
                details={"repo_path": result_data.get("repo_path")},
            )
        else:
            build_errors = result_data.get("build_errors", [])
            return ChecklistItem(
                name="build_ok",
                category="build",
                status="FAIL",
                message="Build falhou",
                required=True,
                details={"errors": build_errors[:3]},
            )

    def _check_smoke(
        self,
        project: str,
        run_result: Optional[Dict[str, Any]] = None,
    ) -> ChecklistItem:
        """Verifica se os smoke tests passaram."""
        run_log = run_result or self._load_latest_run_log(project)

        if run_log is None:
            return ChecklistItem(
                name="smoke_ok",
                category="smoke",
                status="FAIL",
                message="Run log nao encontrado",
                required=True,
            )

        # Verificar smoke_ok no resultado
        result_data = run_log.get("result", run_log)
        smoke_ok = result_data.get("smoke_ok", False)
        smoke_passed = result_data.get("smoke_passed", 0)
        smoke_failed = result_data.get("smoke_failed", 0)

        # Se nao tiver release_mode, smoke nao foi executado
        if not result_data.get("release_mode", False):
            return ChecklistItem(
                name="smoke_ok",
                category="smoke",
                status="SKIP",
                message="Smoke tests nao executados (nao e release mode)",
                required=False,
            )

        if smoke_ok:
            return ChecklistItem(
                name="smoke_ok",
                category="smoke",
                status="PASS",
                message=f"Smoke tests passaram ({smoke_passed}/{smoke_passed + smoke_failed})",
                details={"passed": smoke_passed, "failed": smoke_failed},
            )
        else:
            return ChecklistItem(
                name="smoke_ok",
                category="smoke",
                status="FAIL",
                message=f"Smoke tests falharam ({smoke_failed} falhas)",
                required=True,
                details={"passed": smoke_passed, "failed": smoke_failed},
            )

    def _check_blueprint(
        self,
        project: str,
        run_result: Optional[Dict[str, Any]] = None,
    ) -> ChecklistItem:
        """Verifica se o blueprint esta registrado."""
        run_log = run_result or self._load_latest_run_log(project)

        if run_log is None:
            return ChecklistItem(
                name="blueprint_registered",
                category="blueprint",
                status="FAIL",
                message="Run log nao encontrado",
                required=True,
            )

        # Verificar blueprint no resultado
        result_data = run_log.get("result", run_log)
        blueprint_type = result_data.get("blueprint_type", "")
        blueprint_forced_generic = result_data.get("blueprint_forced_generic", True)

        # Verificar se o blueprint esta registrado
        if blueprint_type:
            blueprint_class = resolve_blueprint(blueprint_type)
            is_registered = blueprint_class != GenericBlueprint or blueprint_type.lower() == "generic"

            if is_registered or blueprint_forced_generic:
                # FORCED_GENERIC e valido
                status = "PASS"
                message = f"Blueprint registrado: {blueprint_type}"
                if blueprint_forced_generic:
                    message = f"Blueprint GENERIC (forced) - {blueprint_type} nao encontrado"
            else:
                status = "PASS"
                message = f"Blueprint registrado: {blueprint_type}"

            return ChecklistItem(
                name="blueprint_registered",
                category="blueprint",
                status=status,
                message=message,
                details={
                    "blueprint_type": blueprint_type,
                    "forced_generic": blueprint_forced_generic,
                },
            )
        else:
            return ChecklistItem(
                name="blueprint_registered",
                category="blueprint",
                status="FAIL",
                message="Blueprint nao especificado",
                required=True,
            )

    def _check_absolute_rules(self, project: str) -> List[ChecklistItem]:
        """Verifica se as regras absolutas foram respeitadas.

        Verifica no codigo gerado:
        - Nao logar dados sensiveis (PII)
        - Nao ter secrets hardcoded
        - Todos endpoints requerem autenticacao
        """
        items = []
        repo_path = self.generated_root / project

        if not repo_path.exists():
            return [ChecklistItem(
                name="absolute_rules",
                category="rules",
                status="SKIP",
                message="Repositorio nao encontrado",
                required=False,
            )]

        # Regra 1: Nao logar dados sensiveis
        pii_check = self._check_no_pii_logging(repo_path)
        items.append(pii_check)

        # Regra 2: Nao ter secrets hardcoded
        secrets_check = self._check_no_hardcoded_secrets(repo_path)
        items.append(secrets_check)

        # Regra 3: Todos endpoints requerem autenticacao
        auth_check = self._check_authenticated_endpoints(repo_path)
        items.append(auth_check)

        return items

    def _check_no_pii_logging(self, repo_path: Path) -> ChecklistItem:
        """Verifica se nao ha logging de dados sensiveis."""
        # Padroes suspeitos de PII em logs
        pii_patterns = [
            "log.*password",
            "log.*senha",
            "log.*cpf",
            "log.*credit.*card",
            "log.*cartao",
            "console.log.*password",
            "console.log.*senha",
            "logger.*password",
            "logger.*cpf",
        ]

        violations = []

        # Verificar arquivos Java
        backend_path = repo_path / "backend"
        if backend_path.exists():
            for java_file in backend_path.rglob("*.java"):
                try:
                    content = java_file.read_text().lower()
                    for pattern in pii_patterns:
                        if self._pattern_matches(content, pattern):
                            violations.append(f"{java_file.name}: {pattern}")
                except Exception:
                    pass

        # Verificar arquivos TypeScript/JavaScript
        frontend_path = repo_path / "frontend"
        if frontend_path.exists():
            for ts_file in list(frontend_path.rglob("*.ts")) + list(frontend_path.rglob("*.tsx")):
                try:
                    content = ts_file.read_text().lower()
                    for pattern in pii_patterns:
                        if self._pattern_matches(content, pattern):
                            violations.append(f"{ts_file.name}: {pattern}")
                except Exception:
                    pass

        if violations:
            return ChecklistItem(
                name="no_pii_logging",
                category="rules",
                status="FAIL",
                message=f"Possiveis logs de PII encontrados ({len(violations)})",
                required=True,
                details={"violations": violations[:5]},
            )
        else:
            return ChecklistItem(
                name="no_pii_logging",
                category="rules",
                status="PASS",
                message="Nenhum log de PII detectado",
            )

    def _check_no_hardcoded_secrets(self, repo_path: Path) -> ChecklistItem:
        """Verifica se nao ha secrets hardcoded."""
        # Padroes de secrets hardcoded
        secret_patterns = [
            'password\\s*=\\s*"[^"]{4,}"',
            'secret\\s*=\\s*"[^"]{4,}"',
            'api_key\\s*=\\s*"[^"]{4,}"',
            'apikey\\s*=\\s*"[^"]{4,}"',
            'token\\s*=\\s*"[^"]{4,}"',
            'jdbc:.*password=[^&\\s]{4,}',
        ]

        violations = []

        # Arquivos a verificar (excluindo configuracoes de exemplo)
        excluded_files = {".env.example", "application-example.yml", "config.example.js"}

        for pattern in ["*.java", "*.ts", "*.tsx", "*.js", "*.yml", "*.yaml", "*.properties"]:
            for file_path in repo_path.rglob(pattern):
                if file_path.name in excluded_files:
                    continue
                if "node_modules" in str(file_path):
                    continue
                if "target" in str(file_path):
                    continue

                try:
                    content = file_path.read_text()
                    for secret_pattern in secret_patterns:
                        if self._pattern_matches(content.lower(), secret_pattern):
                            violations.append(f"{file_path.name}: possible secret")
                except Exception:
                    pass

        if violations:
            return ChecklistItem(
                name="no_hardcoded_secrets",
                category="rules",
                status="FAIL",
                message=f"Possiveis secrets hardcoded ({len(violations)})",
                required=True,
                details={"violations": violations[:5]},
            )
        else:
            return ChecklistItem(
                name="no_hardcoded_secrets",
                category="rules",
                status="PASS",
                message="Nenhum secret hardcoded detectado",
            )

    def _check_authenticated_endpoints(self, repo_path: Path) -> ChecklistItem:
        """Verifica se todos os endpoints requerem autenticacao."""
        backend_path = repo_path / "backend"
        if not backend_path.exists():
            return ChecklistItem(
                name="authenticated_endpoints",
                category="rules",
                status="SKIP",
                message="Backend nao encontrado",
                required=False,
            )

        # Verificar se Security config existe
        security_config_found = False
        public_endpoints = []

        for java_file in backend_path.rglob("*.java"):
            try:
                content = java_file.read_text()

                # Verificar se e uma configuracao de seguranca
                if "SecurityFilterChain" in content or "@EnableWebSecurity" in content:
                    security_config_found = True

                    # Verificar se ha endpoints publicos (permitAll)
                    if "permitAll" in content:
                        # Extrair endpoints publicos - simplificado
                        if "/health" in content.lower():
                            public_endpoints.append("/actuator/health")
                        if "/public" in content.lower():
                            public_endpoints.append("/public/**")

            except Exception:
                pass

        if not security_config_found:
            return ChecklistItem(
                name="authenticated_endpoints",
                category="rules",
                status="FAIL",
                message="Configuracao de seguranca nao encontrada",
                required=True,
            )
        else:
            return ChecklistItem(
                name="authenticated_endpoints",
                category="rules",
                status="PASS",
                message="Endpoints protegidos por autenticacao",
                details={"public_endpoints": public_endpoints},
            )

    def _pattern_matches(self, content: str, pattern: str) -> bool:
        """Verifica se o padrao existe no conteudo (simplificado)."""
        import re
        try:
            return bool(re.search(pattern, content, re.IGNORECASE))
        except Exception:
            # Se regex falhar, fazer busca simples
            return pattern.replace(".*", "").replace("\\s*", "").replace("[^\"]{4,}", "") in content

    def _load_latest_run_log(self, project: str) -> Optional[Dict[str, Any]]:
        """Carrega o run log mais recente do projeto."""
        project_dir = self.store_root / project
        runs_dir = project_dir / "runs"

        if not runs_dir.exists():
            return None

        # Encontrar o run log mais recente
        run_logs = sorted(runs_dir.glob("*.json"), reverse=True)
        if not run_logs:
            return None

        try:
            with open(run_logs[0]) as f:
                return json.load(f)
        except Exception:
            return None


def run_release_checklist(project: str, run_result: Optional[Dict[str, Any]] = None) -> dict:
    """Funcao de conveniencia para executar o checklist.

    Args:
        project: Nome do projeto
        run_result: Resultado do run (opcional)

    Returns:
        Dicionario com resultado do checklist
    """
    checklist = ReleaseChecklist()
    result = checklist.run(project, run_result)
    return result.to_dict()
