"""Store de artefatos com versionamento."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ArtifactsStore:
    """Gerencia persistência de artefatos com layout fixo.

    Layout:
        store_data/{project}/SRS/vN.json
        store_data/{project}/IR/vN.json
        store_data/{project}/OAS/vN.yaml
        store_data/{project}/RBAC/vN.json
        store_data/{project}/PLAN/vN.json
        store_data/{project}/logs/
        store_data/{project}/runs/
    """

    # Mapeamento de kind para extensão padrão
    KIND_EXTENSIONS = {
        "SRS": "json",
        "IR": "json",
        "RBAC": "json",
        "OAS": "yaml",
        "PLAN": "json",
    }

    def __init__(self, store_root: str = "./store_data") -> None:
        self.store_root = Path(store_root)
        self.store_root.mkdir(parents=True, exist_ok=True)

    def _get_project_path(self, project: str) -> Path:
        """Retorna o caminho do projeto."""
        return self.store_root / project

    def _get_kind_path(self, project: str, kind: str) -> Path:
        """Retorna o caminho do tipo de artefato."""
        project_path = self._get_project_path(project)
        return project_path / kind

    def _ensure_project_structure(self, project: str) -> None:
        """Garante que a estrutura do projeto existe."""
        project_path = self._get_project_path(project)
        (project_path / "SRS").mkdir(parents=True, exist_ok=True)
        (project_path / "IR").mkdir(parents=True, exist_ok=True)
        (project_path / "OAS").mkdir(parents=True, exist_ok=True)
        (project_path / "RBAC").mkdir(parents=True, exist_ok=True)
        (project_path / "PLAN").mkdir(parents=True, exist_ok=True)
        (project_path / "logs").mkdir(parents=True, exist_ok=True)
        (project_path / "runs").mkdir(parents=True, exist_ok=True)

    def _get_extension_for_kind(self, kind: str) -> str:
        """Retorna a extensão padrão para um tipo de artefato."""
        return self.KIND_EXTENSIONS.get(kind, "json")

    def _list_versions(self, project: str, kind: str, ext: Optional[str] = None) -> List[int]:
        """Lista todas as versões de um tipo de artefato."""
        kind_path = self._get_kind_path(project, kind)
        if not kind_path.exists():
            return []

        if ext is None:
            ext = self._get_extension_for_kind(kind)

        versions = []
        pattern = re.compile(rf"^v(\d+)\.{ext}$")
        for file in kind_path.iterdir():
            match = pattern.match(file.name)
            if match:
                versions.append(int(match.group(1)))

        return sorted(versions)

    def next_version(self, project: str, kind: str) -> int:
        """Retorna a próxima versão disponível para um tipo de artefato.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato (ex: 'SRS', 'blueprint')

        Returns:
            Próximo número de versão (começa em 1)
        """
        versions = self._list_versions(project, kind)
        if not versions:
            return 1
        return max(versions) + 1

    def save_artifact(
        self,
        project: str,
        kind: str,
        version: int,
        content_dict: Dict[str, Any],
    ) -> Path:
        """Salva um artefato com versionamento.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato (ex: 'SRS', 'blueprint')
            version: Número da versão
            content_dict: Conteúdo do artefato

        Returns:
            Caminho do arquivo salvo
        """
        self._ensure_project_structure(project)
        kind_path = self._get_kind_path(project, kind)
        kind_path.mkdir(parents=True, exist_ok=True)

        artifact_path = kind_path / f"v{version}.json"
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(content_dict, f, indent=2, ensure_ascii=False)

        return artifact_path

    def load_latest(self, project: str, kind: str) -> Optional[Dict[str, Any]]:
        """Carrega a versão mais recente de um tipo de artefato.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato (ex: 'SRS', 'blueprint')

        Returns:
            Conteúdo do artefato ou None se não existir
        """
        versions = self._list_versions(project, kind)
        if not versions:
            return None

        latest_version = max(versions)
        kind_path = self._get_kind_path(project, kind)
        artifact_path = kind_path / f"v{latest_version}.json"

        with open(artifact_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_version(
        self, project: str, kind: str, version: int
    ) -> Optional[Dict[str, Any]]:
        """Carrega uma versão específica de um artefato.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato
            version: Número da versão

        Returns:
            Conteúdo do artefato ou None se não existir
        """
        kind_path = self._get_kind_path(project, kind)
        artifact_path = kind_path / f"v{version}.json"

        if not artifact_path.exists():
            return None

        with open(artifact_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_run_log(
        self,
        execution_id: str,
        payload: Dict[str, Any],
        project: Optional[str] = None,
    ) -> Path:
        """Escreve log de execução.

        Args:
            execution_id: ID único da execução
            payload: Dados do log
            project: Nome do projeto (opcional, extrai do execution_id se não informado)

        Returns:
            Caminho do arquivo de log
        """
        # Usa project informado ou extrai do execution_id
        if project is None:
            # Assume formato: project_hash (ex: demo_abc123)
            # Pega tudo antes do último underscore
            parts = execution_id.rsplit("_", 1)
            project = parts[0] if len(parts) > 1 else "default"

        self._ensure_project_structure(project)
        runs_path = self._get_project_path(project) / "runs"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = runs_path / f"{execution_id}_{timestamp}.json"

        log_entry = {
            "execution_id": execution_id,
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        }

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

        return log_path

    def list_projects(self) -> List[str]:
        """Lista todos os projetos no store."""
        if not self.store_root.exists():
            return []

        return [
            d.name
            for d in self.store_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def list_artifacts(self, project: str, kind: str) -> List[Dict[str, Any]]:
        """Lista todos os artefatos de um tipo em um projeto.

        Returns:
            Lista de dicionários com version e path
        """
        ext = self._get_extension_for_kind(kind)
        versions = self._list_versions(project, kind, ext)
        kind_path = self._get_kind_path(project, kind)

        return [
            {"version": v, "path": str(kind_path / f"v{v}.{ext}")}
            for v in versions
        ]

    def save_text_artifact(
        self,
        project: str,
        kind: str,
        version: int,
        content_str: str,
        ext: str = "yaml",
    ) -> Path:
        """Salva um artefato de texto (YAML, etc) com versionamento.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato (ex: 'OAS')
            version: Número da versão
            content_str: Conteúdo do artefato como string
            ext: Extensão do arquivo (default: yaml)

        Returns:
            Caminho do arquivo salvo
        """
        self._ensure_project_structure(project)
        kind_path = self._get_kind_path(project, kind)
        kind_path.mkdir(parents=True, exist_ok=True)

        artifact_path = kind_path / f"v{version}.{ext}"
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(content_str)

        return artifact_path

    def load_text_artifact(
        self,
        project: str,
        kind: str,
        version: int,
        ext: str = "yaml",
    ) -> Optional[str]:
        """Carrega um artefato de texto por versão.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato
            version: Número da versão
            ext: Extensão do arquivo (default: yaml)

        Returns:
            Conteúdo do artefato como string ou None se não existir
        """
        kind_path = self._get_kind_path(project, kind)
        artifact_path = kind_path / f"v{version}.{ext}"

        if not artifact_path.exists():
            return None

        with open(artifact_path, "r", encoding="utf-8") as f:
            return f.read()

    def load_latest_text(
        self,
        project: str,
        kind: str,
        ext: str = "yaml",
    ) -> Optional[str]:
        """Carrega a versão mais recente de um artefato de texto.

        Args:
            project: Nome do projeto
            kind: Tipo do artefato
            ext: Extensão do arquivo (default: yaml)

        Returns:
            Conteúdo do artefato como string ou None se não existir
        """
        versions = self._list_versions(project, kind, ext)
        if not versions:
            return None

        latest_version = max(versions)
        return self.load_text_artifact(project, kind, latest_version, ext)
