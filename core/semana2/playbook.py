from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal

from .models import TaskIR

ActionType = Literal[
    "open_task_editor",
    "create_block",
    "update_block",
    "attach_condition",
    "save_task",
    "verify_task",
]


@dataclass
class PlaybookAction:
    step_id: str
    action_type: ActionType
    description: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_playbook(ir: TaskIR) -> list[PlaybookAction]:
    actions: list[PlaybookAction] = [
        PlaybookAction(
            step_id="S01",
            action_type="open_task_editor",
            description="Abrir editor de tareas Storecheck en sandbox.",
            payload={"url": "https://webapp.storecheck.com/moduleCapture/create"},
        )
    ]

    index = 2
    for block in ir.blocks:
        actions.append(
            PlaybookAction(
                step_id=f"S{index:02d}",
                action_type="create_block",
                description=f"Crear bloque {block.block_id} ({block.label}).",
                payload={
                    "block_id": block.block_id,
                    "capture_data_type": block.capture_data_type,
                    "label": block.label,
                },
            )
        )
        index += 1

        actions.append(
            PlaybookAction(
                step_id=f"S{index:02d}",
                action_type="update_block",
                description=f"Configurar propiedades del bloque {block.block_id}.",
                payload={
                    "block_id": block.block_id,
                    "mandatory": block.mandatory,
                    "available_na": block.available_na,
                    "allowed_photos": block.allowed_photos,
                    "mandatory_photos": block.mandatory_photos,
                    "multiple_photos": block.multiple_photos,
                    "options": list(block.options),
                },
            )
        )
        index += 1

    for edge in ir.edges:
        actions.append(
            PlaybookAction(
                step_id=f"S{index:02d}",
                action_type="attach_condition",
                description=(
                    f"Configurar condición {edge.condition_type} de {edge.parent_block_id} "
                    f"a {edge.child_block_id}."
                ),
                payload={
                    "parent_block_id": edge.parent_block_id,
                    "child_block_id": edge.child_block_id,
                    "condition_type": edge.condition_type,
                    "condition_value": edge.condition_value,
                },
            )
        )
        index += 1

    actions.extend(
        [
            PlaybookAction(
                step_id=f"S{index:02d}",
                action_type="save_task",
                description="Guardar tarea y capturar request/response de red.",
                payload={"endpoint": "/moduleCapture/update", "required_network_evidence": True},
            ),
            PlaybookAction(
                step_id=f"S{index + 1:02d}",
                action_type="verify_task",
                description="Verificar persistencia por UI y syncTaskData/moduleDefinition.",
                payload={
                    "endpoint": "/moduleCapture/syncTaskData?type=moduleDefinition",
                    "required_network_evidence": True,
                },
            ),
        ]
    )

    return actions
