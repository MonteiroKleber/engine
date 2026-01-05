"""Diagnostic Report Generator - Gera relatórios de diagnóstico para falhas de release.

Gera um relatório legível por humanos que explica:
- O que falhou
- Por que provavelmente falhou
- Como diagnosticar
- Quais ações executar

Este relatório é gerado APENAS quando um release falha.
NÃO substitui Run Log nem Release Report existentes.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from version import __version__


# Mapeamento de status canônicos para causas prováveis
PROBABLE_CAUSES = {
    "BUILD_FAILED": [
        "Erro de compilação no frontend ou backend",
        "Dependências ausentes ou incompatíveis",
        "Versão incompatível de runtime (Node.js, Java, etc.)",
        "Código gerado com erros de sintaxe ou tipagem",
    ],
    "DOCKER_UP_FAILED": [
        "Docker daemon não está rodando",
        "Imagens não foram buildadas (docker compose build não executado)",
        "Portas já em uso (5432, 8080, 3000)",
        "Ambiente sem recursos suficientes (memória, disco)",
        "Timeout ao aguardar containers subirem",
    ],
    "SMOKE_FAILED": [
        "Serviço iniciou mas endpoint não respondeu a tempo",
        "Configuração incorreta de rota ou porta",
        "Tempo de inicialização maior que o permitido",
        "Erro de conexão com banco de dados",
    ],
    "POLICY_FAILED": [
        "Violação de política de segurança",
        "Artefatos não passaram validação",
        "Configuração de RBAC inválida",
    ],
    "UNKNOWN_RELEASE_FAILED": [
        "Erro inesperado durante o release",
        "Exceção não tratada no pipeline",
        "Falha de infraestrutura",
    ],
}

# Mapeamento de status canônicos para ações sugeridas
SUGGESTED_ACTIONS = {
    "BUILD_FAILED": [
        "Verificar logs de build no run log",
        "cd <repo_path> && npm run build (frontend)",
        "cd <repo_path>/backend && mvn compile (backend)",
        "Verificar versões de Node.js e Java instaladas",
    ],
    "DOCKER_UP_FAILED": [
        "docker info",
        "cd <failed_repo_path> && docker compose build",
        "lsof -i :5432 -i :8080 -i :3000",
        "cd <failed_repo_path> && docker compose logs --tail=100",
        "docker compose ps",
    ],
    "SMOKE_FAILED": [
        "docker compose ps",
        "curl -v http://localhost:8080/actuator/health",
        "curl -v http://localhost:3000/",
        "cd <failed_repo_path> && docker compose logs --tail=100",
    ],
    "POLICY_FAILED": [
        "Verificar validação de artefatos no run log",
        "Revisar configuração de RBAC",
        "Verificar políticas de segurança aplicadas",
    ],
    "UNKNOWN_RELEASE_FAILED": [
        "Verificar run log completo para detalhes do erro",
        "Verificar logs do sistema",
        "Tentar executar novamente com --verbose (se disponível)",
    ],
}


@dataclass
class DiagnosticReport:
    """Relatório de diagnóstico para falha de release."""

    # Identificação
    project: str
    final_status: str
    engine_version: str
    duration_ms: float
    timestamp: str

    # Evidências
    build_ok: bool
    docker_compose_ok: bool
    smoke_ok: bool
    docker_ps_snapshot: str
    docker_logs_backend_tail: str
    docker_logs_frontend_tail: str
    errors: List[str]

    # Caminhos
    repo_path: str
    failed_repo_path: str

    def _generate_probable_cause(self) -> str:
        """Gera texto descritivo da causa provável."""
        status = self.final_status

        if status == "DOCKER_UP_FAILED":
            # Analisar evidências para refinar causa
            if not self.docker_ps_snapshot or self.docker_ps_snapshot.strip() == "NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS":
                return (
                    "Timeout ao aguardar docker compose subir os containers. "
                    "Nenhum container ativo foi detectado dentro do tempo limite configurado. "
                    "Isso é indicativo de que o comando docker compose up não conseguiu "
                    "iniciar os serviços, provavelmente devido a imagens não buildadas "
                    "ou Docker daemon não disponível."
                )
            return (
                "O comando docker compose up falhou antes de todos os containers "
                "ficarem operacionais. Isso pode indicar erro de configuração, "
                "portas em conflito ou recursos insuficientes."
            )

        elif status == "BUILD_FAILED":
            return (
                "O build do projeto falhou durante a compilação. "
                "Isso geralmente indica erro de código gerado, dependências "
                "ausentes ou incompatibilidade de versões de runtime."
            )

        elif status == "SMOKE_FAILED":
            return (
                "Os containers subiram mas os smoke tests falharam. "
                "Isso indica que os serviços não estão respondendo corretamente "
                "nos endpoints esperados, provavelmente devido a tempo de "
                "inicialização insuficiente ou erro de configuração."
            )

        elif status == "POLICY_FAILED":
            return (
                "Uma violação de política foi detectada durante o release. "
                "Isso indica que algum artefato ou configuração não passou "
                "nas validações de segurança ou conformidade."
            )

        else:
            return (
                "Ocorreu um erro inesperado durante o processo de release. "
                "Verifique o run log para detalhes completos do erro."
            )

    def _generate_objective_evidence(self) -> List[str]:
        """Gera lista de evidências objetivas."""
        evidence = []

        # Build status
        evidence.append(f"Build frontend: {'OK' if self.build_ok else 'FAILED'}")
        evidence.append(f"Build backend: {'OK' if self.build_ok else 'FAILED'}")

        # Docker status
        evidence.append(f"Docker compose up: {'OK' if self.docker_compose_ok else 'FAILED'}")

        # Container status
        if self.docker_ps_snapshot:
            lines = self.docker_ps_snapshot.strip().split("\n")
            if len(lines) <= 1:
                evidence.append("docker compose ps: vazio (nenhum container rodando)")
            else:
                evidence.append(f"docker compose ps: {len(lines) - 1} container(s) listado(s)")
        else:
            evidence.append("docker compose ps: não disponível")

        # Logs
        if self.docker_logs_backend_tail:
            evidence.append("Logs backend: disponíveis")
        else:
            evidence.append("Logs backend: vazios ou não disponíveis")

        if self.docker_logs_frontend_tail:
            evidence.append("Logs frontend: disponíveis")
        else:
            evidence.append("Logs frontend: vazios ou não disponíveis")

        # Smoke tests
        evidence.append(f"Smoke tests: {'OK' if self.smoke_ok else 'FAILED ou não executados'}")

        return evidence

    def _generate_possible_causes(self) -> List[str]:
        """Gera lista de possíveis causas baseada no status."""
        return PROBABLE_CAUSES.get(self.final_status, PROBABLE_CAUSES["UNKNOWN_RELEASE_FAILED"])

    def _generate_suggested_actions(self) -> List[str]:
        """Gera lista de ações sugeridas com paths substituídos."""
        actions = SUGGESTED_ACTIONS.get(self.final_status, SUGGESTED_ACTIONS["UNKNOWN_RELEASE_FAILED"])

        # Substituir placeholders
        result = []
        for action in actions:
            action = action.replace("<repo_path>", self.repo_path)
            action = action.replace("<failed_repo_path>", self.failed_repo_path or self.repo_path)
            result.append(action)

        return result

    def to_markdown(self) -> str:
        """Gera o relatório em formato Markdown."""
        lines = [
            "# Diagnostic Report",
            "",
            "---",
            "",
            "## Status",
            "",
            "```",
            f"STATUS FINAL: {self.final_status}",
            f"PROJECT: {self.project}",
            f"ENGINE VERSION: {self.engine_version}",
            f"DURATION: {self.duration_ms:.0f}ms",
            "```",
            "",
            "---",
            "",
            "## Causa Provável",
            "",
            self._generate_probable_cause(),
            "",
            "---",
            "",
            "## Evidências Objetivas",
            "",
        ]

        for evidence in self._generate_objective_evidence():
            lines.append(f"- {evidence}")

        lines.extend([
            "",
            "---",
            "",
            "## Possíveis Causas",
            "",
        ])

        for i, cause in enumerate(self._generate_possible_causes(), 1):
            lines.append(f"{i}. {cause}")

        lines.extend([
            "",
            "---",
            "",
            "## Ações Sugeridas",
            "",
        ])

        for i, action in enumerate(self._generate_suggested_actions(), 1):
            lines.append(f"{i}. `{action}`")

        lines.extend([
            "",
            "---",
            "",
            "## Evidência Preservada",
            "",
            "```",
            "REPO PRESERVADO EM:",
            f"  {self.failed_repo_path or 'N/A'}",
            "```",
            "",
        ])

        # Adicionar erros se existirem
        if self.errors:
            lines.extend([
                "---",
                "",
                "## Erros Registrados",
                "",
            ])
            for error in self.errors[:5]:
                lines.append(f"- {error}")
            lines.append("")

        lines.extend([
            "---",
            "",
            f"*Gerado por Bazari Engine v{self.engine_version}*",
            f"*Timestamp: {self.timestamp}*",
        ])

        return "\n".join(lines)


class DiagnosticReportGenerator:
    """Gerador de Diagnostic Reports para falhas de release.

    Gera relatórios de diagnóstico APENAS quando um release falha.
    Não substitui Run Log nem Release Report existentes.
    """

    def __init__(self, store_root: str, generated_root: str = "/home/bazari/generated"):
        """Inicializa o gerador.

        Args:
            store_root: Diretório raiz do artifacts store
            generated_root: Diretório raiz dos projetos gerados
        """
        self.store_root = Path(store_root)
        self.generated_root = Path(generated_root)

    def should_generate(self, run_result: Dict[str, Any]) -> bool:
        """Verifica se deve gerar o diagnostic report.

        Retorna True apenas se:
        - O release falhou (success=False)
        - Está em modo release (release_mode=True)

        Args:
            run_result: Resultado do run_release()

        Returns:
            True se deve gerar, False caso contrário
        """
        return (
            not run_result.get("success", True) and
            run_result.get("release_mode", False)
        )

    def generate(self, project: str, run_result: Dict[str, Any]) -> Optional[DiagnosticReport]:
        """Gera um DiagnosticReport a partir do resultado de run_release().

        Args:
            project: Nome do projeto
            run_result: Resultado do run_release() como dict

        Returns:
            DiagnosticReport se deve gerar, None caso contrário
        """
        if not self.should_generate(run_result):
            return None

        return DiagnosticReport(
            project=project,
            final_status=run_result.get("final_status", "UNKNOWN_RELEASE_FAILED"),
            engine_version=__version__,
            duration_ms=run_result.get("duration_ms", 0.0),
            timestamp=datetime.now().isoformat(),
            build_ok=run_result.get("build_ok", False),
            docker_compose_ok=run_result.get("docker_compose_ok", False),
            smoke_ok=run_result.get("smoke_ok", False),
            docker_ps_snapshot=run_result.get("docker_ps_snapshot", ""),
            docker_logs_backend_tail=run_result.get("docker_logs_backend_tail", ""),
            docker_logs_frontend_tail=run_result.get("docker_logs_frontend_tail", ""),
            errors=run_result.get("errors", []),
            repo_path=run_result.get("repo_path", str(self.generated_root / project)),
            failed_repo_path=run_result.get("failed_repo_path", ""),
        )

    def generate_and_save(
        self,
        project: str,
        run_result: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """Gera e salva o DiagnosticReport.

        Args:
            project: Nome do projeto
            run_result: Resultado do run_release()

        Returns:
            Dict com caminho do arquivo salvo, ou None se não gerou
        """
        report = self.generate(project, run_result)

        if report is None:
            return None

        # Diretório de saída (mesmo do release_report)
        output_dir = self.store_root / project / "releases"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Gerar timestamp para nome do arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = output_dir / f"diagnostic_report_{timestamp}.md"

        # Salvar markdown
        md_path.write_text(report.to_markdown())

        return {
            "markdown": str(md_path),
        }


def generate_diagnostic_report(
    project: str,
    run_result: Dict[str, Any],
    store_root: str,
) -> Optional[Dict[str, str]]:
    """Função de conveniência para gerar diagnostic report.

    Args:
        project: Nome do projeto
        run_result: Resultado do run_release()
        store_root: Diretório raiz do store

    Returns:
        Dict com caminho do arquivo, ou None se não gerou
    """
    generator = DiagnosticReportGenerator(store_root)
    return generator.generate_and_save(project, run_result)
