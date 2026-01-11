"""Fix Loop Agent - Núcleo da autonomia para correção de erros de build.

Fluxo fixo:
1. classify_error() - Classifica o erro
2. generate_fix_patch() - Gera patch de correção
3. apply_patch() - Aplica o patch
4. validate_build() - Valida o build
5. Se sucesso: break; Se falha: próxima iteração

REGRAS ABSOLUTAS:
- MAX_FIX_ATTEMPTS = 3 (nunca loop infinito)
- Cada iteração: 1 patch, 1 causa
- Nunca tocar fora de <generated_root>/<project>
- Patches passam pelas mesmas rules da Semana 7
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import get_config
from fix_loop.error_classifier import (
    BuildErrorClassifier,
    BuildErrorType,
    BuildStep,
    ClassifiedError,
    ClassificationResult,
)
from patch_engine.patch_engine import PatchEngine, PatchResult, PatchSecurityError
from validators.build_validator import BuildValidator, BuildComponent, BuildReport


class FixAttemptStatus(Enum):
    """Status de uma tentativa de correção."""

    SUCCESS = "success"
    PATCH_FAILED = "patch_failed"
    BUILD_FAILED = "build_failed"
    NO_FIX_AVAILABLE = "no_fix_available"
    SECURITY_VIOLATION = "security_violation"
    FATAL_ERROR = "fatal_error"


@dataclass
class FixPatch:
    """Um patch de correção gerado."""

    operation: str  # "create", "modify", "append"
    file_path: str
    content: str
    error_type: BuildErrorType
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "operation": self.operation,
            "file_path": self.file_path,
            "content": self.content,
            "error_type": self.error_type.value,
            "description": self.description,
        }


@dataclass
class FixAttempt:
    """Resultado de uma tentativa de correção."""

    attempt_number: int
    status: FixAttemptStatus
    error_classified: Optional[ClassifiedError] = None
    patch_applied: Optional[FixPatch] = None
    build_report: Optional[BuildReport] = None
    error_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "attempt_number": self.attempt_number,
            "status": self.status.value,
            "error_classified": self.error_classified.to_dict() if self.error_classified else None,
            "patch_applied": self.patch_applied.to_dict() if self.patch_applied else None,
            "build_ok": self.build_report.ok if self.build_report else False,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }


@dataclass
class FixLoopResult:
    """Resultado do fix loop completo."""

    success: bool
    project: str
    total_attempts: int
    attempts: List[FixAttempt] = field(default_factory=list)
    final_build_ok: bool = False
    aborted_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "success": self.success,
            "project": self.project,
            "total_attempts": self.total_attempts,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_build_ok": self.final_build_ok,
            "aborted_reason": self.aborted_reason,
        }


class FixLoopAgent:
    """Agente de correção automática de erros de build.

    Executa um loop fixo de até MAX_FIX_ATTEMPTS tentativas
    para corrigir erros de build automaticamente.

    Attributes:
        MAX_FIX_ATTEMPTS: Número máximo de tentativas (default: 3)
        project: Nome do projeto
        generated_root: Diretório raiz dos projetos gerados
    """

    MAX_FIX_ATTEMPTS = 3

    def __init__(
        self,
        project: str,
        generated_root: Optional[str] = None,
    ) -> None:
        """Inicializa o Fix Loop Agent.

        Args:
            project: Nome do projeto
            generated_root: Diretório raiz dos projetos gerados (from config if None)
        """
        if not project or not project.strip():
            raise ValueError("Project name cannot be empty")

        self.project = project
        _generated_root = generated_root or get_config().generated_root
        self.generated_root = Path(_generated_root)
        self.project_root = self.generated_root / project

        # Componentes
        self.classifier = BuildErrorClassifier()
        self.patch_engine = PatchEngine(project, _generated_root)
        self.build_validator = BuildValidator(_generated_root)

        # Estado do loop
        self._current_attempt = 0
        self._seen_errors: set = set()  # Para detectar loops

    def run(
        self,
        stderr: str,
        stdout: str,
        exit_code: int,
        step: str,
    ) -> FixLoopResult:
        """Executa o fix loop.

        Args:
            stderr: Saída de erro do build inicial
            stdout: Saída padrão do build inicial
            exit_code: Código de saída do build inicial
            step: Etapa do build ("backend", "frontend")

        Returns:
            FixLoopResult com resultado do loop
        """
        result = FixLoopResult(
            success=False,
            project=self.project,
            total_attempts=0,
        )

        # Se build já passou, não há o que corrigir
        if exit_code == 0:
            result.success = True
            result.final_build_ok = True
            return result

        # Variáveis do loop
        current_stderr = stderr
        current_stdout = stdout
        current_exit_code = exit_code

        # Loop de correção
        for attempt_num in range(1, self.MAX_FIX_ATTEMPTS + 1):
            self._current_attempt = attempt_num
            result.total_attempts = attempt_num

            attempt = self._execute_attempt(
                attempt_num,
                current_stderr,
                current_stdout,
                current_exit_code,
                step,
            )
            result.attempts.append(attempt)

            # Verificar resultado da tentativa
            if attempt.status == FixAttemptStatus.SUCCESS:
                result.success = True
                result.final_build_ok = True
                break

            elif attempt.status == FixAttemptStatus.FATAL_ERROR:
                result.aborted_reason = f"Fatal error: {attempt.error_message}"
                break

            elif attempt.status == FixAttemptStatus.NO_FIX_AVAILABLE:
                result.aborted_reason = f"No fix available for error type"
                break

            elif attempt.status == FixAttemptStatus.SECURITY_VIOLATION:
                result.aborted_reason = f"Security violation: {attempt.error_message}"
                break

            elif attempt.status == FixAttemptStatus.BUILD_FAILED:
                # Build ainda falhou, atualizar stderr/stdout para próxima iteração
                if attempt.build_report:
                    current_stderr = "\n".join(attempt.build_report.errors)
                    current_stdout = ""
                    current_exit_code = 1

            # Verificar se estamos em loop (mesmo erro repetido)
            if attempt.error_classified:
                error_sig = self._get_error_signature(attempt.error_classified)
                if error_sig in self._seen_errors:
                    result.aborted_reason = "Loop detected: same error repeated"
                    break
                self._seen_errors.add(error_sig)

        # Se esgotou tentativas
        if not result.success and not result.aborted_reason:
            result.aborted_reason = f"Max attempts ({self.MAX_FIX_ATTEMPTS}) reached"

        return result

    def _execute_attempt(
        self,
        attempt_num: int,
        stderr: str,
        stdout: str,
        exit_code: int,
        step: str,
    ) -> FixAttempt:
        """Executa uma tentativa de correção.

        Args:
            attempt_num: Número da tentativa
            stderr: Saída de erro
            stdout: Saída padrão
            exit_code: Código de saída
            step: Etapa do build

        Returns:
            FixAttempt com resultado da tentativa
        """
        attempt = FixAttempt(
            attempt_number=attempt_num,
            status=FixAttemptStatus.PATCH_FAILED,
        )

        try:
            # 1. Classificar erro
            classification = self.classifier.classify(stderr, stdout, exit_code, step)

            if not classification.has_errors:
                attempt.status = FixAttemptStatus.NO_FIX_AVAILABLE
                attempt.error_message = "No errors to fix"
                return attempt

            # Pegar primeiro erro (1 patch, 1 causa)
            error = classification.errors[0]
            attempt.error_classified = error

            # Verificar se erro é fatal
            if error.error_type == BuildErrorType.FATAL_UNCLASSIFIED:
                attempt.status = FixAttemptStatus.FATAL_ERROR
                attempt.error_message = error.message
                return attempt

            # 2. Gerar patch de correção
            fix_patch = self._generate_fix_patch(error)

            if fix_patch is None:
                attempt.status = FixAttemptStatus.NO_FIX_AVAILABLE
                attempt.error_message = f"No fix strategy for {error.error_type.value}"
                return attempt

            attempt.patch_applied = fix_patch

            # 3. Aplicar patch (usa PatchEngine com regras de segurança)
            patch_dict = {
                "operation": fix_patch.operation,
                "file_path": fix_patch.file_path,
                "content": fix_patch.content,
            }

            patch_result = self.patch_engine.apply_patches([patch_dict])

            if not patch_result.success:
                attempt.status = FixAttemptStatus.PATCH_FAILED
                attempt.error_message = "; ".join(patch_result.errors)
                return attempt

            # 4. Validar build
            build_component = (
                BuildComponent.BACKEND if step.lower() in ("backend", "java", "maven")
                else BuildComponent.FRONTEND
            )

            build_report = self.build_validator.validate(self.project, build_component)
            attempt.build_report = build_report

            if build_report.ok:
                attempt.status = FixAttemptStatus.SUCCESS
            else:
                attempt.status = FixAttemptStatus.BUILD_FAILED
                attempt.error_message = "; ".join(build_report.errors[:3])

        except PatchSecurityError as e:
            attempt.status = FixAttemptStatus.SECURITY_VIOLATION
            attempt.error_message = str(e)

        except Exception as e:
            attempt.status = FixAttemptStatus.FATAL_ERROR
            attempt.error_message = str(e)

        return attempt

    def _generate_fix_patch(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Gera um patch de correção para o erro.

        Args:
            error: Erro classificado

        Returns:
            FixPatch ou None se não há correção disponível
        """
        # Dispatch para estratégia de correção
        strategy_map = {
            BuildErrorType.JAVA_MISSING_IMPORT: self._fix_java_missing_import,
            BuildErrorType.JAVA_TYPE_MISMATCH: self._fix_java_type_mismatch,
            BuildErrorType.JAVA_METHOD_NOT_IMPLEMENTED: self._fix_java_method_not_implemented,
            BuildErrorType.JAVA_SECURITY_CONFIG_ERROR: self._fix_java_security_config,
            BuildErrorType.JAVA_MISSING_ANNOTATION: self._fix_java_missing_annotation,
            BuildErrorType.TS_TYPE_ERROR: self._fix_ts_type_error,
            BuildErrorType.TS_MISSING_IMPORT: self._fix_ts_missing_import,
            BuildErrorType.TS_MISSING_EXPORT: self._fix_ts_missing_export,
            BuildErrorType.TS_PROPERTY_NOT_EXIST: self._fix_ts_property_not_exist,
            BuildErrorType.SQL_MIGRATION_ERROR: self._fix_sql_migration,
            BuildErrorType.UNKNOWN_BUT_PATCHABLE: self._fix_unknown_patchable,
        }

        strategy = strategy_map.get(error.error_type)
        if strategy:
            return strategy(error)

        return None

    def _get_error_signature(self, error: ClassifiedError) -> str:
        """Gera assinatura única para detectar loops."""
        return f"{error.error_type.value}:{error.file_path}:{error.symbol}"

    # ==================== FIX STRATEGIES ====================

    def _fix_java_missing_import(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige import Java faltando."""
        if not error.file_path:
            return None

        # Mapeamento de classes comuns para imports
        import_map = {
            "HttpServletRequest": "import javax.servlet.http.HttpServletRequest;",
            "HttpServletResponse": "import javax.servlet.http.HttpServletResponse;",
            "ResponseEntity": "import org.springframework.http.ResponseEntity;",
            "RequestMapping": "import org.springframework.web.bind.annotation.RequestMapping;",
            "GetMapping": "import org.springframework.web.bind.annotation.GetMapping;",
            "PostMapping": "import org.springframework.web.bind.annotation.PostMapping;",
            "PutMapping": "import org.springframework.web.bind.annotation.PutMapping;",
            "DeleteMapping": "import org.springframework.web.bind.annotation.DeleteMapping;",
            "RestController": "import org.springframework.web.bind.annotation.RestController;",
            "Service": "import org.springframework.stereotype.Service;",
            "Repository": "import org.springframework.stereotype.Repository;",
            "Autowired": "import org.springframework.beans.factory.annotation.Autowired;",
            "Entity": "import javax.persistence.Entity;",
            "Id": "import javax.persistence.Id;",
            "GeneratedValue": "import javax.persistence.GeneratedValue;",
            "Column": "import javax.persistence.Column;",
            "Table": "import javax.persistence.Table;",
            "JpaRepository": "import org.springframework.data.jpa.repository.JpaRepository;",
            "List": "import java.util.List;",
            "Optional": "import java.util.Optional;",
            "LocalDateTime": "import java.time.LocalDateTime;",
            "BigDecimal": "import java.math.BigDecimal;",
        }

        symbol = error.symbol
        if symbol and symbol in import_map:
            import_stmt = import_map[symbol]

            return FixPatch(
                operation="modify",
                file_path=error.file_path,
                content=self._add_import_to_java_file(error.file_path, import_stmt),
                error_type=error.error_type,
                description=f"Add import for {symbol}",
            )

        return None

    def _add_import_to_java_file(self, file_path: str, import_stmt: str) -> str:
        """Adiciona import a um arquivo Java."""
        full_path = self.project_root / file_path
        if not full_path.exists():
            return ""

        content = full_path.read_text()

        # Encontrar posição para inserir import (após package, antes da classe)
        lines = content.split("\n")
        insert_pos = 0

        for i, line in enumerate(lines):
            if line.startswith("package "):
                insert_pos = i + 1
                break

        # Inserir import
        lines.insert(insert_pos, import_stmt)
        return "\n".join(lines)

    def _fix_java_type_mismatch(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige type mismatch em Java."""
        # Estratégia básica: adicionar cast ou converter tipo
        # Implementação simplificada
        return None

    def _fix_java_method_not_implemented(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige método não implementado em Java."""
        # Estratégia: adicionar stub do método
        return None

    def _fix_java_security_config(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige erro de configuração de segurança Spring."""
        # Estratégia: atualizar SecurityConfig para nova API
        return None

    def _fix_java_missing_annotation(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige anotação faltando em Java."""
        return None

    def _fix_ts_type_error(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige erro de tipo TypeScript."""
        if not error.file_path:
            return None

        # Estratégia: adicionar type assertion ou any
        # Esta é uma correção simplificada
        return None

    def _fix_ts_missing_import(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige import TypeScript faltando."""
        if not error.file_path or not error.symbol:
            return None

        # Mapeamento de módulos comuns
        module_map = {
            "react": "import React from 'react';",
            "useState": "import { useState } from 'react';",
            "useEffect": "import { useEffect } from 'react';",
            "axios": "import axios from 'axios';",
        }

        if error.symbol in module_map:
            import_stmt = module_map[error.symbol]

            return FixPatch(
                operation="modify",
                file_path=error.file_path,
                content=self._add_import_to_ts_file(error.file_path, import_stmt),
                error_type=error.error_type,
                description=f"Add import for {error.symbol}",
            )

        return None

    def _add_import_to_ts_file(self, file_path: str, import_stmt: str) -> str:
        """Adiciona import a um arquivo TypeScript."""
        full_path = self.project_root / file_path
        if not full_path.exists():
            return ""

        content = full_path.read_text()
        lines = content.split("\n")

        # Inserir no início do arquivo
        lines.insert(0, import_stmt)
        return "\n".join(lines)

    def _fix_ts_missing_export(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige export TypeScript faltando."""
        return None

    def _fix_ts_property_not_exist(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige propriedade que não existe em TypeScript."""
        return None

    def _fix_sql_migration(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Corrige erro de migração SQL."""
        return None

    def _fix_unknown_patchable(self, error: ClassifiedError) -> Optional[FixPatch]:
        """Tenta correção genérica para erro desconhecido."""
        return None


def run_fix_loop(
    project: str,
    stderr: str,
    stdout: str,
    exit_code: int,
    step: str,
    generated_root: Optional[str] = None,
) -> FixLoopResult:
    """Função de conveniência para executar o fix loop.

    Args:
        project: Nome do projeto
        stderr: Saída de erro do build
        stdout: Saída padrão do build
        exit_code: Código de saída do build
        step: Etapa do build ("backend", "frontend")
        generated_root: Diretório raiz dos projetos gerados (from config if None)

    Returns:
        FixLoopResult com resultado do loop
    """
    agent = FixLoopAgent(project, generated_root)
    return agent.run(stderr, stdout, exit_code, step)
