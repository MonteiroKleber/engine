"""Input Mode - Modos de entrada do motor.

Define os 3 modos de entrada suportados:
- NATURAL: texto solto → Draft → GATE 1 → GATE 2 → IDL v1
- DRAFT: IDL Draft v1 JSON → GATE 1 → GATE 2 → IDL v1
- IDL: IDL v1 (texto .idl ou JSON) → Contract Gate

AUTO detecta o modo automaticamente via heurísticas determinísticas.
"""

import json
import re
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from idl import IDL_SCHEMA_VERSION, IDL_DRAFT_SCHEMA_VERSION


class InputMode(str, Enum):
    """Modos de entrada do motor."""
    NATURAL = "natural"
    DRAFT = "draft"
    IDL = "idl"
    AUTO = "auto"


class InputModeError(Exception):
    """Erro de detecção ou validação de input mode."""
    pass


def parse_input_mode(mode_str: str) -> InputMode:
    """Converte string para InputMode.

    Args:
        mode_str: String do modo (natural, draft, idl, auto)

    Returns:
        InputMode correspondente

    Raises:
        ValueError: Se modo inválido
    """
    mode_lower = mode_str.lower().strip()
    try:
        return InputMode(mode_lower)
    except ValueError:
        valid = ", ".join([m.value for m in InputMode])
        raise ValueError(f"Invalid input mode: '{mode_str}'. Valid modes: {valid}")


def detect_input_mode_auto(
    input_payload: str,
    input_path: Optional[str] = None,
) -> Tuple[InputMode, str]:
    """Detecta o modo de entrada automaticamente.

    Heurísticas determinísticas (ordem importa):
    1. Se extensão .idl → IDL
    2. Se extensão .json:
       - schema_version == "idl.v1" → IDL
       - schema_version == "idl_draft.v1" → DRAFT
       - schema_version desconhecido → ERRO
    3. Se texto inicia com keyword IDL v1 e parse passa → IDL
    4. Caso contrário → NATURAL

    Args:
        input_payload: Conteúdo do input (texto ou JSON)
        input_path: Caminho do arquivo (opcional)

    Returns:
        Tuple de (InputMode detectado, razão da detecção)

    Raises:
        InputModeError: Se não conseguir detectar ou formato inválido
    """
    # 1. Detectar por extensão do arquivo
    if input_path:
        path = Path(input_path)
        ext = path.suffix.lower()

        if ext == ".idl":
            return InputMode.IDL, f"File extension is .idl: {path.name}"

        if ext == ".json":
            return _detect_from_json(input_payload, path.name)

    # 2. Tentar parsear como JSON (pode ser inline JSON)
    if input_payload.strip().startswith("{"):
        try:
            return _detect_from_json(input_payload, "inline JSON")
        except json.JSONDecodeError:
            pass  # Não é JSON válido, continuar

    # 3. Verificar se parece IDL v1 por keywords
    if _looks_like_idl_v1(input_payload):
        return InputMode.IDL, "Input starts with IDL v1 keywords (system/actor/entity)"

    # 4. Default: NATURAL (texto livre)
    return InputMode.NATURAL, "Input is free-form text (no IDL/Draft markers detected)"


def _detect_from_json(json_content: str, source_name: str) -> Tuple[InputMode, str]:
    """Detecta modo a partir de conteúdo JSON.

    Args:
        json_content: Conteúdo JSON
        source_name: Nome da fonte para mensagens

    Returns:
        Tuple de (InputMode, razão)

    Raises:
        InputModeError: Se schema_version desconhecido ou ausente
    """
    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        raise InputModeError(f"Invalid JSON in {source_name}: {e}")

    if not isinstance(data, dict):
        raise InputModeError(f"JSON in {source_name} must be an object, got {type(data).__name__}")

    schema_version = data.get("schema_version")

    if schema_version is None:
        raise InputModeError(
            f"JSON in {source_name} has no 'schema_version' field. "
            f"Cannot determine input mode. Use --input-mode to specify explicitly."
        )

    # IDL v1 canônico
    if schema_version == IDL_SCHEMA_VERSION:
        return InputMode.IDL, f"JSON schema_version is '{IDL_SCHEMA_VERSION}'"

    # IDL Draft v1
    if schema_version == IDL_DRAFT_SCHEMA_VERSION:
        return InputMode.DRAFT, f"JSON schema_version is '{IDL_DRAFT_SCHEMA_VERSION}'"

    # Schema version conhecido mas errado para este contexto
    if schema_version == "diagnostic_report.v1":
        raise InputModeError(
            f"JSON in {source_name} is a DiagnosticReport (schema_version: diagnostic_report.v1), "
            f"not an IDL or Draft file. Please provide a valid IDL, Draft, or natural text input."
        )

    # Schema version desconhecido
    raise InputModeError(
        f"Unknown schema_version '{schema_version}' in {source_name}. "
        f"Expected '{IDL_SCHEMA_VERSION}' (IDL) or '{IDL_DRAFT_SCHEMA_VERSION}' (Draft). "
        f"Use --input-mode to specify explicitly."
    )


def _looks_like_idl_v1(text: str) -> bool:
    """Verifica se texto parece IDL v1 por keywords.

    Args:
        text: Texto a verificar

    Returns:
        True se parece IDL v1
    """
    # Remove comentários e espaços iniciais
    lines = text.strip().split("\n")
    first_meaningful_line = ""

    for line in lines:
        stripped = line.strip()
        # Pular linhas vazias e comentários
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue
        first_meaningful_line = stripped
        break

    if not first_meaningful_line:
        return False

    # Keywords que iniciam um documento IDL v1
    idl_keywords = ["system", "actor", "entity", "usecase", "integration", "nfr"]

    for keyword in idl_keywords:
        # Verifica se linha começa com keyword seguido de espaço ou identificador
        pattern = rf"^{keyword}\s+\w+"
        if re.match(pattern, first_meaningful_line, re.IGNORECASE):
            return True

    return False


def validate_input_mode_match(
    declared_mode: InputMode,
    detected_mode: InputMode,
    input_source: str,
) -> None:
    """Valida que o modo declarado corresponde ao conteúdo.

    Args:
        declared_mode: Modo declarado pelo usuário
        detected_mode: Modo detectado automaticamente
        input_source: Descrição da fonte para mensagens

    Raises:
        InputModeError: Se modos não correspondem
    """
    # AUTO não precisa validar
    if declared_mode == InputMode.AUTO:
        return

    # NATURAL aceita qualquer coisa (vai tentar processar)
    if declared_mode == InputMode.NATURAL:
        return

    # IDL declarado mas conteúdo é Draft
    if declared_mode == InputMode.IDL and detected_mode == InputMode.DRAFT:
        raise InputModeError(
            f"Input mode mismatch: --input-mode=idl but {input_source} contains "
            f"IDL Draft (schema_version: {IDL_DRAFT_SCHEMA_VERSION}). "
            f"Use --input-mode=draft instead."
        )

    # Draft declarado mas conteúdo é IDL
    if declared_mode == InputMode.DRAFT and detected_mode == InputMode.IDL:
        raise InputModeError(
            f"Input mode mismatch: --input-mode=draft but {input_source} contains "
            f"IDL v1 (schema_version: {IDL_SCHEMA_VERSION}). "
            f"Use --input-mode=idl instead."
        )
