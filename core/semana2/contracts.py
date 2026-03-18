from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import ParseResult, TaskIR, ValidationResult


@dataclass
class ExecutionStepEvidence:
    action: str
    endpoint: str | None = None
    request_payload_excerpt: str | None = None
    response_excerpt: str | None = None
    reqid: int | None = None
    success: bool = False
    notes: str = ""


@dataclass
class ExecutionResult:
    executed: bool
    success: bool
    steps: list[ExecutionStepEvidence] = field(default_factory=list)
    final_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoFixResult:
    fixed_ir: TaskIR | None
    reason: str
    should_retry: bool


class TaskParser(Protocol):
    def parse(self, prompt: str, context: dict[str, Any] | None = None) -> ParseResult:
        ...


class TaskValidator(Protocol):
    def validate(self, ir: TaskIR) -> ValidationResult:
        ...


class SandboxExecutor(Protocol):
    def execute(self, ir: TaskIR) -> ExecutionResult:
        ...


class AutoCorrector(Protocol):
    def fix(self, ir: TaskIR, execution_result: ExecutionResult) -> AutoFixResult:
        ...
