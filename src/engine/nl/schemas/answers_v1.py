"""Answers Schema v1 for gap resolution."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import hashlib


def generate_question_id(gap_key: str, policy_key: str, step: str) -> str:
    """Generate deterministic question ID from components."""
    combined = f"{gap_key}|{policy_key}|{step}"
    hash_val = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:8]
    return f"q-{hash_val}"


@dataclass
class Question:
    """A question to resolve a gap."""
    question_id: str
    gap_key: str
    policy_key: str
    step: str
    question_text: str
    question_type: str  # choice, text, number, boolean
    options: List[str] = field(default_factory=list)
    default_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "question_id": self.question_id,
            "gap_key": self.gap_key,
            "policy_key": self.policy_key,
            "step": self.step,
            "question_text": self.question_text,
            "question_type": self.question_type,
        }
        if self.options:
            result["options"] = sorted(self.options)
        if self.default_value is not None:
            result["default_value"] = self.default_value
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Question":
        return cls(
            question_id=d["question_id"],
            gap_key=d["gap_key"],
            policy_key=d["policy_key"],
            step=d["step"],
            question_text=d["question_text"],
            question_type=d["question_type"],
            options=d.get("options", []),
            default_value=d.get("default_value"),
        )


@dataclass
class Gap:
    """A detected gap in the policy."""
    gap_key: str
    gap_type: str  # approval, sod, identity, auth, invariant, workflow
    severity: str  # required, recommended, optional
    description: str
    policy_ref: Optional[str] = None
    questions: List[Question] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_key": self.gap_key,
            "gap_type": self.gap_type,
            "severity": self.severity,
            "description": self.description,
            "policy_ref": self.policy_ref,
            "questions": sorted([q.to_dict() for q in self.questions], key=lambda x: x["question_id"]),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Gap":
        return cls(
            gap_key=d["gap_key"],
            gap_type=d["gap_type"],
            severity=d["severity"],
            description=d["description"],
            policy_ref=d.get("policy_ref"),
            questions=[Question.from_dict(q) for q in d.get("questions", [])],
        )


@dataclass
class Answer:
    """An answer to a gap question."""
    question_id: str
    value: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Answer":
        return cls(
            question_id=d["question_id"],
            value=d["value"],
        )


@dataclass
class AnswersV1:
    """Answers collection v1."""
    version: str = "1.0"
    answers: List[Answer] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "answers": sorted([a.to_dict() for a in self.answers], key=lambda x: x["question_id"]),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnswersV1":
        return cls(
            version=d.get("version", "1.0"),
            answers=[Answer.from_dict(a) for a in d.get("answers", [])],
        )

    def get_answer(self, question_id: str) -> Optional[Answer]:
        """Get answer by question ID."""
        for answer in self.answers:
            if answer.question_id == question_id:
                return answer
        return None
