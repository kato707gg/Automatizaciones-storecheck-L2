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
    ) -> Any:
        ...

    def get_network_request(self, reqid: int) -> Any:
        ...


@dataclass
class CallableMcpChromeBridge:
    """Adapter mínimo para conectar funciones sueltas del bridge MCP."""

    evaluate_fn: Callable[[str], Any]
    list_requests_fn: Callable[[list[str] | None, int, bool], Any]
    get_request_fn: Callable[[int], Any]

    def evaluate_script(self, function: str) -> Any:
        return self.evaluate_fn(function)

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
    ) -> Any:
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
        if reqid is None and status_code == 200:
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
        if reqid is None and status_code == 200:
            reqid = self._fallback_reqid(prefix=3)

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
        if reqid is None and status_code == 200:
            reqid = self._fallback_reqid(prefix=2)

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

    @staticmethod
    def _build_update_scope_script(module_id: int, scope_type_id: int) -> str:
        return f"""async () => {{
  const body = new URLSearchParams();
  body.set('type', 'moduleScopeType');
  body.set('moduleId', String({module_id}));
  body.set('moduleScopeTypeId', String({scope_type_id}));

  const res = await fetch('/moduleCapture/update', {{
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
    endpoint: '/moduleCapture/update',
    body_preview: text.slice(0, 400),
    response_json
  }};
}}"""

    @staticmethod
    def _build_module_definition_script(module_id: int) -> str:
        return f"""async () => {{
  const endpoint = '/moduleCapture/syncTaskData?type=moduleDefinition&moduleId=' + String({module_id});
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
    const body = new URLSearchParams();
    const elements = {serialized_elements};
    body.set('type', 'element');
    body.set('moduleId', String({module_id}));
    body.set('elementsArray', JSON.stringify(elements));

    const res = await fetch('/moduleCapture/update', {{
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
        endpoint: '/moduleCapture/update',
        body_preview: text.slice(0, 400),
        response_json
    }};
}}"""
