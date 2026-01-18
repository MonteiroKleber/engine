"""SIR (Structured Intermediate Representation) Schema v1."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union


@dataclass
class Segment:
    """A segment of source text."""
    segment_key: str
    text: str
    start_char: int
    end_char: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_key": self.segment_key,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Segment":
        return cls(
            segment_key=d["segment_key"],
            text=d["text"],
            start_char=d["start_char"],
            end_char=d["end_char"],
        )


@dataclass
class Source:
    """Source text metadata."""
    language: str
    segments: List[Segment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Source":
        return cls(
            language=d["language"],
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
        )


@dataclass
class Actor:
    """An actor (role) extracted from text."""
    actor_key: str
    name: str
    roles: List[str] = field(default_factory=list)
    source_segment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_key": self.actor_key,
            "name": self.name,
            "roles": sorted([r.lower() for r in self.roles]),
            "source_segment": self.source_segment,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Actor":
        return cls(
            actor_key=d["actor_key"],
            name=d["name"],
            roles=sorted([r.lower() for r in d.get("roles", [])]),
            source_segment=d.get("source_segment"),
        )


@dataclass
class Entity:
    """An entity (resource) extracted from text."""
    entity_key: str
    name: str
    entity_type: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    source_segment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_key": self.entity_key,
            "name": self.name,
            "entity_type": self.entity_type,
            "attributes": dict(sorted(self.attributes.items())),
            "source_segment": self.source_segment,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Entity":
        return cls(
            entity_key=d["entity_key"],
            name=d["name"],
            entity_type=d["entity_type"],
            attributes=d.get("attributes", {}),
            source_segment=d.get("source_segment"),
        )


@dataclass
class Policy:
    """A policy rule extracted from text."""
    policy_key: str
    policy_type: str  # rbac, approval, sod, invariant
    description: str
    actor_refs: List[str] = field(default_factory=list)
    entity_refs: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    source_segment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_key": self.policy_key,
            "policy_type": self.policy_type,
            "description": self.description,
            "actor_refs": sorted(self.actor_refs),
            "entity_refs": sorted(self.entity_refs),
            "conditions": dict(sorted(self.conditions.items())),
            "source_segment": self.source_segment,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Policy":
        return cls(
            policy_key=d["policy_key"],
            policy_type=d["policy_type"],
            description=d["description"],
            actor_refs=sorted(d.get("actor_refs", [])),
            entity_refs=sorted(d.get("entity_refs", [])),
            conditions=d.get("conditions", {}),
            source_segment=d.get("source_segment"),
        )


@dataclass
class RuntimePolicy:
    """Runtime policy rule for policies.json v1.1.

    This is extracted from explicit POLICY markers in text.
    Matches the ISE IDLPolicy format for policies.json v1.1.
    """
    policy_id: str
    phase: str  # "pre" or "post"
    endpoint_sig: str  # exact endpoint signature e.g. "POST /finance/expenses"
    rule_type: str  # numeric_max, numeric_min, string_max_len, required_field, enum_allowlist
    field_path: str  # dot notation e.g. "amount" or "payload.amount"
    value: Optional[Union[int, float, str, List[str]]] = None  # threshold value
    message: Optional[str] = None  # custom error message
    source_segment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "policy_id": self.policy_id,
            "phase": self.phase,
            "endpoint_sig": self.endpoint_sig,
            "rule_type": self.rule_type,
            "field_path": self.field_path,
        }
        if self.value is not None:
            result["value"] = self.value
        if self.message:
            result["message"] = self.message
        if self.source_segment:
            result["source_segment"] = self.source_segment
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RuntimePolicy":
        return cls(
            policy_id=d["policy_id"],
            phase=d["phase"],
            endpoint_sig=d["endpoint_sig"],
            rule_type=d["rule_type"],
            field_path=d["field_path"],
            value=d.get("value"),
            message=d.get("message"),
            source_segment=d.get("source_segment"),
        )


@dataclass
class WorkflowStep:
    """A step in a workflow."""
    step_key: str
    action: str
    actor_ref: Optional[str] = None
    entity_ref: Optional[str] = None
    conditions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_key": self.step_key,
            "action": self.action,
            "actor_ref": self.actor_ref,
            "entity_ref": self.entity_ref,
            "conditions": dict(sorted(self.conditions.items())),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_key=d["step_key"],
            action=d["action"],
            actor_ref=d.get("actor_ref"),
            entity_ref=d.get("entity_ref"),
            conditions=d.get("conditions", {}),
        )


@dataclass
class Workflow:
    """A workflow extracted from text."""
    workflow_key: str
    name: str
    steps: List[WorkflowStep] = field(default_factory=list)
    source_segment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_key": self.workflow_key,
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "source_segment": self.source_segment,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Workflow":
        return cls(
            workflow_key=d["workflow_key"],
            name=d["name"],
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
            source_segment=d.get("source_segment"),
        )


@dataclass
class Extraction:
    """Extracted entities from source."""
    actors: List[Actor] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    policies: List[Policy] = field(default_factory=list)
    workflows: List[Workflow] = field(default_factory=list)
    # Runtime policies for policies.json v1.1 (single-dept mode)
    runtime_policies: List[RuntimePolicy] = field(default_factory=list)
    # Runtime policies per dept (multi-dept mode): dept_id -> [RuntimePolicy]
    dept_runtime_policies: Dict[str, List[RuntimePolicy]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "actors": sorted([a.to_dict() for a in self.actors], key=lambda x: x["actor_key"]),
            "entities": sorted([e.to_dict() for e in self.entities], key=lambda x: x["entity_key"]),
            "policies": sorted([p.to_dict() for p in self.policies], key=lambda x: x["policy_key"]),
            "workflows": sorted([w.to_dict() for w in self.workflows], key=lambda x: x["workflow_key"]),
        }
        # Include runtime_policies only if present
        if self.runtime_policies:
            result["runtime_policies"] = sorted(
                [p.to_dict() for p in self.runtime_policies],
                key=lambda x: x["policy_id"]
            )
        # Include dept_runtime_policies only if present
        if self.dept_runtime_policies:
            result["dept_runtime_policies"] = {
                dept_id: sorted([p.to_dict() for p in policies], key=lambda x: x["policy_id"])
                for dept_id, policies in sorted(self.dept_runtime_policies.items())
            }
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Extraction":
        # Parse dept_runtime_policies
        dept_runtime_policies: Dict[str, List[RuntimePolicy]] = {}
        for dept_id, policies in d.get("dept_runtime_policies", {}).items():
            dept_runtime_policies[dept_id] = [RuntimePolicy.from_dict(p) for p in policies]

        return cls(
            actors=[Actor.from_dict(a) for a in d.get("actors", [])],
            entities=[Entity.from_dict(e) for e in d.get("entities", [])],
            policies=[Policy.from_dict(p) for p in d.get("policies", [])],
            workflows=[Workflow.from_dict(w) for w in d.get("workflows", [])],
            runtime_policies=[RuntimePolicy.from_dict(p) for p in d.get("runtime_policies", [])],
            dept_runtime_policies=dept_runtime_policies,
        )


@dataclass
class SIRv1:
    """Structured Intermediate Representation v1."""
    version: str = "1.0"
    source: Source = field(default_factory=lambda: Source(language="en"))
    extraction: Extraction = field(default_factory=Extraction)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source.to_dict(),
            "extraction": self.extraction.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SIRv1":
        return cls(
            version=d.get("version", "1.0"),
            source=Source.from_dict(d.get("source", {"language": "en"})),
            extraction=Extraction.from_dict(d.get("extraction", {})),
        )
