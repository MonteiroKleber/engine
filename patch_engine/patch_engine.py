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
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.patch_manifest import (
    PatchManifest,
    PatchEntry,
    PatchPolicy,
    PatchManifestStore,
)
from observability.canonical_hash import compute_text_hash_sha256


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
    manifest_path: Optional[str] = None  # Path to PatchManifest if generated

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        result = {
            "success": self.success,
            "applied_count": self.applied_count,
            "failed_count": self.failed_count,
            "rolled_back": self.rolled_back,
            "errors": self.errors,
        }
        if self.manifest_path:
            result["manifest_path"] = self.manifest_path
        return result


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
        store_root: Optional[str] = None,
    ) -> None:
        """Inicializa o Patch Engine.

        Args:
            project: Nome do projeto
            generated_root: Diretório raiz dos projetos gerados
            max_rewrite_ratio: Porcentagem máxima de reescrita (default: 80%)
            store_root: Root for artifact storage (for PatchManifest). If None, uses ./store_data

        Raises:
            ValueError: Se project estiver vazio
        """
        if not project or not project.strip():
            raise ValueError("Project name cannot be empty")

        self.project = project
        self.generated_root = Path(generated_root).resolve()
        self.project_root = self.generated_root / project
        self.max_rewrite_ratio = max_rewrite_ratio
        self.store_root = store_root or "./store_data"

        # Backup para rollback
        self._backup_dir: Optional[Path] = None
        self._applied_operations: List[PatchOperation] = []

    # ==================== SECURITY GUARDS ====================

    _ENGINE_SLOT_START_RE = re.compile(r"@engine:([A-Za-z0-9_-]+):start")
    _ENGINE_SLOT_END_RE = re.compile(r"@engine:([A-Za-z0-9_-]+):end")

    def _extract_engine_slots(self, content: str, file_path: str) -> Dict[str, str]:
        """Extrai slots @engine:*:start/@engine:*:end e retorna o conteúdo interno.

        Regras:
        - Suporta marcadores em comentários JS (// ...) e JSX ({/* ... */})
          desde que a linha contenha "@engine:<name>:start" / ":end".
        - Não permite nesting de slots (determinístico).
        - Não permite slots duplicados com o mesmo nome (determinístico).

        Args:
            content: Conteúdo do arquivo.
            file_path: Caminho (para mensagens de erro).

        Returns:
            Dict[slot_name, slot_inner_content] com o conteúdo ENTRE start e end (sem os marcadores).

        Raises:
            PatchSecurityError: Se houver marcadores inválidos/malformados.
        """
        slots: Dict[str, str] = {}
        open_slot: Optional[str] = None
        start_line_idx: Optional[int] = None

        lines = content.splitlines(keepends=True)
        for idx, line in enumerate(lines):
            m_start = self._ENGINE_SLOT_START_RE.search(line)
            m_end = self._ENGINE_SLOT_END_RE.search(line)

            if m_start and m_end:
                raise PatchSecurityError(
                    f"Invalid slot markers (start+end on same line): {file_path}"
                )

            if m_start:
                slot_name = m_start.group(1)
                if open_slot is not None:
                    raise PatchSecurityError(
                        f"Nested slot markers are not supported (open '{open_slot}', found '{slot_name}'): {file_path}"
                    )
                if slot_name in slots:
                    raise PatchSecurityError(
                        f"Duplicate slot marker for '{slot_name}': {file_path}"
                    )
                open_slot = slot_name
                start_line_idx = idx
                continue

            if m_end:
                slot_name = m_end.group(1)
                if open_slot is None or start_line_idx is None:
                    raise PatchSecurityError(
                        f"Slot end marker without start for '{slot_name}': {file_path}"
                    )
                if slot_name != open_slot:
                    raise PatchSecurityError(
                        f"Slot end marker mismatch (open '{open_slot}', got '{slot_name}'): {file_path}"
                    )
                slots[slot_name] = "".join(lines[start_line_idx + 1 : idx])
                open_slot = None
                start_line_idx = None

        if open_slot is not None:
            raise PatchSecurityError(
                f"Slot start marker without end for '{open_slot}': {file_path}"
            )

        return slots

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

        # Slot-aware rewrite ratio:
        # Se o arquivo contiver marcadores @engine:*:start/@engine:*:end, o limite de reescrita
        # passa a ser avaliado APENAS dentro de cada slot correspondente.
        #
        # Escolha: usar o pior caso (maior change_ratio) entre os slots. Isso mantém o guardrail
        # sem penalizar crescimento do arquivo fora do esqueleto fixo. Além disso, quando o slot
        # antigo está vazio (template), consideramos change_ratio=0 (adição, não reescrita).
        try:
            old_slots = self._extract_engine_slots(old_content, file_path)
            new_slots = self._extract_engine_slots(new_content, file_path)
        except PatchSecurityError:
            # Erros de slot devem ser determinísticos e bloquear o patch
            raise

        if old_slots or new_slots:
            if not old_slots or not new_slots:
                raise PatchSecurityError(
                    f"Slot markers mismatch between old/new content: {file_path}"
                )

            if set(old_slots.keys()) != set(new_slots.keys()):
                raise PatchSecurityError(
                    f"Slot markers mismatch between old/new content: {file_path}"
                )

            worst_change_ratio = 0.0
            worst_slot = ""
            for slot_name in sorted(old_slots.keys()):
                old_slot = old_slots[slot_name]
                new_slot = new_slots[slot_name]

                if not old_slot.strip():
                    change_ratio = 0.0
                else:
                    matcher = difflib.SequenceMatcher(None, old_slot, new_slot)
                    similarity = matcher.ratio()
                    change_ratio = 1.0 - similarity

                if change_ratio > worst_change_ratio:
                    worst_change_ratio = change_ratio
                    worst_slot = slot_name

            if worst_change_ratio > self.max_rewrite_ratio:
                raise PatchSecurityError(
                    f"Rewrite ratio too high ({worst_change_ratio:.1%} > {self.max_rewrite_ratio:.0%}) "
                    f"in slot '{worst_slot}': {file_path}"
                )
            return

        # Arquivo sem slots: comportamento atual (arquivo inteiro).
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
        self,
        patches: List[Dict[str, Any]],
        execution_id: Optional[str] = None,
        attempt: int = 0,
    ) -> PatchResult:
        """Aplica uma lista de patches de forma atômica.

        Args:
            patches: Lista de dicts com {operation, file_path, content?}
            execution_id: If provided, generates a PatchManifest with contract gate
            attempt: Fix loop attempt number (0 = initial, 1+ = fix attempts)

        Returns:
            PatchResult com status da operação

        Note:
            Se qualquer patch falhar, todos são revertidos (rollback).
        """
        self._ensure_project_exists()
        self._applied_operations = []
        result = PatchResult(success=False)

        # Track patch entries for manifest
        patch_entries: List[PatchEntry] = []

        try:
            for patch in patches:
                operation = patch.get("operation")
                file_path = patch.get("file_path")
                content = patch.get("content", "")

                if not operation or not file_path:
                    raise ValueError("Patch must have 'operation' and 'file_path'")

                # Track old content for rewrite ratio calculation
                old_content = ""
                target = self._validate_path(file_path)
                if target.exists() and operation in ("modify", "append"):
                    old_content = target.read_text()

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

                # Create patch entry for manifest
                entry = self._create_patch_entry(
                    file_path, operation, old_content, op.content or ""
                )
                patch_entries.append(entry)

            result.success = True
            self._cleanup_backup()

            # Generate PatchManifest if execution_id provided
            if execution_id:
                manifest_path = self._generate_manifest(
                    execution_id, patch_entries, "applied", attempt
                )
                result.manifest_path = str(manifest_path)

        except Exception as e:
            result.errors.append(str(e))
            result.failed_count = len(patches) - result.applied_count

            # ROLLBACK IMEDIATO
            self._rollback()
            result.rolled_back = True
            result.applied_count = 0

            # Generate manifest with rolled_back status if execution_id provided
            if execution_id:
                try:
                    manifest_path = self._generate_manifest(
                        execution_id, patch_entries, "rolled_back", attempt
                    )
                    result.manifest_path = str(manifest_path)
                except Exception:
                    pass  # Don't fail on manifest generation error

        return result

    def _create_patch_entry(
        self,
        file_path: str,
        operation: str,
        old_content: str,
        new_content: str,
    ) -> PatchEntry:
        """Create a PatchEntry for the manifest.

        Args:
            file_path: Path to the file
            operation: Type of operation (create, modify, delete, append)
            old_content: Original content (empty for create)
            new_content: New content (empty for delete)

        Returns:
            PatchEntry with computed metrics
        """
        # Compute rewrite ratio
        rewrite_ratio = 0.0
        if old_content and new_content:
            matcher = difflib.SequenceMatcher(None, old_content, new_content)
            rewrite_ratio = 1.0 - matcher.ratio()

        # Count line changes
        old_lines = old_content.splitlines() if old_content else []
        new_lines = new_content.splitlines() if new_content else []
        lines_added = max(0, len(new_lines) - len(old_lines))
        lines_removed = max(0, len(old_lines) - len(new_lines))

        # Compute hash of final content
        sha256_after = ""
        target = self._validate_path(file_path)
        if target.exists():
            sha256_after = compute_text_hash_sha256(target.read_text())

        return PatchEntry(
            path=file_path,
            op=operation,
            rewrite_ratio=rewrite_ratio,
            lines_added=lines_added,
            lines_removed=lines_removed,
            sha256_after=sha256_after,
        )

    def _generate_manifest(
        self,
        execution_id: str,
        patch_entries: List[PatchEntry],
        result_status: str,
        attempt: int,
    ) -> Path:
        """Generate and save a PatchManifest.

        Args:
            execution_id: Execution identifier
            patch_entries: List of patch entries
            result_status: "applied", "blocked", or "rolled_back"
            attempt: Fix loop attempt number

        Returns:
            Path to saved manifest
        """
        policy = PatchPolicy(
            max_rewrite_ratio=self.max_rewrite_ratio,
            blocked_paths=list(self.BLOCKED_PATHS),
            allowlist_roots=[str(self.generated_root)],
        )

        manifest = PatchManifest(
            execution_id=execution_id,
            project=self.project,
            patches=patch_entries,
            policy=policy,
            result=result_status,
            attempt=attempt,
        )

        store = PatchManifestStore(self.store_root)
        return store.save(manifest)

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
