from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Protocol

from .contracts import ExecutionResult, ExecutionStepEvidence
from .models import TaskIR
from .playbook import PlaybookAction, build_playbook

RunnerFn = Callable[[PlaybookAction], ExecutionStepEvidence]


@dataclass
class NetworkCallEvidence:
    reqid: int | None
    status_code: int
    endpoint: str
    request_excerpt: str | None = None
    response_excerpt: str | None = None
    response_json: dict[str, Any] | None = None


class ScopeTypeBackend(Protocol):
    def update_module_scope_type(self, module_id: int, scope_type_id: int) -> NetworkCallEvidence:
        ...

    def update_module_elements(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
    ) -> NetworkCallEvidence:
        ...

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        ...


@dataclass
class CallableScopeTypeBackend:
    """Adapter mínimo para conectar funciones existentes (por ejemplo, bridge MCP)."""

    update_fn: Callable[[int, int], NetworkCallEvidence]
    verify_fn: Callable[[int], NetworkCallEvidence]
    update_elements_fn: Callable[[int, list[dict[str, Any]]], NetworkCallEvidence] | None = None

    def update_module_scope_type(self, module_id: int, scope_type_id: int) -> NetworkCallEvidence:
        return self.update_fn(module_id, scope_type_id)

    def update_module_elements(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
    ) -> NetworkCallEvidence:
        if self.update_elements_fn is None:
            raise RuntimeError("update_elements_fn no fue configurado en CallableScopeTypeBackend")
        return self.update_elements_fn(module_id, elements)

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        return self.verify_fn(module_id)


