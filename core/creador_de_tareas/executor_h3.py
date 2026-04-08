from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
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

    def clear_module_elements(self, module_id: int) -> NetworkCallEvidence:
        ...

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        ...

    def create_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        capture_data_type: str,
        label: str,
    ) -> NetworkCallEvidence:
        ...

    def update_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        block_element_id: str | None = None,
    ) -> NetworkCallEvidence:
        ...

    def attach_condition(
        self,
        module_id: int,
        *,
        parent_block_id: str,
        child_block_id: str,
        condition_type: str,
        condition_value: str | None,
        parent_element_id: str | None = None,
        child_element_id: str | None = None,
    ) -> NetworkCallEvidence:
        ...


@dataclass
class CallableScopeTypeBackend:
    """Adapter mínimo para conectar funciones existentes (por ejemplo, bridge MCP)."""

    update_fn: Callable[[int, int], NetworkCallEvidence]
    verify_fn: Callable[[int], NetworkCallEvidence]
    update_elements_fn: Callable[[int, list[dict[str, Any]]], NetworkCallEvidence] | None = None
    create_block_fn: Callable[[int, list[dict[str, Any]], str, str, str], NetworkCallEvidence] | None = None
    update_block_fn: Callable[..., NetworkCallEvidence] | None = None
    attach_condition_fn: Callable[..., NetworkCallEvidence] | None = None
    fetch_diagnostics_fn: Callable[[], dict[str, Any] | list[dict[str, Any]] | None] | None = None

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

    def clear_module_elements(self, module_id: int) -> NetworkCallEvidence:
        return self.update_module_elements(module_id=module_id, elements=[])

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        return self.verify_fn(module_id)

    def create_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        capture_data_type: str,
        label: str,
    ) -> NetworkCallEvidence:
        if self.create_block_fn is not None:
            return self.create_block_fn(module_id, elements, block_id, capture_data_type, label)
        return self.update_module_elements(module_id=module_id, elements=elements)

    def update_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        block_element_id: str | None = None,
    ) -> NetworkCallEvidence:
        if self.update_block_fn is not None:
            try:
                return self.update_block_fn(module_id, elements, block_id, block_element_id)
            except TypeError:
                return self.update_block_fn(module_id, elements, block_id)
        return self.update_module_elements(module_id=module_id, elements=elements)

    def attach_condition(
        self,
        module_id: int,
        *,
        parent_block_id: str,
        child_block_id: str,
        condition_type: str,
        condition_value: str | None,
        parent_element_id: str | None = None,
        child_element_id: str | None = None,
    ) -> NetworkCallEvidence:
        if self.attach_condition_fn is not None:
            try:
                return self.attach_condition_fn(
                    module_id,
                    parent_block_id,
                    child_block_id,
                    condition_type,
                    condition_value,
                    parent_element_id,
                    child_element_id,
                )
            except TypeError:
                return self.attach_condition_fn(
                    module_id,
                    parent_block_id,
                    child_block_id,
                    condition_type,
                    condition_value,
                )
        return self.update_module_elements(module_id=module_id, elements=[])

    def fetch_page_diagnostics(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Optional: Ejecuta una llamada ligera al runtime para leer diagnósticos en página.

        Debe ser proporcionada por el adaptador que conoce el bridge (p. ej. MCP Chrome).
        """
        if self.fetch_diagnostics_fn is None:
            return None
        try:
            return self.fetch_diagnostics_fn()
        except Exception:
            return None


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
    clear_existing_elements_before_run: bool = True
    save_delay_before_publish: float = 0.25
    _elements_cache: list[dict[str, Any]] = field(default_factory=list)
    _block_to_element_id: dict[str, str] = field(default_factory=dict)
    _temp_counter: int = -1
    _prepared_for_run: bool = False
    _last_update_or_create_time: float = field(default_factory=time.time)

    def __call__(self, action: PlaybookAction) -> ExecutionStepEvidence:
        if action.action_type == "create_block":
            return self._run_create_block(action)

        if action.action_type == "update_block":
            return self._run_update_block(action)

        if action.action_type == "attach_condition":
            return self._run_attach_condition(action)

        if action.action_type == "save_task":
            # If recent create/update happened, wait a short configurable delay
            # to give the server time to process related changes and avoid races.
            elapsed = time.time() - self._last_update_or_create_time
            if elapsed < float(self.save_delay_before_publish or 0):
                time.sleep(float(self.save_delay_before_publish) - elapsed)

            save_call = self.backend.update_module_scope_type(
                module_id=self.module_id,
                scope_type_id=self.target_scope_type,
            )
            return self._build_network_step(
                action=action.action_type,
                call=save_call,
                success=self._strict_network_success(save_call),
                notes=(
                    f"scopeType -> {self.target_scope_type} "
                    f"(HTTP {save_call.status_code})"
                ),
            )

        if action.action_type == "verify_task":
            verify_call = self.backend.get_module_definition(module_id=self.module_id)
            observed_scope_type = self._extract_scope_type(verify_call)
            verify_success = self._strict_network_success(verify_call) and observed_scope_type == self.target_scope_type

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

            return self._build_network_step(
                action=action.action_type,
                call=verify_call,
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
        prepare_ok, prepare_note, prepare_call = self._prepare_module_for_creation()
        if not prepare_ok:
            failed_call = prepare_call or NetworkCallEvidence(
                reqid=None,
                status_code=0,
                endpoint="/moduleCapture/update",
                request_excerpt="type=element&operation=pre_cleanup",
                response_excerpt="pre_cleanup_failed_without_call",
                response_json=None,
            )
            return self._build_network_step(
                action=action.action_type,
                call=failed_call,
                success=False,
                notes=f"pre_cleanup_failed: {prepare_note}",
            )

        block_id = str(action.payload.get("block_id", "")).strip() or f"ir_{len(self._elements_cache) + 1}"
        label = str(action.payload.get("label", "Bloque"))
        capture_data_type = str(action.payload.get("capture_data_type", "11"))

        hint_element = {
            "irBlockId": block_id,
            "name": label,
            "captureDataType": capture_data_type,
        }

        create_call = self.backend.create_block(
            module_id=self.module_id,
            elements=[hint_element],
            block_id=block_id,
            capture_data_type=capture_data_type,
            label=label,
        )

        response_json = create_call.response_json if isinstance(create_call.response_json, dict) else {}
        response_element_id = response_json.get("elementId")
        if response_element_id is not None:
            self._block_to_element_id[block_id] = str(response_element_id)

        if response_element_id is None and self._strict_network_success(create_call):
            self._refresh_elements_cache()
            matched = self._find_matching_element(label=label, capture_data_type=capture_data_type)
            if matched is not None and matched.get("elementId") is not None:
                self._block_to_element_id[block_id] = str(matched.get("elementId"))

        mapped_element_id = self._block_to_element_id.get(block_id)
        create_success = self._strict_network_success(create_call)
        operational_success_reason: str | None = None
        if not create_success and create_call.reqid is not None and mapped_element_id is not None:
            create_success = True
            operational_success_reason = "persisted_after_refresh_with_reqid_non_200"

        self._last_update_or_create_time = time.time()
        return self._build_network_step(
            action=action.action_type,
            call=create_call,
            success=create_success,
            operational_success_reason=operational_success_reason,
            notes=(
                f"{prepare_note}; "
                f"create_block block_id={block_id} captureDataType={capture_data_type} "
                f"mappedElementId={mapped_element_id} "
                f"(HTTP {create_call.status_code})"
            ),
        )

    def _prepare_module_for_creation(self) -> tuple[bool, str, NetworkCallEvidence | None]:
        if self._prepared_for_run:
            return True, "pre_cleanup_cached", None

        self._prepared_for_run = True

        if not self.clear_existing_elements_before_run:
            self._refresh_elements_cache()
            return True, "pre_cleanup_disabled", None

        definition_call = self.backend.get_module_definition(module_id=self.module_id)
        if not self._strict_network_success(definition_call):
            return False, "module_definition_unavailable", definition_call

        elements = self._extract_elements(definition_call)
        if elements is None:
            return False, "module_definition_without_elements", definition_call

        self._elements_cache = elements
        existing_count = len(self._elements_cache)
        if existing_count == 0:
            self._block_to_element_id.clear()
            return True, "pre_cleanup_skipped_empty", definition_call

        clear_call = self.backend.clear_module_elements(module_id=self.module_id)
        clear_network_ok = self._strict_network_success(clear_call)

        verify_after_clear = self.backend.get_module_definition(module_id=self.module_id)
        cleared_elements = self._extract_elements(verify_after_clear)
        cleared_count = len(cleared_elements) if isinstance(cleared_elements, list) else -1

        if not clear_network_ok and cleared_count != 0:
            return False, f"pre_cleanup_failed_existing={existing_count}", clear_call

        self._elements_cache = []
        self._block_to_element_id.clear()

        if clear_network_ok:
            return True, f"pre_cleanup_removed={existing_count}", clear_call

        return True, (
            f"pre_cleanup_removed={existing_count}"
            f" persisted_after_verify_with_http_{clear_call.status_code}"
        ), clear_call

    def _run_update_block(self, action: PlaybookAction) -> ExecutionStepEvidence:
        block_id = str(action.payload.get("block_id", "")).strip()

        options_payload = action.payload.get("options")
        options: list[str] = []
        if isinstance(options_payload, list):
            options = [str(option) for option in options_payload[:100]]

        hint_element = {
            "irBlockId": block_id,
            "mandatory": bool(action.payload.get("mandatory", False)),
            "availableNA": bool(action.payload.get("available_na", True)),
            "allowedPhotos": bool(action.payload.get("allowed_photos", False)),
            "mandatoryPhotos": bool(action.payload.get("mandatory_photos", False)),
            "multiplePhotos": bool(action.payload.get("multiple_photos", False)),
            "options": options,
        }

        update_call = self.backend.update_block(
            module_id=self.module_id,
            elements=[hint_element],
            block_id=block_id,
            block_element_id=self._block_to_element_id.get(block_id),
        )
        self._refresh_elements_cache()

        observed = self._resolve_element_for_block(block_id)
        observed_mandatory = None if observed is None else observed.get("mandatory")
        observed_available_na = None if observed is None else observed.get("availableNA")

        self._last_update_or_create_time = time.time()
        return self._build_network_step(
            action=action.action_type,
            call=update_call,
            success=self._strict_network_success(update_call),
            notes=(
                f"update_block block_id={block_id} mandatory={observed_mandatory} "
                f"availableNA={observed_available_na} (HTTP {update_call.status_code})"
            ),
        )

    def _run_attach_condition(self, action: PlaybookAction) -> ExecutionStepEvidence:
        parent_block_id = str(action.payload.get("parent_block_id", "")).strip()
        child_block_id = str(action.payload.get("child_block_id", "")).strip()
        condition_type = str(action.payload.get("condition_type", "stage")).strip() or "stage"
        condition_value_raw = action.payload.get("condition_value")
        condition_value = None if condition_value_raw is None else str(condition_value_raw)
        # Resolve element ids from freshest cache just before making the attach call.
        # Avoid using possibly stale mapping populated earlier in the run.
        self._refresh_elements_cache()
        parent_element_id = self._block_to_element_id.get(parent_block_id) or self._find_element_id_by_block(parent_block_id)
        child_element_id = self._block_to_element_id.get(child_block_id) or self._find_element_id_by_block(child_block_id)

        # Esperar a que el servidor procese completamente los bloques antes de hacer attach
        # Si la última update/create fue muy reciente, agregar un pequeño delay
        elapsed_since_update = time.time() - self._last_update_or_create_time
        if elapsed_since_update < 0.15:  # 150ms de margen
            time.sleep(0.15 - elapsed_since_update)

        attach_call = self.backend.attach_condition(
            module_id=self.module_id,
            parent_block_id=parent_block_id,
            child_block_id=child_block_id,
            condition_type=condition_type,
            condition_value=condition_value,
            parent_element_id=parent_element_id,
            child_element_id=child_element_id,
        )
        self._refresh_elements_cache()

        observed_type, observed_value = self._get_observed_condition_state(child_block_id)
        persisted_ok = self._condition_state_matches(
            observed_type=observed_type,
            observed_value=observed_value,
            expected_type=condition_type,
            expected_value=condition_value,
        )

        retry_notes = ""
        final_call = attach_call
        if (not self._strict_network_success(attach_call)) or (not persisted_ok):
            time.sleep(0.25)
            self._refresh_elements_cache()
            parent_observed = self._resolve_element_for_block(parent_block_id)
            child_observed = self._resolve_element_for_block(child_block_id)
            retry_parent_element_id = (
                str(parent_observed.get("elementId"))
                if isinstance(parent_observed, dict) and parent_observed.get("elementId") is not None
                else parent_element_id
            )
            retry_child_element_id = (
                str(child_observed.get("elementId"))
                if isinstance(child_observed, dict) and child_observed.get("elementId") is not None
                else child_element_id
            )
            retry_call = self.backend.attach_condition(
                module_id=self.module_id,
                parent_block_id=parent_block_id,
                child_block_id=child_block_id,
                condition_type=condition_type,
                condition_value=condition_value,
                parent_element_id=retry_parent_element_id,
                child_element_id=retry_child_element_id,
            )
            self._refresh_elements_cache()
            retry_observed_type, retry_observed_value = self._get_observed_condition_state(child_block_id)
            retry_persisted_ok = self._condition_state_matches(
                observed_type=retry_observed_type,
                observed_value=retry_observed_value,
                expected_type=condition_type,
                expected_value=condition_value,
            )
            retry_notes = (
                f" retry_observedType={retry_observed_type}"
                f" retry_observedValue={retry_observed_value}"
                f" retry_http={retry_call.status_code}"
                f" retry_parentElementId={retry_parent_element_id}"
                f" retry_childElementId={retry_child_element_id}"
            )
            persisted_ok = retry_persisted_ok
            final_call = retry_call
            observed_type, observed_value = retry_observed_type, retry_observed_value

        return self._build_network_step(
            action=action.action_type,
            call=final_call,
            success=self._strict_network_success(final_call) and persisted_ok,
            notes=(
                f"attach_condition {parent_block_id}->{child_block_id} "
                f"type={condition_type} value={condition_value} "
                f"parentElementId={parent_element_id} childElementId={child_element_id} "
                f"observedType={observed_type} observedValue={observed_value} "
                f"(HTTP {final_call.status_code})"
                f"{retry_notes}"
            ),
        )

    def _get_observed_condition_state(self, block_id: str) -> tuple[str | None, str | None]:
        element = self._resolve_element_for_block(block_id)
        if element is None:
            return None, None

        observed_type_raw: Any = None
        for key in ("typeConditionSelected", "conditionTypeSelected", "conditionType"):
            candidate = element.get(key)
            if candidate is not None and str(candidate).strip() != "":
                observed_type_raw = candidate
                break

        observed_type = None
        if observed_type_raw is not None:
            observed_type = str(observed_type_raw).strip().lower()
        else:
            if bool(element.get("activeConditionStage")):
                observed_type = "stage"
            elif bool(element.get("activeConditionAnswer")):
                observed_type = "answer"
            elif bool(element.get("activeConditionNA")):
                observed_type = "na"

        observed_value_raw: Any = None
        for key in ("answerCondition", "conditionValue", "condition_value"):
            candidate = element.get(key)
            if candidate is not None and str(candidate).strip() != "":
                observed_value_raw = candidate
                break

        observed_value = self._normalize_condition_value(observed_value_raw)
        return observed_type, observed_value

    @staticmethod
    def _normalize_condition_value(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"1", "si", "sí", "yes", "true"}:
            return "1"
        if text in {"0", "no", "false"}:
            return "0"
        return text if text else None

    def _condition_state_matches(
        self,
        *,
        observed_type: str | None,
        observed_value: str | None,
        expected_type: str,
        expected_value: str | None,
    ) -> bool:
        normalized_expected_type = str(expected_type or "stage").strip().lower()
        normalized_expected_value = self._normalize_condition_value(expected_value)

        if observed_type != normalized_expected_type:
            return False

        if normalized_expected_type in {"stage", "answer"} and normalized_expected_value is not None:
            return observed_value == normalized_expected_value

        return True

    @staticmethod
    def _strict_network_success(call: NetworkCallEvidence) -> bool:
        return call.status_code == 200 and call.reqid is not None

    def _build_network_step(
        self,
        *,
        action: str,
        call: NetworkCallEvidence,
        success: bool,
        operational_success_reason: str | None = None,
        notes: str,
    ) -> ExecutionStepEvidence:
        # Intent: if the backend exposes a diagnostics fetcher, call it and
        # attach results into call.response_json under the key
        # '__automationDiagnostics'. This forces capture of runtime
        # diagnostics even when the primary response_json is empty.
        try:
            if hasattr(self.backend, "fetch_page_diagnostics"):
                diag = self.backend.fetch_page_diagnostics()
                if diag is not None:
                    if call.response_json is None or not isinstance(call.response_json, dict):
                        call.response_json = {}
                    call.response_json["__automationDiagnostics"] = diag
        except Exception:
            # don't let diagnostics fetching break the main flow
            pass

        # If the call returned a server error, attempt to fetch the full
        # network request details (if the backend/bridge exposes them) and
        # attach as additional diagnostic info to aid debugging.
        try:
            if (isinstance(call.status_code, int) and call.status_code >= 500) and call.reqid is not None:
                request_details = None
                # Prefer backend helper if available
                getter = getattr(self.backend, '_safe_get_network_request', None)
                if callable(getter):
                    try:
                        request_details = getter(call.reqid)
                    except Exception:
                        request_details = None

                # Fallback to bridge.get_network_request if present
                if request_details is None:
                    bridge = getattr(self.backend, 'bridge', None)
                    if bridge is not None and hasattr(bridge, 'get_network_request'):
                        try:
                            request_details = bridge.get_network_request(call.reqid)
                        except Exception:
                            request_details = None

                if request_details is not None:
                    try:
                        if call.response_json is None or not isinstance(call.response_json, dict):
                            call.response_json = {}
                        call.response_json.setdefault('__requestOn500', {})
                        call.response_json['__requestOn500']['reqid'] = call.reqid
                        call.response_json['__requestOn500']['details'] = request_details
                    except Exception:
                        pass
        except Exception:
            pass

        return ExecutionStepEvidence(
            action=action,
            endpoint=call.endpoint,
            http_status=call.status_code,
            request_payload_excerpt=call.request_excerpt,
            response_excerpt=call.response_excerpt,
            response_json=call.response_json,
            reqid=call.reqid,
            success=success,
            operational_success_reason=operational_success_reason,
            notes=notes,
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
            resolved = self._find_element_by_id_recursive(
                elements=self._elements_cache,
                element_id=mapped_element_id,
            )
            if resolved is not None:
                return resolved

        return None

    def _find_element_by_id_recursive(
        self,
        *,
        elements: list[dict[str, Any]],
        element_id: str,
    ) -> dict[str, Any] | None:
        for element in elements:
            if str(element.get("elementId")) == str(element_id):
                return element

            children_raw = element.get("children")
            if isinstance(children_raw, list):
                child_elements = [child for child in children_raw if isinstance(child, dict)]
                found = self._find_element_by_id_recursive(
                    elements=child_elements,
                    element_id=element_id,
                )
                if found is not None:
                    return found

        return None

    def _find_matching_element(self, label: str, capture_data_type: str) -> dict[str, Any] | None:
        for element in reversed(self._elements_cache):
            if (
                str(element.get("name", "")) == label
                and str(element.get("captureDataType", "")) == capture_data_type
            ):
                return element
        return None

    def _find_element_id_by_block(self, block_id: str) -> str | None:
        def _recurse(elements: list[dict[str, Any]]) -> str | None:
            for element in elements:
                if str(element.get("irBlockId", "")) == block_id and element.get("elementId") is not None:
                    return str(element.get("elementId"))
                children_raw = element.get("children")
                if isinstance(children_raw, list):
                    found = _recurse(children_raw)
                    if found is not None:
                        return found
            return None

        return _recurse(self._elements_cache)

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
                        http_status=None,
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

        has_attach_evidence = all(
            step.success and step.reqid is not None
            for step in steps
            if step.action == "attach_condition"
        )

        success = (
            has_create_evidence
            and has_update_evidence
            and has_attach_evidence
            and has_save_evidence
            and has_verify_evidence
        )

        return ExecutionResult(
            executed=self.runner is not None,
            success=success,
            steps=steps,
            final_snapshot={
                "task_name": ir.task_name,
                "planned_steps": len(actions),
                "create_update_network_evidence_complete": has_create_evidence and has_update_evidence,
                "attach_network_evidence_complete": has_attach_evidence,
                "network_evidence_complete": success,
            },
        )
