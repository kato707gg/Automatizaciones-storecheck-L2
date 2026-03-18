from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any, Callable

_CLIENT: Any | None = None


def set_mcp_client(client: Any) -> None:
    """Permite inyectar un cliente MCP en runtime desde código."""
    global _CLIENT
    _CLIENT = client


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_factory_from_ref(ref: str) -> Callable[[], Any]:
    ref = (ref or "").strip()
    if not ref or ":" not in ref:
        raise RuntimeError(
            "Referencia de factory inválida. Usa formato 'paquete.modulo:funcion'."
        )

    module_name, fn_name = ref.split(":", 1)
    module_name = module_name.strip()
    fn_name = fn_name.strip()
    module = importlib.import_module(module_name)
    fn = getattr(module, fn_name)
    if not callable(fn):
        raise RuntimeError(f"Factory no invocable: {ref}")
    return fn


def _load_client_from_config_or_env() -> Any | None:
    """
    Carga cliente MCP con prioridad:
    1) STORECHECK_MCP_CLIENT_FACTORY="paquete.modulo:funcion"
    2) config/mcp_client.local.json {"client_factory": "paquete.modulo:funcion"}
    """
    factory_ref = os.getenv("STORECHECK_MCP_CLIENT_FACTORY", "").strip()

    if not factory_ref:
        config_path = _project_root() / "config" / "mcp_client.local.json"
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    factory_ref = str(raw.get("client_factory", "")).strip()
            except Exception:
                return None

    if not factory_ref:
        factory_ref = "core.semana2.mcp_client_template:create_mcp_client"

    try:
        factory = _load_factory_from_ref(factory_ref)
        return factory()
    except Exception:
        return None


def _get_client() -> Any:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    _CLIENT = _load_client_from_config_or_env()
    if _CLIENT is None:
        raise RuntimeError(
            "No hay cliente MCP configurado. "
            "Configura config/mcp_client.local.json con client_factory, "
            "o llama set_mcp_client(...) al iniciar la app."
        )

    required = ("evaluate_script", "list_network_requests", "get_network_request")
    if not all(hasattr(_CLIENT, method) for method in required):
        raise RuntimeError(
            "El cliente MCP configurado no implementa evaluate_script, "
            "list_network_requests y get_network_request."
        )

    return _CLIENT


def evaluate_script(function: str) -> Any:
    client = _get_client()
    return client.evaluate_script(function)


def list_network_requests(
    resource_types: list[str] | None = None,
    page_size: int = 200,
    include_preserved_requests: bool = True,
) -> Any:
    client = _get_client()
    try:
        return client.list_network_requests(
            resource_types=resource_types,
            page_size=page_size,
            include_preserved_requests=include_preserved_requests,
        )
    except TypeError:
        try:
            return client.list_network_requests(
                resourceTypes=resource_types,
                pageSize=page_size,
                includePreservedRequests=include_preserved_requests,
            )
        except TypeError:
            return client.list_network_requests(
                resource_types,
                page_size,
                include_preserved_requests,
            )


def get_network_request(reqid: int) -> Any:
    client = _get_client()
    try:
        return client.get_network_request(reqid=reqid)
    except TypeError:
        return client.get_network_request(reqid)
