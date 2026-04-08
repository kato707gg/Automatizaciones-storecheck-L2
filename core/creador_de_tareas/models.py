from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

ConditionType = Literal["answer", "stage", "na"]


@dataclass
class BlockIR:
    block_id: str
    capture_data_type: str
    label: str
    mandatory: bool = False
    available_na: bool = True
    allowed_photos: bool = False
    mandatory_photos: bool = False
    multiple_photos: bool = False
    options: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConditionEdge:
    parent_block_id: str
    child_block_id: str
    condition_type: ConditionType = "stage"
    condition_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskIR:
    task_name: str
    blocks: list[BlockIR] = field(default_factory=list)
    edges: list[ConditionEdge] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "blocks": [block.to_dict() for block in self.blocks],
            "edges": [edge.to_dict() for edge in self.edges],
            "assumptions": list(self.assumptions),
        }


@dataclass
class ParseResult:
    ir: TaskIR
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ir": self.ir.to_dict(),
            "warnings": list(self.warnings),
        }


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized_ir: TaskIR | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "normalized_ir": self.normalized_ir.to_dict() if self.normalized_ir else None,
        }
