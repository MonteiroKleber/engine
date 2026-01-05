"""Patch Engine - Aplica patches de código com segurança máxima.

REGRA ABSOLUTA: Só pode escrever em /home/bazari/generated/<project>/**

Bloqueios obrigatórios:
- Proibir tocar em /home/bazari/engine/**
- Proibir tocar em /home/bazari/templates/**
- Proibir path traversal (../)
- Proibir rewrite de arquivo inteiro (>80%)

Rollback: Patch inválido gera rollback imediato.
"""

import difflib
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PatchStatus(Enum):
    """Status de um patch."""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PatchSecurityError(Exception):
    """Erro de segurança do Patch Engine."""

    pass


@dataclass
class PatchOperation:
    """Uma operação de patch."""

    file_path: str
    operation: str  # "create", "modify", "delete"
    content: Optional[str] = None
    old_content: Optional[str] = None  # Para rollback


@dataclass
class PatchResult:
    """Resultado de aplicação de patches."""

    success: bool
    applied_count: int = 0
    failed_count: int = 0
    rolled_back: bool = False
    errors: List[str] = field(default_factory=list)
    operations: List[PatchOperation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "success": self.success,
            "applied_count": self.applied_count,
            "failed_count": self.failed_count,
            "rolled_back": self.rolled_back,
            "errors": self.errors,
        }


