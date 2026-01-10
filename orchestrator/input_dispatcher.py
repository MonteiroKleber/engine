"""Input Dispatcher - Coordena fluxos por modo de entrada.

Dispatcher para os 3 modos de entrada:
- NATURAL: texto → intake → Draft → GATE 1 → GATE 2 → IDL v1 → Contract Gate
- DRAFT: JSON Draft → GATE 1 → GATE 2 → IDL v1 → Contract Gate
- IDL: arquivo .idl ou JSON canônico → Contract Gate

Este módulo NÃO contém LLM. LLM só é chamado via intake (NATURAL mode).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .input_mode import (
    InputMode,
    InputModeError,
    detect_input_mode_auto,
    validate_input_mode_match,
)
from idl import (
    IDL_SCHEMA_VERSION,
    IDL_DRAFT_SCHEMA_VERSION,
    IDLDocument,
    IDLParser,
    IDLStore,
    IDLDraftV1,
    DraftSchemaValidator,
    DraftValidationResult,
    compile_draft_to_idl,
    CompileResult,
    DraftNotCompileableError,
)


@dataclass
class InputDispatchResult:
    """Resultado do dispatch de input."""
    success: bool
    input_mode_resolved: InputMode
    input_source: str  # path ou "inline"
    detection_reason: str

    # IDL output (sempre presente se success)
    idl_document: Optional[IDLDocument] = None
    idl_schema_version: str = ""
    idl_content_hash: str = ""
    idl_json_path: Optional[str] = None
    idl_markdown_path: Optional[str] = None

    # Draft info (se NATURAL ou DRAFT)
    draft_schema_version: Optional[str] = None
    draft_used: bool = False

    # Erros
    errors: list = None
    gate1_errors: list = None
    gate2_errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.gate1_errors is None:
            self.gate1_errors = []
        if self.gate2_errors is None:
            self.gate2_errors = []

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "success": self.success,
            "input_mode_resolved": self.input_mode_resolved.value,
            "input_source": self.input_source,
            "detection_reason": self.detection_reason,
            "idl_schema_version": self.idl_schema_version,
            "idl_content_hash": self.idl_content_hash,
            "idl_json_path": self.idl_json_path,
            "idl_markdown_path": self.idl_markdown_path,
            "draft_schema_version": self.draft_schema_version,
            "draft_used": self.draft_used,
            "errors": self.errors,
            "gate1_errors": self.gate1_errors,
            "gate2_errors": self.gate2_errors,
        }


class InputDispatcher:
    """Dispatcher para modos de entrada.

    Coordena o fluxo correto baseado no input mode:
    - NATURAL → intake → Draft → GATE 1 → GATE 2 → IDL v1
    - DRAFT → GATE 1 → GATE 2 → IDL v1
    - IDL → Contract Gate (parse + save)
    """

    def __init__(self, store_root: str):
        """Inicializa o dispatcher.

        Args:
            store_root: Diretório raiz para armazenamento
        """
        self.store_root = store_root
        self.idl_store = IDLStore(store_root)
        self.idl_parser = IDLParser()
        self.draft_validator = DraftSchemaValidator()

    def dispatch(
        self,
        project: str,
        input_mode: InputMode,
        input_payload: str,
        input_path: Optional[str] = None,
    ) -> InputDispatchResult:
        """Processa input e retorna IDL v1.

        Args:
            project: Nome do projeto
            input_mode: Modo de entrada (ou AUTO)
            input_payload: Conteúdo do input
            input_path: Caminho do arquivo (opcional)

        Returns:
            InputDispatchResult com IDL ou erros
        """
        input_source = input_path if input_path else "inline"

        # Resolver modo AUTO
        if input_mode == InputMode.AUTO:
            try:
                resolved_mode, detection_reason = detect_input_mode_auto(
                    input_payload, input_path
                )
            except InputModeError as e:
                return InputDispatchResult(
                    success=False,
                    input_mode_resolved=InputMode.AUTO,
                    input_source=input_source,
                    detection_reason="",
                    errors=[str(e)],
                )
        else:
            resolved_mode = input_mode
            detection_reason = f"Explicitly set to {input_mode.value}"

            # Validar que modo declarado corresponde ao conteúdo
            try:
                detected, _ = detect_input_mode_auto(input_payload, input_path)
                validate_input_mode_match(input_mode, detected, input_source)
            except InputModeError as e:
                return InputDispatchResult(
                    success=False,
                    input_mode_resolved=input_mode,
                    input_source=input_source,
                    detection_reason=detection_reason,
                    errors=[str(e)],
                )

        # Dispatch para fluxo correto
        if resolved_mode == InputMode.IDL:
            return self._dispatch_idl(project, input_payload, input_path, input_source, detection_reason)
        elif resolved_mode == InputMode.DRAFT:
            return self._dispatch_draft(project, input_payload, input_source, detection_reason)
        elif resolved_mode == InputMode.NATURAL:
            return self._dispatch_natural(project, input_payload, input_source, detection_reason)
        else:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=resolved_mode,
                input_source=input_source,
                detection_reason=detection_reason,
                errors=[f"Unknown input mode: {resolved_mode}"],
            )

    def _dispatch_idl(
        self,
        project: str,
        input_payload: str,
        input_path: Optional[str],
        input_source: str,
        detection_reason: str,
    ) -> InputDispatchResult:
        """Processa entrada IDL v1.

        Fluxo: .idl ou JSON canônico → parse → Contract Gate (save)

        Não passa por GATE 1 ou GATE 2 (já é IDL v1).
        """
        try:
            # Determinar se é JSON canônico ou texto .idl
            if input_payload.strip().startswith("{"):
                # JSON canônico - carregar diretamente
                data = json.loads(input_payload)
                # Criar documento a partir do JSON (reparse para validar)
                # Por agora, vamos salvar diretamente e deixar Contract Gate validar
                from idl.idl_v1 import IDLDocument, SystemDefinition

                # Extrair system info do JSON
                system_data = data.get("system", {})
                system = SystemDefinition(
                    id=system_data.get("id", project),
                    name=system_data.get("name", project),
                    version=system_data.get("version"),
                    description=system_data.get("description"),
                )

                # Criar documento mínimo e deixar o store validar
                document = IDLDocument(system=system)

                # Se já tem hash, usar load para validar
                if "content_hash_sha256" in data:
                    # Salvar temporariamente e carregar para validar Contract Gate
                    temp_path = Path(self.store_root) / "idl" / f"_temp_{project}.json"
                    temp_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path.write_text(input_payload, encoding="utf-8")

                    try:
                        self.idl_store.load(str(temp_path), validate_gate=True)
                        # Se passou, mover para path final
                        paths = self.idl_store.save(document, project)
                    finally:
                        if temp_path.exists():
                            temp_path.unlink()
                else:
                    # JSON sem hash - parse e salvar normalmente
                    paths = self.idl_store.save(document, project)

            else:
                # Texto .idl - parse usando IDLParser
                document = self.idl_parser.parse(input_payload)
                paths = self.idl_store.save(document, project)

            # Extrair hash do documento salvo
            canonical = document.to_canonical_dict()

            return InputDispatchResult(
                success=True,
                input_mode_resolved=InputMode.IDL,
                input_source=input_source,
                detection_reason=detection_reason,
                idl_document=document,
                idl_schema_version=IDL_SCHEMA_VERSION,
                idl_content_hash=canonical.get("content_hash_sha256", ""),
                idl_json_path=paths.get("json"),
                idl_markdown_path=paths.get("markdown"),
                draft_used=False,
            )

        except Exception as e:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=InputMode.IDL,
                input_source=input_source,
                detection_reason=detection_reason,
                errors=[f"IDL processing failed: {str(e)}"],
            )

    def _dispatch_draft(
        self,
        project: str,
        input_payload: str,
        input_source: str,
        detection_reason: str,
    ) -> InputDispatchResult:
        """Processa entrada IDL Draft v1.

        Fluxo: JSON Draft → GATE 1 → GATE 2 → IDL v1 → Contract Gate
        """
        try:
            # Parse JSON
            data = json.loads(input_payload)

            # GATE 1: Validação estrutural
            gate1_result = self.draft_validator.validate(data)

            if not gate1_result.valid:
                return InputDispatchResult(
                    success=False,
                    input_mode_resolved=InputMode.DRAFT,
                    input_source=input_source,
                    detection_reason=detection_reason,
                    draft_schema_version=IDL_DRAFT_SCHEMA_VERSION,
                    draft_used=True,
                    errors=["GATE 1 (Draft Structural Validation) failed"],
                    gate1_errors=[e.to_dict() for e in gate1_result.errors],
                )

            draft = gate1_result.draft

            # GATE 2: Compilação Draft → IDL v1
            compile_result = compile_draft_to_idl(draft)

            if not compile_result.success:
                return InputDispatchResult(
                    success=False,
                    input_mode_resolved=InputMode.DRAFT,
                    input_source=input_source,
                    detection_reason=detection_reason,
                    draft_schema_version=IDL_DRAFT_SCHEMA_VERSION,
                    draft_used=True,
                    errors=["GATE 2 (Draft → IDL Compilation) failed - unresolved fields or open questions"],
                    gate2_errors=[e.to_dict() for e in compile_result.errors],
                )

            # Contract Gate: salvar IDL v1
            document = compile_result.idl
            paths = self.idl_store.save(document, project)

            canonical = document.to_canonical_dict()

            return InputDispatchResult(
                success=True,
                input_mode_resolved=InputMode.DRAFT,
                input_source=input_source,
                detection_reason=detection_reason,
                idl_document=document,
                idl_schema_version=IDL_SCHEMA_VERSION,
                idl_content_hash=canonical.get("content_hash_sha256", ""),
                idl_json_path=paths.get("json"),
                idl_markdown_path=paths.get("markdown"),
                draft_schema_version=IDL_DRAFT_SCHEMA_VERSION,
                draft_used=True,
            )

        except json.JSONDecodeError as e:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=InputMode.DRAFT,
                input_source=input_source,
                detection_reason=detection_reason,
                errors=[f"Invalid JSON: {str(e)}"],
            )
        except Exception as e:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=InputMode.DRAFT,
                input_source=input_source,
                detection_reason=detection_reason,
                errors=[f"Draft processing failed: {str(e)}"],
            )

    def _dispatch_natural(
        self,
        project: str,
        input_payload: str,
        input_source: str,
        detection_reason: str,
    ) -> InputDispatchResult:
        """Processa entrada NATURAL (texto livre).

        Fluxo: texto → intake compiler → Draft → GATE 1 → GATE 2 → IDL v1

        NOTA: Nesta versão, o intake compiler é um STUB que:
        - Cria um Draft vazio com open_questions
        - BLOQUEIA no GATE 2 (requer resolução manual)

        O intake compiler real (com LLM) será implementado separadamente.
        """
        # STUB: Criar Draft com open_questions para bloquear GATE 2
        # Isso força o usuário a resolver as questões antes de compilar
        draft = IDLDraftV1(
            project=project,
            open_questions=[
                f"Natural language input requires manual conversion: '{input_payload[:100]}...'"
            ],
        )

        # GATE 1: Sempre passa (draft estruturalmente válido)
        gate1_result = self.draft_validator.validate(draft.to_dict())

        if not gate1_result.valid:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=InputMode.NATURAL,
                input_source=input_source,
                detection_reason=detection_reason,
                draft_schema_version=IDL_DRAFT_SCHEMA_VERSION,
                draft_used=True,
                errors=["GATE 1 failed (internal error - stub draft should be valid)"],
                gate1_errors=[e.to_dict() for e in gate1_result.errors],
            )

        # GATE 2: Vai falhar porque tem open_questions
        compile_result = compile_draft_to_idl(draft)

        if not compile_result.success:
            return InputDispatchResult(
                success=False,
                input_mode_resolved=InputMode.NATURAL,
                input_source=input_source,
                detection_reason=detection_reason,
                draft_schema_version=IDL_DRAFT_SCHEMA_VERSION,
                draft_used=True,
                errors=[
                    "GATE 2 blocked: Natural language input requires IDL Draft resolution.",
                    "Please convert your input to IDL Draft v1 JSON and resolve all open_questions.",
                    "Then use --input-mode=draft to process the resolved draft.",
                ],
                gate2_errors=[e.to_dict() for e in compile_result.errors],
            )

        # Se chegou aqui, algo está errado (draft com open_questions não deveria compilar)
        return InputDispatchResult(
            success=False,
            input_mode_resolved=InputMode.NATURAL,
            input_source=input_source,
            detection_reason=detection_reason,
            errors=["Internal error: draft with open_questions should not compile"],
        )


def dispatch_input(
    project: str,
    input_mode: InputMode,
    input_payload: str,
    input_path: Optional[str] = None,
    store_root: str = "/tmp/idl_store",
) -> InputDispatchResult:
    """Função de conveniência para dispatch de input.

    Args:
        project: Nome do projeto
        input_mode: Modo de entrada (ou AUTO)
        input_payload: Conteúdo do input
        input_path: Caminho do arquivo (opcional)
        store_root: Diretório raiz para armazenamento

    Returns:
        InputDispatchResult
    """
    dispatcher = InputDispatcher(store_root)
    return dispatcher.dispatch(project, input_mode, input_payload, input_path)
