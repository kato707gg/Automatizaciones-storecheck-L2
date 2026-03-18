from __future__ import annotations

from dataclasses import dataclass
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

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        ...


@dataclass
class CallableScopeTypeBackend:
    """Adapter mínimo para conectar funciones existentes (por ejemplo, bridge MCP)."""

    update_fn: Callable[[int, int], NetworkCallEvidence]
    verify_fn: Callable[[int], NetworkCallEvidence]

    def update_module_scope_type(self, module_id: int, scope_type_id: int) -> NetworkCallEvidence:
        return self.update_fn(module_id, scope_type_id)

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

    def __call__(self, action: PlaybookAction) -> ExecutionStepEvidence:
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

        has_save_evidence = any(
            step.action == "save_task" and step.success and step.reqid is not None
            for step in steps
        )
        has_verify_evidence = any(
            step.action == "verify_task" and step.success and step.reqid is not None
            for step in steps
        )

        success = has_save_evidence and has_verify_evidence

        return ExecutionResult(
            executed=self.runner is not None,
            success=success,
            steps=steps,
            final_snapshot={
                "task_name": ir.task_name,
                "planned_steps": len(actions),
                "network_evidence_complete": success,
            },
        )
