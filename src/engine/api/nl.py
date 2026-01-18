"""NL Pipeline API Router."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.nl.errors import (
    NL_EMPTY_INPUT,
    NL_EXTRACTION_FAILED,
    NL_INVALID_LANGUAGE,
    NL_DRAFT_FAILED,
    NL_SIR_INVALID,
    NL_NO_POLICIES,
    NL_GAP_DETECTION_FAILED,
    NL_ANSWERS_INVALID,
    NL_QUESTION_NOT_FOUND,
    NL_FINALIZE_FAILED,
    NL_GAPS_REMAINING,
    NL_VALIDATION_FAILED,
)
from engine.nl.schemas.sir_v1 import SIRv1
from engine.nl.schemas.answers_v1 import AnswersV1, Gap, Answer
from engine.nl.extractors import get_extractor, LLMExtractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps, gaps_to_dict
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize, validate_final
from engine.nl.canonical import canonical_dict


router = APIRouter(prefix="/nl", tags=["nl"])


# Request/Response Models

class CompileSIRRequest(BaseModel):
    """Request for SIR compilation."""
    text: str = Field(..., min_length=1, description="Natural language text to compile")
    language: Optional[str] = Field(None, description="Language hint (auto-detected if not provided)")


class CompileSIRResponse(BaseModel):
    """Response from SIR compilation."""
    sir: Dict[str, Any]


class CompileDraftRequest(BaseModel):
    """Request for Draft IDL compilation."""
    sir: Dict[str, Any] = Field(..., description="SIR to compile to draft")


class CompileDraftResponse(BaseModel):
    """Response from Draft IDL compilation."""
    draft: Dict[str, Any]


class DetectGapsRequest(BaseModel):
    """Request for gap detection."""
    sir: Dict[str, Any] = Field(..., description="SIR used for extraction")
    draft: Dict[str, Any] = Field(..., description="Draft IDL to analyze")


class DetectGapsResponse(BaseModel):
    """Response from gap detection."""
    gaps: Dict[str, Any]


class AnswerItem(BaseModel):
    """An answer to a gap question."""
    question_id: str
    value: Any


class ApplyAnswersRequest(BaseModel):
    """Request for applying answers."""
    draft: Dict[str, Any] = Field(..., description="Draft IDL to update")
    gaps: List[Dict[str, Any]] = Field(..., description="Detected gaps")
    answers: List[AnswerItem] = Field(..., description="Answers to apply")


class ApplyAnswersResponse(BaseModel):
    """Response from applying answers."""
    draft: Dict[str, Any]
    remaining_gaps: List[Dict[str, Any]]


class FinalizeRequest(BaseModel):
    """Request for finalization."""
    draft: Dict[str, Any] = Field(..., description="Draft IDL to finalize")
    remaining_gaps: List[Dict[str, Any]] = Field(default=[], description="Remaining gaps")
    allow_gaps: bool = Field(default=False, description="Allow finalization with gaps")


class FinalizeResponse(BaseModel):
    """Response from finalization."""
    idl: Dict[str, Any]
    valid: bool
    errors: List[str]


def _error_response(code: str, message: str, meta: Optional[Dict[str, Any]] = None) -> HTTPException:
    """Create standard error response."""
    detail = {
        "code": code,
        "message": message,
    }
    if meta:
        detail["meta"] = meta
    return HTTPException(status_code=422, detail=detail)


@router.post("/compile/sir", response_model=CompileSIRResponse)
async def compile_sir(request: CompileSIRRequest) -> CompileSIRResponse:
    """Compile natural language text to SIR.

    Extracts structured information from natural language policy descriptions.
    Uses ENGINE_NL_EXTRACTOR env var to select extractor (deterministic or llm).
    """
    if not request.text or not request.text.strip():
        raise _error_response(NL_EMPTY_INPUT, "Input text is empty")

    # Validate language if provided
    if request.language and request.language not in ("en", "pt"):
        raise _error_response(
            NL_INVALID_LANGUAGE,
            f"Unsupported language: {request.language}",
            {"supported": ["en", "pt"]},
        )

    try:
        extractor = get_extractor()
        sir = extractor.extract(request.text, request.language)
        sir_dict = sir.to_dict()

        # Add metadata for LLM extractor
        if isinstance(extractor, LLMExtractor):
            sir_dict["meta"] = {
                "extractor_used": extractor.extractor_used,
            }
            if extractor.last_error_code:
                sir_dict["meta"]["llm_error_code"] = extractor.last_error_code

        return CompileSIRResponse(sir=sir_dict)
    except ValueError as e:
        raise _error_response(NL_EXTRACTION_FAILED, str(e))
    except Exception as e:
        raise _error_response(NL_EXTRACTION_FAILED, f"Extraction failed: {e}")


@router.post("/compile/draft", response_model=CompileDraftResponse)
async def compile_draft(request: CompileDraftRequest) -> CompileDraftResponse:
    """Compile SIR to Draft IDL.

    Generates initial IDL structure from SIR.
    """
    try:
        sir = SIRv1.from_dict(request.sir)
    except Exception as e:
        raise _error_response(NL_SIR_INVALID, f"Invalid SIR: {e}")

    try:
        draft = generate_draft(sir)
        return CompileDraftResponse(draft=draft)
    except ValueError as e:
        if "No policies" in str(e):
            raise _error_response(NL_NO_POLICIES, str(e))
        raise _error_response(NL_DRAFT_FAILED, str(e))
    except Exception as e:
        raise _error_response(NL_DRAFT_FAILED, f"Draft generation failed: {e}")


@router.post("/gaps", response_model=DetectGapsResponse)
async def detect_gaps_endpoint(request: DetectGapsRequest) -> DetectGapsResponse:
    """Detect gaps in Draft IDL.

    Analyzes the draft and identifies missing or incomplete information.
    """
    try:
        sir = SIRv1.from_dict(request.sir)
    except Exception as e:
        raise _error_response(NL_SIR_INVALID, f"Invalid SIR: {e}")

    try:
        gaps = detect_gaps(sir, request.draft)
        return DetectGapsResponse(gaps=gaps_to_dict(gaps))
    except Exception as e:
        raise _error_response(NL_GAP_DETECTION_FAILED, f"Gap detection failed: {e}")


@router.post("/answers/apply", response_model=ApplyAnswersResponse)
async def apply_answers_endpoint(request: ApplyAnswersRequest) -> ApplyAnswersResponse:
    """Apply answers to resolve gaps.

    Updates the draft IDL with user-provided answers.
    """
    # Convert gaps from dict to Gap objects
    try:
        gaps = [Gap.from_dict(g) for g in request.gaps]
    except Exception as e:
        raise _error_response(NL_ANSWERS_INVALID, f"Invalid gaps format: {e}")

    # Convert answers
    try:
        answers_list = [
            Answer(question_id=a.question_id, value=a.value)
            for a in request.answers
        ]
        answers = AnswersV1(answers=answers_list)
    except Exception as e:
        raise _error_response(NL_ANSWERS_INVALID, f"Invalid answers format: {e}")

    try:
        updated_draft, remaining_gaps = apply_answers(request.draft, gaps, answers)
        return ApplyAnswersResponse(
            draft=updated_draft,
            remaining_gaps=[g.to_dict() for g in remaining_gaps],
        )
    except ValueError as e:
        if "Question not found" in str(e):
            raise _error_response(NL_QUESTION_NOT_FOUND, str(e))
        raise _error_response(NL_ANSWERS_INVALID, str(e))
    except Exception as e:
        raise _error_response(NL_ANSWERS_INVALID, f"Failed to apply answers: {e}")


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_endpoint(request: FinalizeRequest) -> FinalizeResponse:
    """Finalize Draft IDL to production format.

    Validates and produces the final IDL.
    """
    # Convert remaining gaps
    try:
        remaining_gaps = [Gap.from_dict(g) for g in request.remaining_gaps]
    except Exception as e:
        raise _error_response(NL_FINALIZE_FAILED, f"Invalid gaps format: {e}")

    try:
        idl = finalize(request.draft, remaining_gaps, request.allow_gaps)
    except ValueError as e:
        if "required gaps" in str(e).lower():
            raise _error_response(NL_GAPS_REMAINING, str(e))
        raise _error_response(NL_FINALIZE_FAILED, str(e))
    except Exception as e:
        raise _error_response(NL_FINALIZE_FAILED, f"Finalization failed: {e}")

    # Validate final IDL
    valid, errors = validate_final(idl)

    if not valid and not request.allow_gaps:
        raise _error_response(
            NL_VALIDATION_FAILED,
            "Final IDL validation failed",
            {"errors": errors},
        )

    return FinalizeResponse(
        idl=idl,
        valid=valid,
        errors=errors,
    )