class PatchEngine:
    """Engine de patches com segurança blindada.

    REGRA ABSOLUTA: Só pode escrever em generated_root/<project>/**

    Attributes:
        generated_root: Diretório raiz onde projetos são gerados
        blocked_paths: Lista de paths absolutamente proibidos
        max_rewrite_ratio: Porcentagem máxima de reescrita permitida (0.0-1.0)
    """

    # Paths ABSOLUTAMENTE proibidos
    BLOCKED_PATHS = [
        "/home/bazari/engine",
        "/home/bazari/templates",
    ]

    def __init__(
        self,
        project: str,
        generated_root: str = "/home/bazari/generated",
        max_rewrite_ratio: float = 0.80,
    ) -> None:
        """Inicializa o Patch Engine.

        Args:
            project: Nome do projeto
            generated_root: Diretório raiz dos projetos gerados
            max_rewrite_ratio: Porcentagem máxima de reescrita (default: 80%)

        Raises:
            ValueError: Se project estiver vazio
        """
        if not project or not project.strip():
            raise ValueError("Project name cannot be empty")

        self.project = project
        self.generated_root = Path(generated_root).resolve()
        self.project_root = self.generated_root / project
        self.max_rewrite_ratio = max_rewrite_ratio

        # Backup para rollback
        self._backup_dir: Optional[Path] = None
        self._applied_operations: List[PatchOperation] = []

    # ==================== SECURITY GUARDS ====================

    def _validate_path(self, file_path: str) -> Path:
        """Valida e resolve um path de forma segura.

        Args:
            file_path: Caminho do arquivo (relativo ou absoluto)

        Returns:
            Path absoluto validado

        Raises:
            PatchSecurityError: Se o path for inválido ou proibido
        """
        # Detectar path traversal
        if ".." in file_path:
            raise PatchSecurityError(
                f"Path traversal detected: {file_path}"
            )

        # Normalizar path
        if os.path.isabs(file_path):
            target = Path(file_path).resolve()
        else:
            target = (self.project_root / file_path).resolve()

        # Verificar se está dentro do projeto
        try:
            target.relative_to(self.project_root)
        except ValueError:
            raise PatchSecurityError(
                f"Path outside project directory: {target}"
            )

        # Verificar paths bloqueados
        target_str = str(target)
        for blocked in self.BLOCKED_PATHS:
            if target_str.startswith(blocked):
                raise PatchSecurityError(
                    f"Access to blocked path: {blocked}"
                )

        return target

    def _check_rewrite_ratio(
        self, old_content: str, new_content: str, file_path: str
    ) -> None:
        """Verifica se o patch excede o limite de reescrita.

        Args:
            old_content: Conteúdo original
            new_content: Novo conteúdo
            file_path: Caminho do arquivo (para mensagem de erro)

        Raises:
            PatchSecurityError: Se exceder o limite de reescrita
        """
        if not old_content:
            return  # Arquivo novo, sem limite

        # Calcular similaridade usando difflib
        matcher = difflib.SequenceMatcher(None, old_content, new_content)
        similarity = matcher.ratio()
        change_ratio = 1.0 - similarity

        if change_ratio > self.max_rewrite_ratio:
            raise PatchSecurityError(
                f"Rewrite ratio too high ({change_ratio:.1%} > {self.max_rewrite_ratio:.0%}): {file_path}"
            )

    def _ensure_project_exists(self) -> None:
        """Garante que o diretório do projeto existe.

        Raises:
            FileNotFoundError: Se o projeto não existir
        """
        if not self.project_root.exists():
            raise FileNotFoundError(
                f"Project not found: {self.project_root}"
            )

    # ==================== BACKUP & ROLLBACK ====================

    def _create_backup(self, file_path: Path) -> None:
        """Cria backup de um arquivo para rollback.

        Args:
            file_path: Arquivo a ser backed up
        """
        if self._backup_dir is None:
            self._backup_dir = Path(tempfile.mkdtemp(prefix="patch_backup_"))

        if file_path.exists():
            # Criar estrutura de diretórios no backup
            relative = file_path.relative_to(self.project_root)
            backup_path = self._backup_dir / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)

    def _rollback(self) -> None:
        """Executa rollback de todas as operações aplicadas."""
        if not self._applied_operations:
            return

        for op in reversed(self._applied_operations):
            target = self._validate_path(op.file_path)

            try:
                if op.operation == "create":
                    # Remover arquivo criado
                    if target.exists():
                        target.unlink()
                elif op.operation == "modify":
                    # Restaurar conteúdo original
                    if op.old_content is not None:
                        target.write_text(op.old_content)
                elif op.operation == "delete":
                    # Restaurar arquivo deletado
                    if op.old_content is not None:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(op.old_content)
            except Exception:
                # Ignorar erros durante rollback
                pass

        # Limpar backup
        self._cleanup_backup()

    def _cleanup_backup(self) -> None:
        """Remove diretório de backup."""
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)
            self._backup_dir = None

    # ==================== PATCH OPERATIONS ====================

    def create_file(self, file_path: str, content: str) -> PatchOperation:
        """Cria um novo arquivo.

        Args:
            file_path: Caminho relativo ao projeto
            content: Conteúdo do arquivo

        Returns:
            PatchOperation executada

        Raises:
            PatchSecurityError: Se path for inválido
            FileExistsError: Se arquivo já existir
        """
        target = self._validate_path(file_path)

        if target.exists():
            raise FileExistsError(f"File already exists: {file_path}")

        # Criar diretórios se necessário
        target.parent.mkdir(parents=True, exist_ok=True)

        # Escrever arquivo
        target.write_text(content)

        op = PatchOperation(
            file_path=file_path,
            operation="create",
            content=content,
        )
        self._applied_operations.append(op)
        return op

    def modify_file(self, file_path: str, content: str) -> PatchOperation:
        """Modifica um arquivo existente.

        Args:
            file_path: Caminho relativo ao projeto
            content: Novo conteúdo

        Returns:
            PatchOperation executada

        Raises:
            PatchSecurityError: Se path for inválido ou reescrita exceder limite
            FileNotFoundError: Se arquivo não existir
        """
        target = self._validate_path(file_path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Ler conteúdo atual
        old_content = target.read_text()

        # Verificar limite de reescrita
        self._check_rewrite_ratio(old_content, content, file_path)

        # Criar backup
        self._create_backup(target)

        # Escrever novo conteúdo
        target.write_text(content)

        op = PatchOperation(
            file_path=file_path,
            operation="modify",
            content=content,
            old_content=old_content,
        )
        self._applied_operations.append(op)
        return op

    def delete_file(self, file_path: str) -> PatchOperation:
        """Remove um arquivo.

        Args:
            file_path: Caminho relativo ao projeto

        Returns:
            PatchOperation executada

        Raises:
            PatchSecurityError: Se path for inválido
            FileNotFoundError: Se arquivo não existir
        """
        target = self._validate_path(file_path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Ler conteúdo para rollback
        old_content = target.read_text()

        # Criar backup
        self._create_backup(target)

        # Remover arquivo
        target.unlink()

        op = PatchOperation(
            file_path=file_path,
            operation="delete",
            old_content=old_content,
        )
        self._applied_operations.append(op)
        return op

    def append_to_file(self, file_path: str, content: str) -> PatchOperation:
        """Adiciona conteúdo ao final de um arquivo.

        Args:
            file_path: Caminho relativo ao projeto
            content: Conteúdo a adicionar

        Returns:
            PatchOperation executada

        Raises:
            PatchSecurityError: Se path for inválido
            FileNotFoundError: Se arquivo não existir
        """
        target = self._validate_path(file_path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        old_content = target.read_text()
        new_content = old_content + content

        # Verificar limite de reescrita
        self._check_rewrite_ratio(old_content, new_content, file_path)

        # Criar backup
        self._create_backup(target)

        # Escrever
        target.write_text(new_content)

        op = PatchOperation(
            file_path=file_path,
            operation="modify",
            content=new_content,
            old_content=old_content,
        )
        self._applied_operations.append(op)
        return op

    def insert_in_file(
        self, file_path: str, content: str, after_line: Optional[int] = None
    ) -> PatchOperation:
        """Insere conteúdo em uma posição específica do arquivo.

        Args:
            file_path: Caminho relativo ao projeto
            content: Conteúdo a inserir
            after_line: Inserir após esta linha (1-based). None = início.

        Returns:
            PatchOperation executada

        Raises:
            PatchSecurityError: Se path for inválido
            FileNotFoundError: Se arquivo não existir
        """
        target = self._validate_path(file_path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        old_content = target.read_text()
        lines = old_content.splitlines(keepends=True)

        if after_line is None:
            # Inserir no início
            new_lines = [content + "\n"] + lines
        elif after_line >= len(lines):
            # Inserir no final
            new_lines = lines + [content + "\n"]
        else:
            # Inserir na posição
            new_lines = lines[:after_line] + [content + "\n"] + lines[after_line:]

        new_content = "".join(new_lines)

        # Verificar limite de reescrita
        self._check_rewrite_ratio(old_content, new_content, file_path)

        # Criar backup
        self._create_backup(target)

        # Escrever
        target.write_text(new_content)

        op = PatchOperation(
            file_path=file_path,
            operation="modify",
            content=new_content,
            old_content=old_content,
        )
        self._applied_operations.append(op)
        return op

    # ==================== BATCH OPERATIONS ====================

    def apply_patches(
        self, patches: List[Dict[str, Any]]
    ) -> PatchResult:
        """Aplica uma lista de patches de forma atômica.

        Args:
            patches: Lista de dicts com {operation, file_path, content?}

        Returns:
            PatchResult com status da operação

        Note:
            Se qualquer patch falhar, todos são revertidos (rollback).
        """
        self._ensure_project_exists()
        self._applied_operations = []
        result = PatchResult(success=False)

        try:
            for patch in patches:
                operation = patch.get("operation")
                file_path = patch.get("file_path")
                content = patch.get("content", "")

                if not operation or not file_path:
                    raise ValueError("Patch must have 'operation' and 'file_path'")

                if operation == "create":
                    op = self.create_file(file_path, content)
                elif operation == "modify":
                    op = self.modify_file(file_path, content)
                elif operation == "delete":
                    op = self.delete_file(file_path)
                elif operation == "append":
                    op = self.append_to_file(file_path, content)
                else:
                    raise ValueError(f"Unknown operation: {operation}")

                result.operations.append(op)
                result.applied_count += 1

            result.success = True
            self._cleanup_backup()

        except Exception as e:
            result.errors.append(str(e))
            result.failed_count = len(patches) - result.applied_count

            # ROLLBACK IMEDIATO
            self._rollback()
            result.rolled_back = True
            result.applied_count = 0

        return result

    # ==================== CONTEXT MANAGER ====================

    def __enter__(self) -> "PatchEngine":
        """Entra no contexto."""
        self._ensure_project_exists()
        self._applied_operations = []
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Sai do contexto, fazendo rollback se houve exceção."""
        if exc_type is not None:
            self._rollback()
            return False  # Re-raise exception

        self._cleanup_backup()
        return False
