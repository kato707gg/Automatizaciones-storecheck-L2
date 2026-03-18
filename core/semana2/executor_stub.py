from __future__ import annotations

from .contracts import ExecutionResult, ExecutionStepEvidence
from .models import TaskIR


class DryRunExecutor:
    """
    Executor de arranque (sin tocar Storecheck):
    - genera pasos planeados
    - deja lista la estructura para conectar MCP Chrome.
    """

    def execute(self, ir: TaskIR) -> ExecutionResult:
        steps = [
            ExecutionStepEvidence(
                action="open_task_editor",
                endpoint="/moduleCapture/create",
                success=True,
                notes="Paso simulado (dry-run).",
            ),
            ExecutionStepEvidence(
                action="create_blocks_from_ir",
                success=True,
                notes=f"Bloques a crear: {len(ir.blocks)}",
            ),
            ExecutionStepEvidence(
                action="apply_conditions",
                success=True,
                notes=f"Condiciones a aplicar: {len(ir.edges)}",
            ),
            ExecutionStepEvidence(
                action="save_task",
                endpoint="/moduleCapture/update",
                success=False,
                notes="Sin ejecución real MCP aún. Requiere integración en Semana 2 H3.",
            ),
        ]

        return ExecutionResult(
            executed=False,
            success=False,
            steps=steps,
            final_snapshot={
                "task_name": ir.task_name,
                "planned_blocks": len(ir.blocks),
                "planned_edges": len(ir.edges),
                "mode": "dry_run",
            },
        )
