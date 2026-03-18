from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_local_config() -> dict[str, Any]:
    config_path = _project_root() / "config" / "mcp_client.local.json"
    if not config_path.exists():
        return {}
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


class LocalMcpClientTemplate:
    """Cliente MCP usando SDK oficial de Python (robusto para stdio)."""

    def __init__(self) -> None:
        cfg = _load_local_config()

        default_cmd = [
            r"C:/Program Files/nodejs/npx.cmd",
            "-y",
            "chrome-devtools-mcp",
            "--browserUrl",
            "http://127.0.0.1:9222",
            "--no-usage-statistics",
        ]
        server_cmd = cfg.get("server_command")
        if isinstance(server_cmd, list) and all(isinstance(x, str) for x in server_cmd):
            self._server_command = server_cmd
        else:
            self._server_command = default_cmd

        self._tool_eval = str(cfg.get("tool_evaluate", "evaluate_script"))
        self._tool_list = str(cfg.get("tool_list_requests", "list_network_requests"))
        self._tool_get = str(cfg.get("tool_get_request", "get_network_request"))
        self._request_timeout_seconds = float(cfg.get("request_timeout_seconds", 20))

    def evaluate_script(self, function: str) -> Any:
        return self._call_tool(self._tool_eval, {"function": function})

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
    ) -> Any:
        try:
            return self._call_tool(
                self._tool_list,
                {
                    "resourceTypes": resource_types,
                    "pageSize": page_size,
                    "includePreservedRequests": include_preserved_requests,
                },
            )
        except Exception:
            return self._call_tool(
                self._tool_list,
                {
                    "resource_types": resource_types,
                    "page_size": page_size,
                    "include_preserved_requests": include_preserved_requests,
                },
            )

    def get_network_request(self, reqid: int) -> Any:
        try:
            return self._call_tool(self._tool_get, {"reqid": reqid})
        except Exception:
            return self._call_tool(self._tool_get, {"requestId": reqid})

    def close(self) -> None:
        return

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        payload = {k: v for k, v in arguments.items() if v is not None}

        async def _run() -> Any:
            command = self._server_command[0]
            args = self._server_command[1:]
            server = StdioServerParameters(command=command, args=args)

            async with stdio_client(server) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, payload)
                    if result.isError:
                        raise RuntimeError(f"Tool MCP devolvió error: {result.model_dump()}")
                    return self._parse_call_result(result.model_dump())

        try:
            return asyncio.run(asyncio.wait_for(_run(), timeout=self._request_timeout_seconds))
        except Exception as exc:
            raise RuntimeError(f"Fallo MCP en '{tool_name}': {exc}") from exc

    @staticmethod
    def _parse_call_result(result_dump: dict[str, Any]) -> Any:
        structured = result_dump.get("structuredContent")
        if structured is not None:
            return structured

        content = result_dump.get("content")
        if not isinstance(content, list):
            return result_dump

        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])

        if not texts:
            return ""

        merged = "\n".join(texts).strip()
        if not merged:
            return ""

        fenced = re.search(r"```json\s*([\s\S]*?)\s*```", merged)
        if fenced:
            candidate = fenced.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                return candidate

        if merged.startswith("{") or merged.startswith("["):
            try:
                return json.loads(merged)
            except Exception:
                return merged

        return merged


def create_mcp_client() -> LocalMcpClientTemplate:
    return LocalMcpClientTemplate()