@dataclass
class ScopeTypePatternRunner:
    """
    Runner real para el patrón save/verify usando moduleScopeType.

    Útil para cerrar corridas reales en verde con evidencia de red trazable
    sin acoplar el ejecutor al transporte (MCP, requests, etc.).
    """

    module_id: int
    original_scope_type: int
    target_scope_type: int
    backend: ScopeTypeBackend
    restore_on_verify: bool = False
    _elements_cache: list[dict[str, Any]] = field(default_factory=list)
    _block_to_element_id: dict[str, str] = field(default_factory=dict)
    _temp_counter: int = -1

    def __call__(self, action: PlaybookAction) -> ExecutionStepEvidence:
        if action.action_type == "create_block":
            return self._run_create_block(action)

        if action.action_type == "update_block":
            return self._run_update_block(action)

        if action.action_type == "save_task":
            save_call = self.backend.update_module_scope_type(
                module_id=self.module_id,
                scope_type_id=self.target_scope_type,
            )
            return ExecutionStepEvidence(
                action=action.action_type,
                endpoint=save_call.endpoint,
                request_payload_excerpt=save_call.request_excerpt,
                response_excerpt=save_call.response_excerpt,
                reqid=save_call.reqid,
                success=save_call.status_code == 200,
                notes=(
                    f"scopeType -> {self.target_scope_type} "
                    f"(HTTP {save_call.status_code})"
                ),
            )

        if action.action_type == "verify_task":
            verify_call = self.backend.get_module_definition(module_id=self.module_id)
            observed_scope_type = self._extract_scope_type(verify_call)
            verify_success = (
                verify_call.status_code == 200
                and observed_scope_type == self.target_scope_type
            )

            notes = (
                f"observed scopeType={observed_scope_type}, "
                f"expected={self.target_scope_type}"
            )

            if self.restore_on_verify:
                restore_call = self.backend.update_module_scope_type(
                    module_id=self.module_id,
                    scope_type_id=self.original_scope_type,
                )
                notes = (
                    f"{notes}; restore_scopeType={self.original_scope_type} "
                    f"restore_reqid={restore_call.reqid} "
                    f"restore_http={restore_call.status_code}"
                )

            return ExecutionStepEvidence(
                action=action.action_type,
                endpoint=verify_call.endpoint,
                request_payload_excerpt=verify_call.request_excerpt,
                response_excerpt=verify_call.response_excerpt,
                reqid=verify_call.reqid,
                success=verify_success,
                notes=notes,
            )

        return ExecutionStepEvidence(
            action=action.action_type,
            endpoint=action.payload.get("endpoint"),
            request_payload_excerpt=str(action.payload)[:300],
            success=True,
            notes=f"Step {action.step_id} delegado al runner (sin tráfico de red requerido).",
        )

    def _run_create_block(self, action: PlaybookAction) -> ExecutionStepEvidence:
        self._load_elements_cache_if_needed()

        block_id = str(action.payload.get("block_id", "")).strip() or f"ir_{len(self._elements_cache) + 1}"
        label = str(action.payload.get("label", "Bloque"))
        capture_data_type = str(action.payload.get("capture_data_type", "11"))
        order = len(self._elements_cache) + 1

        element = self._build_minimal_element(
            block_id=block_id,
            label=label,
            capture_data_type=capture_data_type,
            order=order,
        )
        self._elements_cache.append(element)

        update_call = self.backend.update_module_elements(
            module_id=self.module_id,
            elements=self._elements_cache,
        )

        self._refresh_elements_cache()
        matched = self._find_matching_element(label=label, capture_data_type=capture_data_type)
        if matched is not None and matched.get("elementId") is not None:
            self._block_to_element_id[block_id] = str(matched.get("elementId"))

        return ExecutionStepEvidence(
            action=action.action_type,
            endpoint=update_call.endpoint,
            request_payload_excerpt=update_call.request_excerpt,
            response_excerpt=update_call.response_excerpt,
            reqid=update_call.reqid,
            success=update_call.status_code == 200,
            notes=(
                f"create_block block_id={block_id} captureDataType={capture_data_type} "
                f"(HTTP {update_call.status_code})"
            ),
        )

    def _run_update_block(self, action: PlaybookAction) -> ExecutionStepEvidence:
        self._load_elements_cache_if_needed()

        block_id = str(action.payload.get("block_id", "")).strip()
        element = self._resolve_element_for_block(block_id)
        if element is None:
            return ExecutionStepEvidence(
                action=action.action_type,
                endpoint="/moduleCapture/update",
                request_payload_excerpt=str(action.payload)[:300],
                reqid=None,
                success=False,
                notes=f"No se encontró bloque previo para update_block block_id={block_id}.",
            )

        element["mandatory"] = bool(action.payload.get("mandatory", False))
        element["availableNA"] = bool(action.payload.get("available_na", True))
        element["allowedPhotos"] = bool(action.payload.get("allowed_photos", False))
        element["mandatoryPhotos"] = bool(action.payload.get("mandatory_photos", False))
        element["multiplePhotos"] = bool(action.payload.get("multiple_photos", False))

        options = action.payload.get("options")
        if isinstance(options, list) and options:
            element["options"] = [str(option) for option in options[:100]]

        update_call = self.backend.update_module_elements(
            module_id=self.module_id,
            elements=self._elements_cache,
        )
        self._refresh_elements_cache()

        return ExecutionStepEvidence(
            action=action.action_type,
            endpoint=update_call.endpoint,
            request_payload_excerpt=update_call.request_excerpt,
            response_excerpt=update_call.response_excerpt,
            reqid=update_call.reqid,
            success=update_call.status_code == 200,
            notes=(
                f"update_block block_id={block_id} mandatory={element.get('mandatory')} "
                f"availableNA={element.get('availableNA')} (HTTP {update_call.status_code})"
            ),
        )

    def _load_elements_cache_if_needed(self) -> None:
        if self._elements_cache:
            return
        self._refresh_elements_cache()

    def _refresh_elements_cache(self) -> None:
        definition_call = self.backend.get_module_definition(module_id=self.module_id)
        elements = self._extract_elements(definition_call)
        if elements is not None:
            self._elements_cache = elements

    def _resolve_element_for_block(self, block_id: str) -> dict[str, Any] | None:
        mapped_element_id = self._block_to_element_id.get(block_id)
        if mapped_element_id is not None:
            for element in self._elements_cache:
                if str(element.get("elementId")) == mapped_element_id:
                    return element

        if block_id.startswith("b") and block_id[1:].isdigit():
            index = int(block_id[1:]) - 1
            if 0 <= index < len(self._elements_cache):
                candidate = self._elements_cache[index]
                candidate_element_id = candidate.get("elementId")
                if candidate_element_id is not None:
                    self._block_to_element_id[block_id] = str(candidate_element_id)
                return candidate

        return None

    def _find_matching_element(self, label: str, capture_data_type: str) -> dict[str, Any] | None:
        for element in reversed(self._elements_cache):
            if (
                str(element.get("name", "")) == label
                and str(element.get("captureDataType", "")) == capture_data_type
            ):
                return element
        return self._elements_cache[-1] if self._elements_cache else None

    def _build_minimal_element(
        self,
        block_id: str,
        label: str,
        capture_data_type: str,
        order: int,
    ) -> dict[str, Any]:
        temp_id = str(self._temp_counter)
        self._temp_counter -= 1

        return {
            "id": temp_id,
            "elementId": temp_id,
            "orderElement": str(order),
            "name": label,
            "captureDataType": str(capture_data_type),
            "active": True,
            "mandatory": False,
            "availableNA": True,
            "allowedPhotos": False,
            "mandatoryPhotos": False,
            "multiplePhotos": False,
            "countProductLvl": "",
            "attachmentId": "",
        }

    @staticmethod
    def _extract_elements(call: NetworkCallEvidence) -> list[dict[str, Any]] | None:
        response_json = call.response_json
        if not isinstance(response_json, dict):
            return None

        module_capture = response_json.get("moduleCapture")
        if not isinstance(module_capture, dict):
            return None

        elements_wrapper = module_capture.get("elements")
        if not isinstance(elements_wrapper, dict):
            return None

        elements = elements_wrapper.get("elements")
        if not isinstance(elements, list):
            return None

        sanitized: list[dict[str, Any]] = []
        for item in elements:
            if isinstance(item, dict):
                sanitized.append(dict(item))
        return sanitized

    @staticmethod
    def _extract_scope_type(call: NetworkCallEvidence) -> int | None:
        response_json = call.response_json

        if response_json is None and call.response_excerpt:
            text = call.response_excerpt.strip()
            if text.startswith("{"):
                try:
                    response_json = json.loads(text)
                except json.JSONDecodeError:
                    response_json = None

        if not isinstance(response_json, dict):
            return None

        module_capture = response_json.get("moduleCapture")
        if not isinstance(module_capture, dict):
            return None

        value = module_capture.get("moduleScopeTypeId")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


