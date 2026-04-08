from __future__ import annotations

from .contracts import AutoFixResult, ExecutionResult
from .models import TaskIR


class NoOpAutoCorrector:
    """Autocorrector mínimo: no modifica IR, solo deja razón explícita."""

    def fix(self, ir: TaskIR, execution_result: ExecutionResult) -> AutoFixResult:
        return AutoFixResult(
            fixed_ir=None,
            reason="NoOpAutoCorrector activo: sin lógica de corrección automática todavía.",
            should_retry=False,
        )
