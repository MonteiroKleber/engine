"""Repo Generator - Cria estrutura de projeto a partir dos templates."""

import os
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from config import get_config


class ReleaseFailureCategory(Enum):
    """Categorias canônicas de falha de release.

    Status obrigatórios para classificação de falhas em modo --release.
    Toda execução em --release DEVE terminar com exatamente UM destes status.
    """
    BUILD_FAILED = "BUILD_FAILED"
    DOCKER_UP_FAILED = "DOCKER_UP_FAILED"
    SMOKE_FAILED = "SMOKE_FAILED"
    POLICY_FAILED = "POLICY_FAILED"
    UNKNOWN_RELEASE_FAILED = "UNKNOWN_RELEASE_FAILED"


class RepoGenerator:
    """Gera repositório de projeto copiando templates base.

    Copia os templates estáticos para um novo diretório de projeto,
    criando a estrutura:
        {output_root}/{project}/
        ├── backend/       (from spring-boot template)
        ├── frontend/      (from react-vite template)
        ├── db/            (from postgres-flyway template)
        └── docker-compose.yml (from docker template)
    """

    # Mapeamento de template para diretório destino
    TEMPLATE_MAPPING = {
        "spring-boot": "backend",
        "react-vite": "frontend",
        "postgres-flyway": "db",
    }

    def __init__(
        self,
        templates_root: Optional[str] = None,
        output_root: Optional[str] = None,
    ) -> None:
        """Inicializa o gerador.

        Args:
            templates_root: Diretório raiz dos templates (from config if None)
            output_root: Diretório raiz para projetos gerados (from config if None)
        """
        config = get_config()
        self.templates_root = Path(templates_root or config.templates_root)
        self.output_root = Path(output_root or config.generated_root)

    def create_repo(self, project: str, exec_id: Optional[str] = None) -> Path:
        """Cria repositório para um projeto.

        Args:
            project: Nome do projeto
            exec_id: ID de execução para isolar volume do DB (opcional).
                     Se fornecido, o volume postgres será nomeado com este ID
                     para evitar conflitos entre execuções.

        Returns:
            Path do diretório criado

        Raises:
            ValueError: Se project estiver vazio
            FileNotFoundError: Se templates_root não existir
            FileExistsError: Se o projeto já existir
        """
        if not project or not project.strip():
            raise ValueError("Project name cannot be empty")

        if not self.templates_root.exists():
            raise FileNotFoundError(
                f"Templates root not found: {self.templates_root}"
            )

        project_dir = self.output_root / project

        if project_dir.exists():
            raise FileExistsError(f"Project already exists: {project_dir}")

        # Criar diretório do projeto
        project_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copiar templates mapeados
            for template_name, dest_name in self.TEMPLATE_MAPPING.items():
                self._copy_template(template_name, project_dir / dest_name)

            # Copiar arquivos docker (com exec_id para volume isolado)
            self._copy_docker_files(project_dir, exec_id=exec_id)

            return project_dir

        except Exception as e:
            # Limpar em caso de erro
            if project_dir.exists():
                shutil.rmtree(project_dir)
            raise e

    def _copy_template(self, template_name: str, dest: Path) -> None:
        """Copia um template para o destino.

        Args:
            template_name: Nome do template (diretório em templates_root)
            dest: Caminho de destino
        """
        src = self.templates_root / template_name

        if not src.exists():
            raise FileNotFoundError(f"Template not found: {src}")

        shutil.copytree(src, dest)

    def _copy_docker_files(
        self, project_dir: Path, exec_id: Optional[str] = None
    ) -> None:
        """Copia arquivos Docker para o projeto.

        Args:
            project_dir: Diretório do projeto
            exec_id: ID de execução para isolar volume do DB.
                     Se fornecido, substitui 'postgres_data' por
                     'postgres_data_<exec_id>' no docker-compose.yml
        """
        docker_src = self.templates_root / "docker"

        if not docker_src.exists():
            raise FileNotFoundError(f"Docker template not found: {docker_src}")

        # Copiar docker-compose.yml (com substituição de volume se exec_id fornecido)
        compose_src = docker_src / "docker-compose.yml"
        if compose_src.exists():
            compose_content = compose_src.read_text(encoding="utf-8")

            # Se exec_id fornecido, substituir nome do volume para isolamento
            if exec_id:
                # Substituir o nome do volume em todas as ocorrências
                # Ex: postgres_data -> postgres_data_petclinic_abc123
                old_volume = "postgres_data"
                new_volume = f"postgres_data_{exec_id}"
                compose_content = compose_content.replace(old_volume, new_volume)

            # Escrever o compose modificado
            (project_dir / "docker-compose.yml").write_text(
                compose_content, encoding="utf-8"
            )

        # Copiar docker-compose.dev.yml
        compose_dev_src = docker_src / "docker-compose.dev.yml"
        if compose_dev_src.exists():
            shutil.copy2(compose_dev_src, project_dir / "docker-compose.dev.yml")

        # Copiar Dockerfiles para o diretório docker/
        docker_dir = project_dir / "docker"
        docker_dir.mkdir(exist_ok=True)

        for file_name in ["Dockerfile.backend", "Dockerfile.frontend", "nginx.conf"]:
            src_file = docker_src / file_name
            if src_file.exists():
                shutil.copy2(src_file, docker_dir / file_name)

        # Copiar .env.example
        env_src = docker_src / ".env.example"
        if env_src.exists():
            shutil.copy2(env_src, project_dir / ".env.example")

    def repo_exists(self, project: str) -> bool:
        """Verifica se um projeto já existe.

        Args:
            project: Nome do projeto

        Returns:
            True se o projeto existir
        """
        return (self.output_root / project).exists()

    def delete_repo(self, project: str) -> None:
        """Remove um repositório existente.

        Args:
            project: Nome do projeto

        Raises:
            FileNotFoundError: Se o projeto não existir
        """
        project_dir = self.output_root / project

        if not project_dir.exists():
            raise FileNotFoundError(f"Project not found: {project_dir}")

        shutil.rmtree(project_dir)

    def get_repo_path(self, project: str) -> Optional[Path]:
        """Retorna o path de um projeto se existir.

        Args:
            project: Nome do projeto

        Returns:
            Path do projeto ou None se não existir
        """
        project_dir = self.output_root / project
        return project_dir if project_dir.exists() else None

    def move_to_failed(
        self,
        project: str,
        category: Optional[ReleaseFailureCategory] = None,
    ) -> Optional[Path]:
        """Move um repositório com falha para _failed/ em vez de deletar.

        Preserva logs, saída do build e arquivos para debug/auditoria.
        Formato: _failed/<CATEGORY>/<project>_<timestamp>/

        Args:
            project: Nome do projeto
            category: Categoria canônica da falha (BUILD_FAILED, DOCKER_UP_FAILED, etc.)
                     Se não especificada, usa UNKNOWN_RELEASE_FAILED

        Returns:
            Path do diretório de destino, ou None se projeto não existe
        """
        project_dir = self.output_root / project

        if not project_dir.exists():
            return None

        # Determinar categoria (default: UNKNOWN_RELEASE_FAILED)
        if category is None:
            category = ReleaseFailureCategory.UNKNOWN_RELEASE_FAILED

        # Criar diretório _failed/<CATEGORY>/ se não existir
        failed_root = self.output_root / "_failed" / category.value
        failed_root.mkdir(parents=True, exist_ok=True)

        # Gerar nome único com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        failed_name = f"{project}_{timestamp}"
        failed_dir = failed_root / failed_name

        # Mover (não copiar) para preservar espaço
        shutil.move(str(project_dir), str(failed_dir))

        return failed_dir

    def cleanup_old_failed(self, max_age_days: int = 7) -> int:
        """Remove repositórios com falha antigos.

        Args:
            max_age_days: Idade máxima em dias para manter

        Returns:
            Número de diretórios removidos
        """
        failed_root = self.output_root / "_failed"
        if not failed_root.exists():
            return 0

        removed = 0
        now = datetime.now()

        for item in failed_root.iterdir():
            if not item.is_dir():
                continue

            # Extrair timestamp do nome (projeto_YYYYMMDD_HHMMSS)
            parts = item.name.rsplit("_", 2)
            if len(parts) >= 3:
                try:
                    date_str = parts[-2]
                    item_date = datetime.strptime(date_str, "%Y%m%d")
                    age = (now - item_date).days

                    if age > max_age_days:
                        shutil.rmtree(item)
                        removed += 1
                except (ValueError, IndexError):
                    # Nome não segue o padrão, ignorar
                    pass

        return removed


def create_repo(
    project: str,
    templates_root: Optional[str] = None,
    output_root: Optional[str] = None,
) -> Path:
    """Função de conveniência para criar repositório.

    Args:
        project: Nome do projeto
        templates_root: Diretório raiz dos templates (from config if None)
        output_root: Diretório raiz para projetos gerados (from config if None)

    Returns:
        Path do diretório criado
    """
    generator = RepoGenerator(templates_root, output_root)
    return generator.create_repo(project)
