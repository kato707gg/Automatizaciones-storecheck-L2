from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Callable, Protocol

from .executor_h3 import NetworkCallEvidence, ScopeTypeBackend


class McpChromeBridge(Protocol):
    def evaluate_script(self, function: str) -> Any:
        ...

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
        page_idx: int | None = None,
    ) -> Any:
        ...

    def get_network_request(self, reqid: int) -> Any:
        ...


@dataclass
class CallableMcpChromeBridge:
    """Adapter mínimo para conectar funciones sueltas del bridge MCP."""

    evaluate_fn: Callable[[str], Any]
    list_requests_fn: Callable[..., Any]
    get_request_fn: Callable[[int], Any]

    def evaluate_script(self, function: str) -> Any:
        return self.evaluate_fn(function)

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
        page_idx: int | None = None,
    ) -> Any:
        try:
            return self.list_requests_fn(
                resource_types=resource_types,
                page_size=page_size,
                include_preserved_requests=include_preserved_requests,
                page_idx=page_idx,
            )
        except TypeError:
            return self.list_requests_fn(resource_types, page_size, include_preserved_requests)

    def get_network_request(self, reqid: int) -> Any:
        return self.get_request_fn(reqid)


@dataclass
class McpScopeTypeBackend(ScopeTypeBackend):
    """
    Backend concreto para corridas reales sobre MCP Chrome.

    Implementa:
    - update_module_scope_type(module_id, scope_type_id)
    - update_module_elements(module_id, elements)
    - get_module_definition(module_id)

    Captura reqid por diff de red (antes/después) y usa get_network_request
    para enriquecer la evidencia.
    """

    bridge: McpChromeBridge
    include_preserved_requests: bool = True
    network_page_size: int = 250
    strict_reqid: bool = True
    soft_refresh_enabled: bool = True

    def update_module_scope_type(self, module_id: int, scope_type_id: int) -> NetworkCallEvidence:
        endpoint = "/moduleCapture/update"
        request_excerpt = (
            f"type=moduleScopeType&moduleId={module_id}&moduleScopeTypeId={scope_type_id}"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_update_scope_script(module_id=module_id, scope_type_id=scope_type_id)
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=1)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def update_module_elements(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
    ) -> NetworkCallEvidence:
        endpoint = "/moduleCapture/update"
        request_excerpt = (
            f"type=element&moduleId={module_id}&elementsCount={len(elements)}"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_update_elements_script(module_id=module_id, elements=elements)
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=3)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def clear_module_elements(self, module_id: int) -> NetworkCallEvidence:
        endpoint = "/moduleCapture/update"
        request_excerpt = (
            f"type=element&operation=clear_module_elements&moduleId={module_id}&elementsCount=0"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_clear_elements_script(module_id=module_id)
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=7)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def get_module_definition(self, module_id: int) -> NetworkCallEvidence:
        endpoint = f"/moduleCapture/syncTaskData?type=moduleDefinition&moduleId={module_id}"
        request_excerpt = f"type=moduleDefinition,moduleId={module_id}"

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_module_definition_script(module_id=module_id)
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains="/moduleCapture/syncTaskData?type=moduleDefinition",
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=2)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def create_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        capture_data_type: str,
        label: str,
    ) -> NetworkCallEvidence:
        endpoint = "/moduleCapture/update"
        request_excerpt = (
            f"type=newElement&operation=create_block&moduleId={module_id}&blockId={block_id}"
            f"&captureDataType={capture_data_type}&label={label}"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_create_block_script(
                module_id=module_id,
                block_id=block_id,
                capture_data_type=capture_data_type,
                label=label,
                soft_refresh_enabled=self.soft_refresh_enabled,
            )
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=4)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def update_block(
        self,
        module_id: int,
        elements: list[dict[str, Any]],
        *,
        block_id: str,
        block_element_id: str | None = None,
    ) -> NetworkCallEvidence:
        endpoint = "/moduleCapture/update"

        target: dict[str, Any] | None = None
        for item in elements:
            if isinstance(item, dict) and str(item.get("irBlockId", "")) == block_id:
                target = item
                break

        mandatory = bool(target.get("mandatory", False)) if target else False
        available_na = bool(target.get("availableNA", True)) if target else True
        allowed_photos = bool(target.get("allowedPhotos", False)) if target else False
        mandatory_photos = bool(target.get("mandatoryPhotos", False)) if target else False
        multiple_photos = bool(target.get("multiplePhotos", False)) if target else False
        options_value = target.get("options") if target else None
        options = options_value if isinstance(options_value, list) else []

        request_excerpt = (
            f"type=element&operation=update_block&moduleId={module_id}&blockId={block_id}"
            f"&blockElementId={block_element_id}"
            f"&mandatory={mandatory}&availableNA={available_na}&optionsCount={len(options)}"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_update_block_script(
                module_id=module_id,
                block_id=block_id,
                block_element_id=block_element_id,
                mandatory=mandatory,
                available_na=available_na,
                allowed_photos=allowed_photos,
                mandatory_photos=mandatory_photos,
                multiple_photos=multiple_photos,
                options=options,
                soft_refresh_enabled=self.soft_refresh_enabled,
            )
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=5)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

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
        endpoint = "/moduleCapture/update"
        request_excerpt = (
            f"type=element&operation=attach_condition&moduleId={module_id}"
            f"&parentBlockId={parent_block_id}&childBlockId={child_block_id}"
            f"&conditionType={condition_type}&conditionValue={condition_value}"
            f"&parentElementId={parent_element_id}&childElementId={child_element_id}"
        )

        reqids_before = self._snapshot_reqids()
        eval_result = self.bridge.evaluate_script(
            self._build_attach_condition_script(
                module_id=module_id,
                parent_block_id=parent_block_id,
                child_block_id=child_block_id,
                condition_type=condition_type,
                condition_value=condition_value,
                parent_element_id=parent_element_id,
                child_element_id=child_element_id,
                soft_refresh_enabled=self.soft_refresh_enabled,
            )
        )
        reqids_after = self._snapshot_reqids()

        reqid = self._resolve_reqid(
            reqids_before=reqids_before,
            reqids_after=reqids_after,
            endpoint_contains=endpoint,
        )
        request_details = self._safe_get_network_request(reqid)

        status_code = self._coalesce_status(eval_result, request_details)
        response_excerpt = self._coalesce_response_excerpt(eval_result, request_details)
        response_json = self._extract_response_json(eval_result, request_details)
        if reqid is None and status_code == 200 and not self.strict_reqid:
            reqid = self._fallback_reqid(prefix=6)

        return NetworkCallEvidence(
            reqid=reqid,
            status_code=status_code,
            endpoint=endpoint,
            request_excerpt=request_excerpt,
            response_excerpt=response_excerpt,
            response_json=response_json,
        )

    def _snapshot_reqids(self) -> set[int]:
        listing = self.bridge.list_network_requests(
            resource_types=["xhr", "fetch"],
            page_size=self.network_page_size,
            include_preserved_requests=self.include_preserved_requests,
        )
        return self._extract_reqids(listing)

    def _resolve_reqid(
        self,
        reqids_before: set[int],
        reqids_after: set[int],
        endpoint_contains: str,
    ) -> int | None:
        new_reqids = sorted(reqids_after - reqids_before, reverse=True)
        if not new_reqids:
            return None

        for reqid in new_reqids:
            details = self._safe_get_network_request(reqid)
            endpoint = self._extract_endpoint(details)
            if endpoint_contains in endpoint:
                return reqid

        return new_reqids[0]

    def _safe_get_network_request(self, reqid: int | None) -> Any:
        if reqid is None:
            return None
        try:
            return self.bridge.get_network_request(reqid)
        except Exception:
            return None

    @staticmethod
    def _fallback_reqid(prefix: int) -> int:
        ms = int(time.time() * 1000) % 10_000_000
        return prefix * 10_000_000 + ms

    @staticmethod
    def _extract_reqids(payload: Any) -> set[int]:
        reqids: set[int] = set()

        if isinstance(payload, dict):
            for key in ("requests", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    reqids.update(McpScopeTypeBackend._extract_reqids(value))

            direct = payload.get("reqid")
            if isinstance(direct, int):
                reqids.add(direct)

        if isinstance(payload, list):
            for item in payload:
                reqids.update(McpScopeTypeBackend._extract_reqids(item))

        if isinstance(payload, str):
            for match in re.findall(r"reqid\s*=\s*(\d+)", payload):
                reqids.add(int(match))

        return reqids

    @staticmethod
    def _extract_endpoint(request_details: Any) -> str:
        if isinstance(request_details, dict):
            for key in ("url", "requestUrl", "endpoint", "path"):
                value = request_details.get(key)
                if isinstance(value, str):
                    return value

            request_obj = request_details.get("request")
            if isinstance(request_obj, dict):
                value = request_obj.get("url")
                if isinstance(value, str):
                    return value

        if isinstance(request_details, str):
            match = re.search(r"Request\s+(https?://\S+)", request_details)
            if match:
                return match.group(1)

        return ""

    @staticmethod
    def _coalesce_status(eval_result: Any, request_details: Any) -> int:
        for payload in (eval_result, request_details):
            if isinstance(payload, dict):
                for key in ("status", "status_code", "http_status"):
                    value = payload.get(key)
                    if isinstance(value, int):
                        return value
        return 0

    @staticmethod
    def _coalesce_response_excerpt(eval_result: Any, request_details: Any) -> str | None:
        for payload in (request_details, eval_result):
            if isinstance(payload, dict):
                for key in ("responseBody", "response_body", "response_excerpt", "body_preview", "body"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value[:400]

            if isinstance(payload, str):
                response_match = re.search(r"Response Body\n([\s\S]*)", payload)
                if response_match:
                    return response_match.group(1).strip()[:400]

        return None

    @staticmethod
    def _extract_response_json(eval_result: Any, request_details: Any) -> dict[str, Any] | None:
        for payload in (eval_result, request_details):
            if isinstance(payload, dict):
                json_candidate = payload.get("response_json") or payload.get("json")
                if isinstance(json_candidate, dict):
                    return json_candidate

        excerpt = McpScopeTypeBackend._coalesce_response_excerpt(eval_result, request_details)
        if not excerpt:
            return None

        text = excerpt.strip()
        if not text.startswith("{"):
            return None

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None

        return parsed if isinstance(parsed, dict) else None

    def fetch_page_diagnostics(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Leer `window.__automationDiagnostics` del runtime (si existe).

        Retorna la estructura evaluada por el bridge o None si no es posible.
        """
        try:
            result = self.bridge.evaluate_script("() => { try { return window.__automationDiagnostics || []; } catch(e) { return []; } }")
            return result
        except Exception:
            return None

    @staticmethod
    def _build_update_scope_script(module_id: int, scope_type_id: int) -> str:
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
  const body = new URLSearchParams();
  body.set('type', 'moduleScopeType');
  body.set('moduleId', String({module_id}));
  body.set('moduleScopeTypeId', String({scope_type_id}));

    const res = await fetch(endpoint, {{
    method: 'POST',
    credentials: 'include',
    headers: {{
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest'
    }},
    body: body.toString()
  }});

  const text = await res.text();
  let response_json = null;
  try {{ response_json = JSON.parse(text); }} catch (e) {{}}

  return {{
    status_code: res.status,
        endpoint,
    body_preview: text.slice(0, 400),
    response_json
  }};
}}"""

    @staticmethod
    def _build_module_definition_script(module_id: int) -> str:
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/syncTaskData?type=moduleDefinition&moduleId=' + String({module_id}), baseUrl).toString();
  const res = await fetch(endpoint, {{
    method: 'GET',
    credentials: 'include',
    headers: {{
      'X-Requested-With': 'XMLHttpRequest'
    }}
  }});

  const text = await res.text();
  let response_json = null;
  try {{ response_json = JSON.parse(text); }} catch (e) {{}}

  return {{
    status_code: res.status,
    endpoint,
    body_preview: text.slice(0, 400),
    response_json
  }};
}}"""

    @staticmethod
    def _build_update_elements_script(module_id: int, elements: list[dict[str, Any]]) -> str:
        serialized_elements = json.dumps(elements, ensure_ascii=False)
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
    const body = new URLSearchParams();
    const elements = {serialized_elements};
    body.set('type', 'element');
    body.set('moduleId', String({module_id}));
    body.set('elementsArray', JSON.stringify(elements));

    const res = await fetch(endpoint, {{
        method: 'POST',
        credentials: 'include',
        headers: {{
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }},
        body: body.toString()
    }});

    const text = await res.text();
    let response_json = null;
    try {{ response_json = JSON.parse(text); }} catch (e) {{}}

    return {{
        status_code: res.status,
        endpoint,
        body_preview: text.slice(0, 400),
        response_json
    }};
}}"""

    @staticmethod
    def _build_clear_elements_script(module_id: int) -> str:
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
    const moduleId = String({module_id});

    if (window.editor && typeof window.editor.getMain === 'function') {{
        const main = window.editor.getMain();
        if (main && main.length) {{
            const rows = main.children('li.element-capture').toArray();
            for (const row of rows) {{
                if (typeof window.editor.removeElement === 'function') {{
                    try {{ window.editor.removeElement(row); }} catch (_e) {{}}
                }} else {{
                    try {{ row.remove(); }} catch (_e) {{}}
                }}
            }}
        }}
    }}

    if (window.module && window.module.moduleCapture) {{
        if (!window.module.moduleCapture.elements) window.module.moduleCapture.elements = {{}};
        window.module.moduleCapture.elements.elements = [];
    }}

    const body = new URLSearchParams();
    body.set('type', 'element');
    body.set('moduleId', moduleId);
    body.set('elementsArray', '[]');
    body.set('ownerElementId', '');

    const res = await fetch(endpoint, {{
        method: 'POST',
        credentials: 'include',
        headers: {{
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }},
        body: body.toString()
    }});

    const text = await res.text();
    let response_json = null;
    try {{ response_json = JSON.parse(text); }} catch (_e) {{}}

    return {{
        status_code: res.status,
        endpoint,
        body_preview: text.slice(0, 400),
        response_json
    }};
}}"""

    @staticmethod
    def _build_create_block_script(
        module_id: int,
        block_id: str,
        capture_data_type: str,
        label: str,
        soft_refresh_enabled: bool = True,
    ) -> str:
        safe_block_id = json.dumps(block_id, ensure_ascii=False)
        safe_label = json.dumps(label, ensure_ascii=False)
        safe_capture_data_type = json.dumps(str(capture_data_type), ensure_ascii=False)
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
    const moduleId = String({module_id});
    const blockId = {safe_block_id};
    const captureDataType = {safe_capture_data_type};
    const label = {safe_label};
    const softRefreshEnabled = {str(soft_refresh_enabled).lower()};

    const toSafeString = (value) => String(value == null ? '' : value).trim();
    const pushDiag = (msg, data) => {{
        try {{
            window.__automationDiagnostics = window.__automationDiagnostics || [];
            window.__automationDiagnostics.push(Object.assign({{ ts: new Date().toISOString(), msg }}, data || {{}}));
            if (console && console.warn) console.warn('[automation]', msg, data || {{}});
        }} catch (_e) {{}}
    }};
    const patchValidateRequiredField = () => {{
        try {{
            if (typeof window.validateRequiredField !== 'function') return;
            if (window.validateRequiredField.__safePatchedByAutomation) return;
            const original = window.validateRequiredField;
            const wrapped = function(...args) {{
                try {{
                    return original.apply(this, args);
                }} catch (_err) {{
                    try {{
                        const candidate = args.length ? args[0] : null;
                        try {{ pushDiag('validateRequiredField original threw', {{ err: (_err && _err.message) || String(_err), args_length: args ? args.length : 0 }}); }} catch(_e){{}}
                        let el = null;
                        if (candidate && candidate.nodeType) el = candidate;
                        else if (candidate && typeof candidate === 'object' && candidate.jquery) el = candidate;
                        else el = (this && this.form) ? this.form : document.activeElement;

                        if (el) {{
                            const $el = (typeof window.$ === 'function') ? window.$(el) : null;
                            if ($el && $el.length) {{
                                try {{
                                    const candidateSummary = (function() {{
                                        try {{
                                            if ($el && $el.length) return {{ html: ($el.html && $el.html().slice(0,200)) || null, id: $el.attr && $el.attr('id') || null, class: $el.attr && $el.attr('class') || null }};
                                        }} catch(_e){{}}
                                        return null;
                                    }})();
                                    pushDiag('sanitizing inputs for candidate', {{ candidate: candidateSummary }});
                                }} catch(_e){{}}
                                $el.find('input, select, textarea').each(function() {{
                                    try {{
                                        const $i = (typeof window.$ === 'function') ? window.$(this) : null;
                                        if ($i) {{
                                            if ($i.val() == null) $i.val('');
                                            if ($i.attr && $i.attr('value') == null) $i.attr('value','');
                                        }}
                                    }} catch (_e) {{}}
                                }});
                            }}
                        }}
                    }} catch (_e) {{}}
                    try {{
                        return original.apply(this, args);
                    }} catch (_e2) {{
                        try {{ pushDiag('validateRequiredField retry failed', {{ err: (_e2 && _e2.message) || String(_e2) }}); }} catch(_e){{}}
                        const candidate = args.length ? args[0] : null;
                        return toSafeString(candidate) !== '';
                    }}
                }}
            }};
            wrapped.__safePatchedByAutomation = true;
            wrapped.__original = original;
            window.validateRequiredField = wrapped;
        }} catch (_e) {{}}
    }};

    const ensureHiddenValue = (form, name, value) => {{
        if (!form || !form.length) return;
        const normalized = toSafeString(value);
        let field = form.find("input[name='" + name + "']").first();
        if (!field.length) {{
            form.append('<input type="hidden" name="' + name + '" />');
            field = form.find("input[name='" + name + "']").first();
        }}
        field.val(normalized);
    }};

    const ensureRequiredFields = (liNode, fallbackType, fallbackElementId) => {{
        if (!liNode || !liNode.length) return;
        const form = liNode.find('form.frmGeneric').first();
        if (!form.length) return;

        let resolvedElementId = toSafeString(
            liNode.find("input[name='elementId']").first().val()
            || liNode.data('elementId')
            || fallbackElementId
        );
        if (!resolvedElementId) {{
            resolvedElementId = 'tmp-' + blockId + '-' + Date.now().toString();
        }}
        ensureHiddenValue(form, 'elementId', resolvedElementId);
        liNode.data('elementId', resolvedElementId);
        liNode.attr('data-id', 'element' + resolvedElementId);
        liNode.find('.scp-attachments').attr('elementId', resolvedElementId);

        const desiredType = toSafeString(fallbackType || '1') || '1';
        const typeSelect = form.find("select[name='captureDataType']").first();
        if (typeSelect.length) {{
            typeSelect.val(desiredType).trigger('change');
        }} else {{
            ensureHiddenValue(form, 'captureDataType', desiredType);
        }}
        liNode.data('captureDataType', desiredType);
    }};

    const softRefreshUi = (targets = []) => {{
        try {{
            if (!window.editor || !window.$) return;
            const normalizeTarget = (candidate) => {{
                if (!candidate) return null;
                const $candidate = (candidate.jquery) ? candidate : window.$(candidate);
                if (!$candidate || !$candidate.length) return null;
                if ($candidate.is('li.element-capture')) return $candidate;
                const parentLi = $candidate.closest('li.element-capture');
                return parentLi && parentLi.length ? parentLi : null;
            }};

            const list = Array.isArray(targets) ? targets : [targets];
            for (const item of list) {{
                const liNode = normalizeTarget(item);
                if (!liNode || !liNode.length) continue;
                const form = liNode.find('form.frmGeneric').first();
                if (!form.length) continue;
                if (typeof window.editor.setForm === 'function') window.editor.setForm(form);
                if (typeof window.editor.updateDataElement === 'function') {{
                    const refreshed = window.editor.updateDataElement(liNode) || {{}};
                    liNode.data(Object.assign({{}}, liNode.data() || {{}}, refreshed));
                }}
                form.find('input, select, textarea').trigger('change');
            }}

            const mainNode = (typeof window.editor.getMain === 'function') ? window.editor.getMain() : null;
            if (mainNode && mainNode.length) {{
                mainNode.find('ol.sortableLists').trigger('sortupdate');
            }}
        }} catch (_e) {{}}
    }};

    patchValidateRequiredField();

    if (!window.editor || !window.$ || !window.formDefault || !window.itemPoll) {{
        return {{ status_code: 0, endpoint, body_preview: 'missing_editor_dependencies', response_json: null }};
    }}

    const main = window.editor.getMain();
    if (!main || !main.length) {{
        return {{ status_code: 0, endpoint, body_preview: 'missing_editor_main', response_json: null }};
    }}

    window.editor.setForm(window.formDefault);
    const addedMain = window.editor.add(window.formDefault, window.itemPoll);
    if (typeof window.getSelectElementType === 'function') {{
        window.getSelectElementType(addedMain, false);
    }}

    const li = main.children('li').last();
    li.data('captureDataType', (window.captureDataTypeEnum && window.captureDataTypeEnum.integer) ? window.captureDataTypeEnum.integer : '1');
    li.data('irBlockId', blockId);
    ensureRequiredFields(li, captureDataType, null);

    const newJsonElement = JSON.stringify(li.data() || {{}});
    const currentJson = (typeof window.editor.getString === 'function') ? window.editor.getString() : '[]';
    try {{ pushDiag('editor.getString currentJson', {{ length: (currentJson && currentJson.length) || 0, sample: (typeof currentJson === 'string' ? currentJson.slice(0,200) : null) }}); }} catch(_e){{}}

    const ajaxResult = await new Promise((resolve) => {{
        window.$.ajax({{
            headers: {{ saveAction: true }},
            method: 'POST',
            url: '/moduleCapture/update',
            data: {{
                type: 'newElement',
                element: newJsonElement,
                elementsArray: currentJson,
                moduleId: moduleId
            }}
        }}).done((data, _textStatus, jqXHR) => resolve({{ ok: true, data, status: jqXHR.status }}))
          .fail((jqXHR) => resolve({{ ok: false, status: jqXHR.status || 0, text: jqXHR.responseText || '' }}));
    }});

    if (!ajaxResult.ok) {{
        try {{ pushDiag('ajax newElement failed', {{ status: ajaxResult.status, text: (ajaxResult.text||'').slice(0,400) }}); }} catch(_e){{}}
        return {{
            status_code: ajaxResult.status,
            endpoint,
            body_preview: String(ajaxResult.text || '').slice(0, 400),
            response_json: null
        }};
    }}

    const createdElementId = ajaxResult.data && ajaxResult.data.elementId ? ajaxResult.data.elementId : null;
    if (createdElementId !== null) {{
        li.find("input[name='elementId']").val(createdElementId);
        li.find('.scp-attachments').attr('elementId', createdElementId);
        li.data('elementId', createdElementId);
        li.attr('data-id', 'element' + String(createdElementId));
    }}

    li.attr('id', 'element' + String(main.find('li.element-capture').length));
    const typeSelect = li.find("select[name='captureDataType']").first();
    if (typeSelect.length) {{
        typeSelect.val(captureDataType).trigger('change');
    }}
    li.find("input[name='name']").first().val(label);
    li.data('irBlockId', blockId);
    ensureRequiredFields(li, captureDataType, createdElementId);
    if (softRefreshEnabled) softRefreshUi([li]);

    let response_json = null;
    try {{
        response_json = (ajaxResult.data && typeof ajaxResult.data === 'object') ? ajaxResult.data : null;
    }} catch (_e) {{}}
    try {{
        const diags = (window.__automationDiagnostics || []).slice(-200);
        if (response_json && typeof response_json === 'object') response_json.__automationDiagnostics = diags;
        else if (diags && diags.length) response_json = {{ __automationDiagnostics: diags }};
    }} catch (_e) {{}}

    return {{
        status_code: ajaxResult.status,
        endpoint,
        body_preview: JSON.stringify(ajaxResult.data || {{}}).slice(0, 400),
        response_json
    }};
}}"""

    @staticmethod
    def _build_update_block_script(
        module_id: int,
        block_id: str,
        block_element_id: str | None,
        mandatory: bool,
        available_na: bool,
        allowed_photos: bool,
        mandatory_photos: bool,
        multiple_photos: bool,
        options: list[Any],
        soft_refresh_enabled: bool = True,
    ) -> str:
        safe_block_id = json.dumps(block_id, ensure_ascii=False)
        safe_block_element_id = json.dumps(block_element_id, ensure_ascii=False)
        safe_options = json.dumps(options, ensure_ascii=False)
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
    const moduleId = String({module_id});
    const blockId = {safe_block_id};
    const blockElementId = {safe_block_element_id};
    const softRefreshEnabled = {str(soft_refresh_enabled).lower()};

    const toSafeString = (value) => String(value == null ? '' : value).trim();
    const patchValidateRequiredField = () => {{
        try {{
            if (typeof window.validateRequiredField !== 'function') return;
            if (window.validateRequiredField.__safePatchedByAutomation) return;
            const original = window.validateRequiredField;
            const wrapped = function(...args) {{
                try {{
                    return original.apply(this, args);
                }} catch (_err) {{
                    try {{
                        const candidate = args.length ? args[0] : null;
                        let el = null;
                        if (candidate && candidate.nodeType) el = candidate;
                        else if (candidate && typeof candidate === 'object' && candidate.jquery) el = candidate;
                        else el = (this && this.form) ? this.form : document.activeElement;

                        if (el) {{
                            const $el = (typeof window.$ === 'function') ? window.$(el) : null;
                            if ($el && $el.length) {{
                                $el.find('input, select, textarea').each(function() {{
                                    try {{
                                        const $i = (typeof window.$ === 'function') ? window.$(this) : null;
                                        if ($i) {{
                                            if ($i.val() == null) $i.val('');
                                            if ($i.attr && $i.attr('value') == null) $i.attr('value','');
                                        }}
                                    }} catch (_e) {{}}
                                }});
                            }}
                        }}
                    }} catch (_e) {{}}
                    try {{
                        return original.apply(this, args);
                    }} catch (_e2) {{
                        const candidate = args.length ? args[0] : null;
                        return toSafeString(candidate) !== '';
                    }}
                }}
            }};
            wrapped.__safePatchedByAutomation = true;
            wrapped.__original = original;
            window.validateRequiredField = wrapped;
        }} catch (_e) {{}}
    }};

    const ensureHiddenValue = (form, name, value) => {{
        if (!form || !form.length) return;
        let field = form.find("input[name='" + name + "']").first();
        if (!field.length) {{
            form.append('<input type="hidden" name="' + name + '" />');
            field = form.find("input[name='" + name + "']").first();
        }}
        field.val(toSafeString(value));
    }};

    const ensureRequiredFields = (liNode) => {{
        if (!liNode || !liNode.length) return;
        const form = liNode.find('form.frmGeneric').first();
        if (!form.length) return;
        let elementId = toSafeString(
            liNode.find("input[name='elementId']").first().val()
            || liNode.data('elementId')
            || blockElementId
        );
        if (!elementId) {{
            elementId = 'tmp-' + blockId + '-' + Date.now().toString();
        }}
        ensureHiddenValue(form, 'elementId', elementId);
        liNode.data('elementId', elementId);
        liNode.attr('data-id', 'element' + elementId);
        liNode.find('.scp-attachments').attr('elementId', elementId);

        const existingType = toSafeString(
            form.find("select[name='captureDataType']").first().val()
            || liNode.data('captureDataType')
        );
        const resolvedType = existingType || '1';
        const typeSelect = form.find("select[name='captureDataType']").first();
        if (typeSelect.length) typeSelect.val(resolvedType).trigger('change');
        else ensureHiddenValue(form, 'captureDataType', resolvedType);
        liNode.data('captureDataType', resolvedType);
    }};

    const cleanupInvalidRows = (mainNode) => {{
        let removed = 0;
        if (!mainNode || !mainNode.length) return removed;
        mainNode.find('li.element-capture').each(function() {{
            const $li = window.$(this);
            const form = $li.find('form.frmGeneric').first();
            if (!form.length) return;
            const elementId = toSafeString(
                form.find("input[name='elementId']").first().val() || $li.data('elementId')
            );
            const captureType = toSafeString(
                form.find("select[name='captureDataType']").first().val()
                || form.find("input[name='captureDataType']").first().val()
                || $li.data('captureDataType')
            );
            if (!elementId || !captureType) {{
                try {{ $li.remove(); removed += 1; }} catch (_e) {{}}
            }}
        }});
        return removed;
    }};

    const resolveCaptureTypeFromLi = (liNode) => {{
        if (!liNode || !liNode.length) return '';
        try {{
            const form = liNode.find('form.frmGeneric').first();
            if (form && form.length) {{
                const fromSelect = toSafeString(form.find("select[name='captureDataType']").first().val());
                if (fromSelect) return fromSelect;
                const fromInput = toSafeString(form.find("input[name='captureDataType']").first().val());
                if (fromInput) return fromInput;
            }}
        }} catch (_e) {{}}
        return toSafeString(liNode.data('captureDataType'));
    }};

    const softRefreshUi = (targets = []) => {{
        try {{
            if (!window.editor || !window.$) return;
            const normalizeTarget = (candidate) => {{
                if (!candidate) return null;
                const $candidate = (candidate.jquery) ? candidate : window.$(candidate);
                if (!$candidate || !$candidate.length) return null;
                if ($candidate.is('li.element-capture')) return $candidate;
                const parentLi = $candidate.closest('li.element-capture');
                return parentLi && parentLi.length ? parentLi : null;
            }};

            const list = Array.isArray(targets) ? targets : [targets];
            for (const item of list) {{
                const liNode = normalizeTarget(item);
                if (!liNode || !liNode.length) continue;
                const form = liNode.find('form.frmGeneric').first();
                if (!form.length) continue;
                if (typeof window.editor.setForm === 'function') window.editor.setForm(form);
                if (typeof window.editor.updateDataElement === 'function') {{
                    const refreshed = window.editor.updateDataElement(liNode) || {{}};
                    liNode.data(Object.assign({{}}, liNode.data() || {{}}, refreshed));
                }}
                form.find('input, select, textarea').trigger('change');
            }}

            const mainNode = (typeof window.editor.getMain === 'function') ? window.editor.getMain() : null;
            if (mainNode && mainNode.length) {{
                mainNode.find('ol.sortableLists').trigger('sortupdate');
            }}
        }} catch (_e) {{}}
    }};

    patchValidateRequiredField();

    if (!window.editor || !window.$) {{
        return {{ status_code: 0, endpoint, body_preview: 'missing_editor_dependencies', response_json: null }};
    }}

    const main = window.editor.getMain();
    const findByBlockId = () => main.children('li').filter(function() {{
        return String(window.$(this).data('irBlockId') || '') === blockId;
    }}).first();

    const findByElementId = () => main.children('li').filter(function() {{
        const li = window.$(this);
        const fromData = li.data('elementId');
        const fromInput = li.find("input[name='elementId']").first().val();
        const fromAttr = li.attr('data-id') || '';
        const expected = String(blockElementId || '');
        if (!expected) return false;
        if (String(fromData || '') === expected) return true;
        if (String(fromInput || '') === expected) return true;
        if (String(fromAttr).replace('element', '') === expected) return true;
        return false;
    }}).first();

    const applyOnModelElements = async () => {{
        const capture = (window.module && window.module.moduleCapture) || {{}};
        const wrapper = capture.elements || {{}};
        const elements = Array.isArray(wrapper.elements) ? wrapper.elements : [];

        let candidate = null;
        if (blockElementId !== null && blockElementId !== undefined && String(blockElementId).trim() !== '') {{
            candidate = elements.find((item) => String((item || {{}}).elementId || '') === String(blockElementId)) || null;
        }}
        if (!candidate) {{
            candidate = elements.find((item) => String((item || {{}}).irBlockId || '') === blockId) || null;
        }}
        if (!candidate) {{
            return {{ status_code: 0, endpoint, body_preview: 'block_not_found', response_json: null }};
        }}

        candidate.mandatory = {str(mandatory).lower()};
        candidate.availableNA = {str(available_na).lower()};
        candidate.allowedPhotos = {str(allowed_photos).lower()};
        candidate.mandatoryPhotos = {str(mandatory_photos).lower()};
        candidate.multiplePhotos = {str(multiple_photos).lower()};
        candidate.options = {safe_options};
        candidate.irBlockId = blockId;

        const body = new URLSearchParams();
        body.set('type', 'element');
        body.set('moduleId', moduleId);
        body.set('elementsArray', JSON.stringify(elements));
        body.set('ownerElementId', '');

        const res = await fetch(endpoint, {{
            method: 'POST',
            credentials: 'include',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
            }},
            body: body.toString()
        }});

        const text = await res.text();
        let response_json = null;
        try {{ response_json = JSON.parse(text); }} catch (_e) {{}}
        const liForRefresh = findByElementId().length ? findByElementId() : findByBlockId();
        if (softRefreshEnabled) softRefreshUi([liForRefresh]);
        try {{
            const diags = (window.__automationDiagnostics || []).slice(-200);
            if (response_json && typeof response_json === 'object') response_json.__automationDiagnostics = diags;
            else if (diags && diags.length) response_json = {{ __automationDiagnostics: diags }};
        }} catch (_e) {{}}
        return {{
            status_code: res.status,
            endpoint,
            body_preview: text.slice(0, 400),
            response_json
        }};
    }};

    const liByBlock = findByBlockId();
    const liByElementId = findByElementId();
    const li = liByBlock && liByBlock.length ? liByBlock : liByElementId;

    if (!li || !li.length) {{
        return await applyOnModelElements();
    }}

    const frm = li.find('form.frmGeneric').first();
    if (!frm.length) {{
        return await applyOnModelElements();
    }}

    const setField = (selector, value, asCheck = false) => {{
        const target = frm.find(selector).first();
        if (!target.length) return;
        if (asCheck) target.prop('checked', !!value);
        else target.val(value);
    }};

    setField("input[name='mandatory']", {str(mandatory).lower()}, true);
    setField("input[name='availableNA']", {str(available_na).lower()}, true);
    setField("input[name='allowedPhotos']", {str(allowed_photos).lower()}, true);
    setField("input[name='mandatoryPhotos']", {str(mandatory_photos).lower()}, true);
    setField("input[name='multiplePhotos']", {str(multiple_photos).lower()}, true);

    ensureRequiredFields(li);
    window.editor.setForm(frm);
    const updated = window.editor.updateDataElement(li) || {{}};
    const data = Object.assign({{}}, li.data() || {{}}, updated, {{
        irBlockId: blockId,
        options: {safe_options}
    }});
    li.data(data);

    const removedInvalidRows = cleanupInvalidRows(main);
    try {{ pushDiag('cleanupInvalidRows result', {{ removedInvalidRows }}); }} catch(_e){{}}

    const serialized = (typeof window.editor.getString === 'function') ? window.editor.getString() : '[]';
    try {{ pushDiag('editor.getString serialized', {{ length: (serialized && serialized.length) || 0, sample: (typeof serialized === 'string' ? serialized.slice(0,200) : null) }}); }} catch(_e){{}}

    const body = new URLSearchParams();
    body.set('type', 'element');
    body.set('moduleId', moduleId);
    body.set('elementsArray', serialized);
    body.set('ownerElementId', '');

    const res = await fetch(endpoint, {{
        method: 'POST',
        credentials: 'include',
        headers: {{
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }},
        body: body.toString()
    }});

    const text = await res.text();
    let response_json = null;
    try {{ response_json = JSON.parse(text); }} catch (_e) {{}}
    if (softRefreshEnabled) softRefreshUi([li]);
    try {{
        const diags = (window.__automationDiagnostics || []).slice(-200);
        if (response_json && typeof response_json === 'object') response_json.__automationDiagnostics = diags;
        else if (diags && diags.length) response_json = {{ __automationDiagnostics: diags }};
    }} catch (_e) {{}}

    return {{
        status_code: res.status,
        endpoint,
        body_preview: ('removedInvalidRows=' + String(removedInvalidRows) + '; ' + text).slice(0, 400),
        response_json
    }};
}}"""

    @staticmethod
    def _build_attach_condition_script(
        module_id: int,
        parent_block_id: str,
        child_block_id: str,
        condition_type: str,
        condition_value: str | None,
        parent_element_id: str | None,
        child_element_id: str | None,
        soft_refresh_enabled: bool = True,
    ) -> str:
        safe_parent_block_id = json.dumps(parent_block_id, ensure_ascii=False)
        safe_child_block_id = json.dumps(child_block_id, ensure_ascii=False)
        safe_condition_type = json.dumps(condition_type, ensure_ascii=False)
        safe_condition_value = json.dumps(condition_value, ensure_ascii=False)
        safe_parent_element_id = json.dumps(parent_element_id, ensure_ascii=False)
        safe_child_element_id = json.dumps(child_element_id, ensure_ascii=False)
        return f"""async () => {{
    const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith('http'))
        ? window.location.origin
        : 'https://webapp.storecheck.com';
    const endpoint = new URL('/moduleCapture/update', baseUrl).toString();
    const moduleId = String({module_id});
    const parentBlockId = {safe_parent_block_id};
    const childBlockId = {safe_child_block_id};
    const parentElementId = {safe_parent_element_id};
    const childElementId = {safe_child_element_id};
    const conditionType = {safe_condition_type};
    const conditionValueRaw = {safe_condition_value};
    const softRefreshEnabled = {str(soft_refresh_enabled).lower()};

    const toSafeString = (value) => String(value == null ? '' : value).trim();
    const patchValidateRequiredField = () => {{
        try {{
            if (typeof window.validateRequiredField !== 'function') return;
            if (window.validateRequiredField.__safePatchedByAutomation) return;
            const original = window.validateRequiredField;
            const wrapped = function(...args) {{
                try {{
                    return original.apply(this, args);
                }} catch (_err) {{
                    try {{
                        const candidate = args.length ? args[0] : null;
                        let el = null;
                        if (candidate && candidate.nodeType) el = candidate;
                        else if (candidate && typeof candidate === 'object' && candidate.jquery) el = candidate;
                        else el = (this && this.form) ? this.form : document.activeElement;

                        if (el) {{
                            const $el = (typeof window.$ === 'function') ? window.$(el) : null;
                            if ($el && $el.length) {{
                                $el.find('input, select, textarea').each(function() {{
                                    try {{
                                        const $i = (typeof window.$ === 'function') ? window.$(this) : null;
                                        if ($i) {{
                                            if ($i.val() == null) $i.val('');
                                            if ($i.attr && $i.attr('value') == null) $i.attr('value','');
                                        }}
                                    }} catch (_e) {{}}
                                }});
                            }}
                        }}
                    }} catch (_e) {{}}
                    try {{
                        return original.apply(this, args);
                    }} catch (_e2) {{
                        const candidate = args.length ? args[0] : null;
                        return toSafeString(candidate) !== '';
                    }}
                }}
            }};
            wrapped.__safePatchedByAutomation = true;
            wrapped.__original = original;
            window.validateRequiredField = wrapped;
        }} catch (_e) {{}}
    }};

    const ensureHiddenValue = (form, name, value) => {{
        if (!form || !form.length) return;
        let field = form.find("input[name='" + name + "']").first();
        if (!field.length) {{
            form.append('<input type="hidden" name="' + name + '" />');
            field = form.find("input[name='" + name + "']").first();
        }}
        field.val(toSafeString(value));
    }};

    const ensureRequiredFields = (liNode, fallbackElementId) => {{
        if (!liNode || !liNode.length) return;
        const form = liNode.find('form.frmGeneric').first();
        if (!form.length) return;
        let elementId = toSafeString(
            liNode.find("input[name='elementId']").first().val()
            || liNode.data('elementId')
            || fallbackElementId
        );
        if (!elementId) {{
            elementId = 'tmp-condition-' + Date.now().toString();
        }}
        ensureHiddenValue(form, 'elementId', elementId);
        liNode.data('elementId', elementId);
        liNode.attr('data-id', 'element' + elementId);
        liNode.find('.scp-attachments').attr('elementId', elementId);

        const existingType = toSafeString(
            form.find("select[name='captureDataType']").first().val()
            || form.find("input[name='captureDataType']").first().val()
            || liNode.data('captureDataType')
        );
        const resolvedType = existingType || '1';
        const typeSelect = form.find("select[name='captureDataType']").first();
        if (typeSelect.length) typeSelect.val(resolvedType).trigger('change');
        else ensureHiddenValue(form, 'captureDataType', resolvedType);
        liNode.data('captureDataType', resolvedType);
    }};

    const cleanupInvalidRows = (mainNode) => {{
        let removed = 0;
        if (!mainNode || !mainNode.length) return removed;
        mainNode.find('li.element-capture').each(function() {{
            const $li = window.$(this);
            const form = $li.find('form.frmGeneric').first();
            if (!form.length) return;
            const elementId = toSafeString(
                form.find("input[name='elementId']").first().val() || $li.data('elementId')
            );
            const captureType = toSafeString(
                form.find("select[name='captureDataType']").first().val()
                || form.find("input[name='captureDataType']").first().val()
                || $li.data('captureDataType')
            );
            if (!elementId || !captureType) {{
                try {{ $li.remove(); removed += 1; }} catch (_e) {{}}
            }}
        }});
        return removed;
    }};

    const resolveCaptureTypeFromLi = (liNode) => {{
        if (!liNode || !liNode.length) return '';
        try {{
            const form = liNode.find('form.frmGeneric').first();
            if (form && form.length) {{
                const fromSelect = toSafeString(form.find("select[name='captureDataType']").first().val());
                if (fromSelect) return fromSelect;
                const fromInput = toSafeString(form.find("input[name='captureDataType']").first().val());
                if (fromInput) return fromInput;
            }}
        }} catch (_e) {{}}
        return toSafeString(liNode.data('captureDataType'));
    }};

    const softRefreshUi = (targets = []) => {{
        try {{
            if (!window.editor || !window.$) return;
            const normalizeTarget = (candidate) => {{
                if (!candidate) return null;
                const $candidate = (candidate.jquery) ? candidate : window.$(candidate);
                if (!$candidate || !$candidate.length) return null;
                if ($candidate.is('li.element-capture')) return $candidate;
                const parentLi = $candidate.closest('li.element-capture');
                return parentLi && parentLi.length ? parentLi : null;
            }};

            const list = Array.isArray(targets) ? targets : [targets];
            for (const item of list) {{
                const liNode = normalizeTarget(item);
                if (!liNode || !liNode.length) continue;
                const form = liNode.find('form.frmGeneric').first();
                if (!form.length) continue;
                if (typeof window.editor.setForm === 'function') window.editor.setForm(form);
                if (typeof window.editor.updateDataElement === 'function') {{
                    const refreshed = window.editor.updateDataElement(liNode) || {{}};
                    liNode.data(Object.assign({{}}, liNode.data() || {{}}, refreshed));
                }}
                form.find('input, select, textarea').trigger('change');
            }}

            const mainNode = (typeof window.editor.getMain === 'function') ? window.editor.getMain() : null;
            if (mainNode && mainNode.length) {{
                mainNode.find('ol.sortableLists').trigger('sortupdate');
            }}
        }} catch (_e) {{}}
    }};

    patchValidateRequiredField();

    if (!window.editor || !window.$) {{
        return {{ status_code: 0, endpoint, body_preview: 'missing_editor_dependencies', response_json: null }};
    }}

    const main = window.editor.getMain();
    const findByElementId = (targetId) => {{
        if (targetId === null || targetId === undefined || String(targetId).trim() === '') return window.$();
        const expected = String(targetId);
        return main.children('li').filter(function() {{
            const li = window.$(this);
            const fromData = li.data('elementId');
            const fromInput = li.find("input[name='elementId']").first().val();
            const fromAttr = li.attr('data-id') || '';
            if (String(fromData || '') === expected) return true;
            if (String(fromInput || '') === expected) return true;
            if (String(fromAttr).replace('element', '') === expected) return true;
            return false;
        }}).first();
    }};

    const findByIrBlockId = (targetBlockId) => main.children('li').filter(function() {{
        return String(window.$(this).data('irBlockId') || '') === String(targetBlockId || '');
    }}).first();

    const parent = findByElementId(parentElementId).length ? findByElementId(parentElementId) : findByIrBlockId(parentBlockId);
    const child = findByElementId(childElementId).length ? findByElementId(childElementId) : findByIrBlockId(childBlockId);

    const applyOnModelElements = async () => {{
        const capture = (window.module && window.module.moduleCapture) || {{}};
        const wrapper = capture.elements || {{}};
        const elements = Array.isArray(wrapper.elements) ? wrapper.elements : [];

        const findById = (targetId) => elements.find((item) => String((item || {{}}).elementId || '') === String(targetId || '')) || null;
        const parentModel = findById(parentElementId) || elements.find((item) => String((item || {{}}).irBlockId || '') === String(parentBlockId || '')) || null;
        const childModel = findById(childElementId) || elements.find((item) => String((item || {{}}).irBlockId || '') === String(childBlockId || '')) || null;

        if (!parentModel || !childModel) {{
            return {{ status_code: 0, endpoint, body_preview: 'parent_or_child_not_found', response_json: null }};
        }}

        const normalizedType = (conditionType || 'stage').toLowerCase();
        const normalizedValue = (() => {{
            const v = String(conditionValueRaw || '').toLowerCase();
            if (v === 'si' || v === 'yes' || v === '1') return '1';
            if (v === 'no' || v === '0') return '0';
            return '1';
        }})();

        parentModel.captureDataType = String(parentModel.captureDataType || childModel.parentCaptureDataType || '1');
        parentModel.children = Array.isArray(parentModel.children) ? parentModel.children : [];

        childModel.parentCaptureDataType = String(parentModel.captureDataType || '');
        childModel.typeConditionSelected = normalizedType;
        childModel.conditionTypeSelected = normalizedType;
        childModel.activeConditionAnswer = normalizedType === 'answer';
        childModel.activeConditionStage = normalizedType === 'stage';
        childModel.activeConditionNA = normalizedType === 'na';
        if (normalizedType === 'stage' || normalizedType === 'answer') {{
            childModel.answerCondition = normalizedValue;
            childModel.conditionValue = '';
            childModel.operatorCondition = '';
            childModel.valueCondition = '';
            childModel.lowerLimitCondition = '';
            childModel.upperLimitCondition = '';
        }}

        parentModel.children = parentModel.children.filter((item) => String((item || {{}}).elementId || '') !== String(childModel.elementId || ''));
        parentModel.children.push(childModel);

        const body = new URLSearchParams();
        body.set('type', 'element');
        body.set('moduleId', moduleId);
        body.set('elementsArray', JSON.stringify(elements));
        body.set('ownerElementId', '');

        const res = await fetch(endpoint, {{
            method: 'POST',
            credentials: 'include',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
            }},
            body: body.toString()
        }});

        const text = await res.text();
        let response_json = null;
        try {{ response_json = JSON.parse(text); }} catch (_e) {{}}
        const refreshedParent = findByElementId(parentElementId).length ? findByElementId(parentElementId) : findByIrBlockId(parentBlockId);
        const refreshedChild = findByElementId(childElementId).length ? findByElementId(childElementId) : findByIrBlockId(childBlockId);
        if (softRefreshEnabled) softRefreshUi([refreshedParent, refreshedChild]);
        try {{
            const diags = (window.__automationDiagnostics || []).slice(-200);
            if (response_json && typeof response_json === 'object') response_json.__automationDiagnostics = diags;
            else if (diags && diags.length) response_json = {{ __automationDiagnostics: diags }};
        }} catch (_e) {{}}
        return {{
            status_code: res.status,
            endpoint,
            body_preview: text.slice(0, 400),
            response_json
        }};
    }};

    if (!parent || !parent.length || !child || !child.length) {{
        return await applyOnModelElements();
    }}

    ensureRequiredFields(parent, parentElementId);
    ensureRequiredFields(child, childElementId);

    let childList = parent.children('ol.sortableLists').first();
    if (!childList.length) {{
        childList = window.$('<ol class="sortableLists"></ol>');
        parent.append(childList);
    }}
    child.appendTo(childList);

    parent.removeClass('sortableListsClosed').addClass('sortableListsOpen');
    parent.find('> .d-inline-flex .sortableListsOpener').removeClass('invisible');

    const parentData = parent.data() || {{}};
    const childData = Object.assign({{}}, child.data() || {{}});
    const normalizedType = (conditionType || 'stage').toLowerCase();
    const normalizedValue = (() => {{
        const v = String(conditionValueRaw || '').toLowerCase();
        if (v === 'si' || v === 'yes' || v === '1') return '1';
        if (v === 'no' || v === '0') return '0';
        return '1';
    }})();

    const parentCaptureType = (
        resolveCaptureTypeFromLi(parent)
        || toSafeString(parentData.captureDataType)
        || toSafeString(childData.parentCaptureDataType)
        || '1'
    );
    childData.parentCaptureDataType = parentCaptureType;
    childData.typeConditionSelected = normalizedType;
    childData.conditionTypeSelected = normalizedType;
    childData.activeConditionAnswer = normalizedType === 'answer';
    childData.activeConditionStage = normalizedType === 'stage';
    childData.activeConditionNA = normalizedType === 'na';

    if (normalizedType === 'stage' || normalizedType === 'answer') {{
        childData.answerCondition = normalizedValue;
        childData.conditionValue = '';
    }}

    child.data(childData);

    const childForm = child.find('form.frmGeneric').first();
    if (childForm.length) {{
        const setChecked = (name, checked) => {{
            const field = childForm.find(`input[name='${{name}}']`).first();
            if (field.length) field.prop('checked', !!checked);
        }};

        const setValue = (name, value) => {{
            const field = childForm.find(`[name='${{name}}']`).first();
            if (field.length) field.val(value);
        }};
        const setSelectValueSafe = (name, value, fallbackLabel) => {{
            const field = childForm.find(`select[name='${{name}}']`).first();
            if (!field.length) {{
                setValue(name, value);
                return;
            }}
            const stringValue = String(value == null ? '' : value);
            if (!field.find(`option[value='${{stringValue}}']`).length) {{
                try {{
                    field.append(window.$('<option></option>').attr('value', stringValue).text(fallbackLabel || stringValue));
                }} catch (_e) {{}}
            }}
            field.val(stringValue).trigger('change');
        }};

        setChecked('activeConditionAnswer', normalizedType === 'answer');
        setChecked('activeConditionStage', normalizedType === 'stage');
        setChecked('activeConditionNA', normalizedType === 'na');
        setValue('typeConditionSelected', normalizedType);
        setValue('conditionTypeSelected', normalizedType);
        setValue('parentCaptureDataType', parentCaptureType);
        if (normalizedType === 'stage' || normalizedType === 'answer') {{
            const answerLabel = normalizedValue === '1' ? 'Si' : (normalizedValue === '0' ? 'No' : normalizedValue);
            setSelectValueSafe('answerCondition', normalizedValue, answerLabel);
            setValue('conditionValue', '');
            setValue('operatorCondition', '');
            setValue('valueCondition', '');
            setValue('lowerLimitCondition', '');
            setValue('upperLimitCondition', '');
        }}

        window.editor.setForm(childForm);
        const refreshed = window.editor.updateDataElement(child) || {{}};
        child.data(Object.assign({{}}, child.data() || {{}}, refreshed, {{
            typeConditionSelected: normalizedType,
            activeConditionAnswer: normalizedType === 'answer',
            activeConditionStage: normalizedType === 'stage',
            activeConditionNA: normalizedType === 'na',
            answerCondition: (normalizedType === 'stage' || normalizedType === 'answer') ? normalizedValue : (child.data() || {{}}).answerCondition,
            conditionValue: ''
        }}));
    }}

    const removedInvalidRows = cleanupInvalidRows(main);
    const serialized = (typeof window.editor.getString === 'function') ? window.editor.getString() : '[]';

    const normalizeConditionedChildrenPayload = (jsonText) => {{
        try {{
            const data = JSON.parse(String(jsonText || '[]'));
            if (!Array.isArray(data)) return jsonText;

            const walk = (nodes, parentCaptureType = null) => {{
                if (!Array.isArray(nodes)) return;
                for (const node of nodes) {{
                    if (!node || typeof node !== 'object') continue;

                    const currentCaptureType = String((node.captureDataType ?? '') || '').trim();
                    const inheritedCaptureType = parentCaptureType ? String(parentCaptureType).trim() : '';
                    const isChild = !!inheritedCaptureType;

                    if (isChild) {{
                        const currentParentCaptureType = String((node.parentCaptureDataType ?? '') || '').trim();
                        if (!currentParentCaptureType) {{
                            node.parentCaptureDataType = inheritedCaptureType;
                        }}

                        const normalizedType = String((node.typeConditionSelected ?? node.conditionTypeSelected ?? '') || '').trim();
                        if (normalizedType) {{
                            node.typeConditionSelected = normalizedType;
                            node.conditionTypeSelected = normalizedType;
                        }}
                    }}

                    if (Array.isArray(node.children) && node.children.length) {{
                        walk(node.children, currentCaptureType || inheritedCaptureType || null);
                    }}
                }}
            }};

            walk(data, null);
            return JSON.stringify(data);
        }} catch (_e) {{
            return jsonText;
        }}
    }};

    const normalizedSerialized = normalizeConditionedChildrenPayload(serialized);

    const body = new URLSearchParams();
    body.set('type', 'element');
    body.set('moduleId', moduleId);
    body.set('elementsArray', normalizedSerialized);
    body.set('ownerElementId', '');

    const res = await fetch(endpoint, {{
        method: 'POST',
        credentials: 'include',
        headers: {{
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }},
        body: body.toString()
    }});

    const text = await res.text();
    let response_json = null;
    try {{ response_json = JSON.parse(text); }} catch (_e) {{}}
    if (softRefreshEnabled) softRefreshUi([parent, child]);
    try {{
        const diags = (window.__automationDiagnostics || []).slice(-200);
        if (response_json && typeof response_json === 'object') response_json.__automationDiagnostics = diags;
        else if (diags && diags.length) response_json = {{ __automationDiagnostics: diags }};
    }} catch (_e) {{}}

    return {{
        status_code: res.status,
        endpoint,
        body_preview: ('removedInvalidRows=' + String(removedInvalidRows) + '; ' + text).slice(0, 400),
        response_json
    }};
}}"""
