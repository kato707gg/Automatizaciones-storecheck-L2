from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Callable


def _load_callable_from_ref(ref: str, env_name: str) -> Callable[..., Any]:
    ref = (ref or "").strip()
    if not ref:
        raise RuntimeError(
            f"No se configuró {env_name}. Usa formato 'paquete.modulo:funcion'."
        )

    if ":" not in ref:
        raise RuntimeError(
            f"{env_name} debe usar formato 'paquete.modulo:funcion'. Valor recibido: {ref}"
        )

    module_name, func_name = ref.split(":", 1)
    module_name = module_name.strip()
    func_name = func_name.strip()
    if not module_name or not func_name:
        raise RuntimeError(
            f"{env_name} inválido. Usa formato 'paquete.modulo:funcion'."
        )

    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, func_name)
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar {env_name}={ref}: {exc}") from exc

    if not callable(fn):
        raise RuntimeError(f"{env_name}={ref} no es invocable.")

    return fn


class EnvCallableMcpChromeBridge:
    """
    Bridge MCP concreto que conecta funciones de cliente MCP definidas por entorno.

    Variables requeridas:
    - STORECHECK_MCP_EVALUATE_FN="paquete.modulo:funcion"
    - STORECHECK_MCP_LIST_REQUESTS_FN="paquete.modulo:funcion"
    - STORECHECK_MCP_GET_REQUEST_FN="paquete.modulo:funcion"

    La función de listado puede aceptar nombres snake_case o camelCase.
    """

    def __init__(self) -> None:
        self._evaluate_fn = _load_callable_from_ref(
            os.getenv("STORECHECK_MCP_EVALUATE_FN", ""),
            "STORECHECK_MCP_EVALUATE_FN",
        )
        self._list_requests_fn = _load_callable_from_ref(
            os.getenv("STORECHECK_MCP_LIST_REQUESTS_FN", ""),
            "STORECHECK_MCP_LIST_REQUESTS_FN",
        )
        self._get_request_fn = _load_callable_from_ref(
            os.getenv("STORECHECK_MCP_GET_REQUEST_FN", ""),
            "STORECHECK_MCP_GET_REQUEST_FN",
        )

    def evaluate_script(self, function: str) -> Any:
        return self._evaluate_fn(function)

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
    ) -> Any:
        fn = self._list_requests_fn

        kwargs_snake = {
            "resource_types": resource_types,
            "page_size": page_size,
            "include_preserved_requests": include_preserved_requests,
        }
        kwargs_camel = {
            "resourceTypes": resource_types,
            "pageSize": page_size,
            "includePreservedRequests": include_preserved_requests,
        }

        try:
            params = inspect.signature(fn).parameters
            names = set(params.keys())
            if {"resource_types", "page_size", "include_preserved_requests"}.issubset(names):
                return fn(**kwargs_snake)
            if {"resourceTypes", "pageSize", "includePreservedRequests"}.issubset(names):
                return fn(**kwargs_camel)
        except (TypeError, ValueError):
            pass

        try:
            return fn(**kwargs_snake)
        except TypeError:
            pass

        try:
            return fn(**kwargs_camel)
        except TypeError:
            return fn(resource_types, page_size, include_preserved_requests)

    def get_network_request(self, reqid: int) -> Any:
        fn = self._get_request_fn
        try:
            return fn(reqid=reqid)
        except TypeError:
            return fn(reqid)