@dataclass
class PlaybookExecutor:
    """
    Ejecuta un playbook determinista.

    - Con runner=None funciona como dry-run avanzado.
    - Con runner inyectado permite ejecutar pasos reales (p. ej. MCP Chrome bridge).
    """

    runner: RunnerFn | None = None

    def execute(self, ir: TaskIR) -> ExecutionResult:
        actions = build_playbook(ir)
        steps: list[ExecutionStepEvidence] = []

        for action in actions:
            if self.runner is None:
                steps.append(
                    ExecutionStepEvidence(
                        action=action.action_type,
                        endpoint=action.payload.get("endpoint"),
                        success=action.action_type not in {"save_task", "verify_task"},
                        notes=f"Playbook step {action.step_id} en modo simulación.",
                        request_payload_excerpt=str(action.payload)[:300],
                    )
                )
                continue

            steps.append(self.runner(action))

        has_create_evidence = all(
            step.success and step.reqid is not None
            for step in steps
            if step.action == "create_block"
        )
        has_update_evidence = all(
            step.success and step.reqid is not None
            for step in steps
            if step.action == "update_block"
        )

        has_save_evidence = any(
            step.action == "save_task" and step.success and step.reqid is not None
            for step in steps
        )
        has_verify_evidence = any(
            step.action == "verify_task" and step.success and step.reqid is not None
            for step in steps
        )

        success = has_create_evidence and has_update_evidence and has_save_evidence and has_verify_evidence

        return ExecutionResult(
            executed=self.runner is not None,
            success=success,
            steps=steps,
            final_snapshot={
                "task_name": ir.task_name,
                "planned_steps": len(actions),
                "create_update_network_evidence_complete": has_create_evidence and has_update_evidence,
                "network_evidence_complete": success,
            },
        )
