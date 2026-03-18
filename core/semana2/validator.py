from __future__ import annotations

from copy import deepcopy

from .models import TaskIR, ValidationIssue, ValidationResult


_ALLOWED_CAPTURE_DATA_TYPES = {
    "1",  # Entero
    "2",  # Decimal
    "3",  # Lista única
    "4",  # Lista múltiple
    "6",  # Si / No
    "11", # Texto
    "12", # Foto
    "33", # Acciones múltiples
    "34", # Reconocimiento de imagen
}


class TaskIRValidator:
    """
    Validador determinista de schema/reglas críticas (MVP Semana 2).
    """

    def validate(self, ir: TaskIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        normalized = deepcopy(ir)

        if not normalized.task_name or not normalized.task_name.strip():
            issues.append(ValidationIssue(code="TASK_NAME_REQUIRED", message="El nombre de tarea es obligatorio."))
        else:
            normalized.task_name = normalized.task_name.strip()

        if not normalized.blocks:
            issues.append(ValidationIssue(code="BLOCKS_REQUIRED", message="La tarea debe tener al menos un bloque."))
            return ValidationResult(valid=False, issues=issues, normalized_ir=normalized)

        block_ids = [block.block_id for block in normalized.blocks]
        if len(block_ids) != len(set(block_ids)):
            issues.append(ValidationIssue(code="DUPLICATE_BLOCK_ID", message="Hay block_id duplicados en el IR."))

        block_map = {block.block_id: block for block in normalized.blocks}

        for block in normalized.blocks:
            if block.capture_data_type not in _ALLOWED_CAPTURE_DATA_TYPES:
                issues.append(
                    ValidationIssue(
                        code="CAPTURE_TYPE_NOT_ALLOWED",
                        message=f"captureDataType no permitido en MVP: {block.capture_data_type} (block_id={block.block_id}).",
                    )
                )

            if not block.label.strip():
                issues.append(
                    ValidationIssue(
                        code="BLOCK_LABEL_REQUIRED",
                        message=f"El bloque {block.block_id} no tiene label.",
                    )
                )

            if block.capture_data_type == "3":
                if len(block.options) < 2:
                    issues.append(
                        ValidationIssue(
                            code="UNIQUE_LIST_MIN_OPTIONS",
                            message=f"El bloque {block.block_id} (lista única) requiere mínimo 2 opciones.",
                        )
                    )

        for edge in normalized.edges:
            if edge.parent_block_id not in block_map:
                issues.append(
                    ValidationIssue(
                        code="EDGE_PARENT_NOT_FOUND",
                        message=f"Parent block inexistente: {edge.parent_block_id}.",
                    )
                )
                continue

            if edge.child_block_id not in block_map:
                issues.append(
                    ValidationIssue(
                        code="EDGE_CHILD_NOT_FOUND",
                        message=f"Child block inexistente: {edge.child_block_id}.",
                    )
                )
                continue

            parent = block_map[edge.parent_block_id]
            if edge.condition_type == "stage" and edge.condition_value in {"0", "1"}:
                if parent.capture_data_type != "6":
                    issues.append(
                        ValidationIssue(
                            code="YESNO_STAGE_REQUIRES_PARENT_6",
                            message=(
                                f"Condición stage con valor {edge.condition_value} requiere padre tipo 6 (Si/No). "
                                f"Padre actual={parent.capture_data_type}."
                            ),
                        )
                    )

        has_errors = any(issue.severity == "error" for issue in issues)
        return ValidationResult(valid=not has_errors, issues=issues, normalized_ir=normalized)
