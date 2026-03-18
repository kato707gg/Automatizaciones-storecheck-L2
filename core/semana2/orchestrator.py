from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import AutoCorrector, ExecutionResult, SandboxExecutor, TaskParser, TaskValidator
from .models import ParseResult, ValidationResult


@dataclass
class OrchestratorResult:
    parse_result: ParseResult
    validation_result: ValidationResult
    execution_result: ExecutionResult | None
    retries: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parse_result": self.parse_result.to_dict(),
            "validation_result": self.validation_result.to_dict(),
            "execution_result": {
                "executed": self.execution_result.executed,
                "success": self.execution_result.success,
                "steps": [
                    {
                        "action": step.action,
                        "endpoint": step.endpoint,
                        "request_payload_excerpt": step.request_payload_excerpt,
                        "response_excerpt": step.response_excerpt,
                        "reqid": step.reqid,
                        "success": step.success,
                        "notes": step.notes,
                    }
                    for step in self.execution_result.steps
                ],
                "final_snapshot": self.execution_result.final_snapshot,
            }
            if self.execution_result
            else None,
            "retries": self.retries,
            "notes": list(self.notes),
        }


class Semana2Orchestrator:
    def __init__(
        self,
        parser: TaskParser,
        validator: TaskValidator,
        executor: SandboxExecutor | None = None,
        auto_corrector: AutoCorrector | None = None,
        max_retries: int = 1,
    ) -> None:
        self.parser = parser
        self.validator = validator
        self.executor = executor
        self.auto_corrector = auto_corrector
        self.max_retries = max_retries

    def run(self, prompt: str, context: dict[str, Any] | None = None) -> OrchestratorResult:
        parse_result = self.parser.parse(prompt=prompt, context=context)
        validation_result = self.validator.validate(parse_result.ir)

        if not validation_result.valid:
            return OrchestratorResult(
                parse_result=parse_result,
                validation_result=validation_result,
                execution_result=None,
                notes=["Flujo detenido: IR inválido."],
            )

        if self.executor is None:
            return OrchestratorResult(
                parse_result=parse_result,
                validation_result=validation_result,
                execution_result=None,
                notes=["Ejecución omitida: no se configuró executor."],
            )

        execution_result = self.executor.execute(validation_result.normalized_ir)

        retries = 0
        if not execution_result.success and self.auto_corrector is not None:
            while retries < self.max_retries:
                fix = self.auto_corrector.fix(validation_result.normalized_ir, execution_result)
                if not fix.should_retry or fix.fixed_ir is None:
                    break
                retries += 1
                validation_result = self.validator.validate(fix.fixed_ir)
                if not validation_result.valid:
                    break
                execution_result = self.executor.execute(validation_result.normalized_ir)
                if execution_result.success:
                    break

        notes = []
        if execution_result.success:
            notes.append("Flujo completado correctamente.")
        else:
            notes.append("Ejecución completada con fallos o sin evidencia de éxito.")

        return OrchestratorResult(
            parse_result=parse_result,
            validation_result=validation_result,
            execution_result=execution_result,
            retries=retries,
            notes=notes,
        )
