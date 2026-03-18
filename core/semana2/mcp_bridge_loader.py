from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

from .mcp_backend import McpChromeBridge


def _load_bridge_from_ref(bridge_ref: str) -> McpChromeBridge | None:
    bridge_ref = (bridge_ref or "").strip()
    if not bridge_ref or ":" not in bridge_ref:
        return None

    module_name, class_name = bridge_ref.split(":", 1)
    module_name = module_name.strip()
    class_name = class_name.strip()
    if not module_name or not class_name:
        return None

    try:
        module = importlib.import_module(module_name)
        bridge_cls: type[Any] = getattr(module, class_name)
        bridge = bridge_cls()
    except Exception:
        return None

    required = ("evaluate_script", "list_network_requests", "get_network_request")
    if not all(hasattr(bridge, method) for method in required):
        return None

    return bridge


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_bridge_from_config_file() -> McpChromeBridge | None:
    """
    Carga bridge desde config local del proyecto (sin usar terminal).

    Archivo esperado:
    - config/mcp_bridge.local.json

    Formato:
    {
      "bridge": "core.semana2.mcp_bridge_runtime:EnvCallableMcpChromeBridge",
      "evaluate_fn": "paquete.modulo:funcion",
      "list_requests_fn": "paquete.modulo:funcion",
      "get_request_fn": "paquete.modulo:funcion"
    }
    """
    config_path = _project_root() / "config" / "mcp_bridge.local.json"
    if not config_path.exists():
        return None

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    bridge_ref = str(raw.get("bridge", "")).strip()
    if not bridge_ref:
        bridge_ref = "core.semana2.mcp_bridge_runtime:EnvCallableMcpChromeBridge"

    evaluate_fn = str(raw.get("evaluate_fn", "")).strip()
    list_requests_fn = str(raw.get("list_requests_fn", "")).strip()
    get_request_fn = str(raw.get("get_request_fn", "")).strip()

    if evaluate_fn and list_requests_fn and get_request_fn:
        os.environ.setdefault("STORECHECK_MCP_EVALUATE_FN", evaluate_fn)
        os.environ.setdefault("STORECHECK_MCP_LIST_REQUESTS_FN", list_requests_fn)
        os.environ.setdefault("STORECHECK_MCP_GET_REQUEST_FN", get_request_fn)

    return _load_bridge_from_ref(bridge_ref)


def load_mcp_bridge_from_env() -> McpChromeBridge | None:
    """
    Carga automática de bridge MCP desde variable de entorno.

    Formato esperado:
    - STORECHECK_MCP_BRIDGE="paquete.modulo:Clase"

    La clase debe implementar la interfaz McpChromeBridge.
    Si no está configurado o falla la carga, retorna None.
    """
    bridge_ref = os.getenv("STORECHECK_MCP_BRIDGE", "").strip()
    if bridge_ref:
        bridge = _load_bridge_from_ref(bridge_ref)
        if bridge is not None:
            return bridge

    return _load_bridge_from_config_file()
