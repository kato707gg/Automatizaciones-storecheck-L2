from __future__ import annotations

import atexit
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

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
            "--no-usage-statistics",
        ]
        server_cmd = cfg.get("server_command")
        if isinstance(server_cmd, list) and all(isinstance(x, str) for x in server_cmd):
            self._server_command_template = server_cmd
        else:
            self._server_command_template = default_cmd

        self._configured_browser_url = str(cfg.get("browser_url", "auto")).strip() or "auto"
        self._startup_url = str(cfg.get("startup_url", "https://webapp.storecheck.com/")).strip() or "https://webapp.storecheck.com/"
        self._debug_ports = self._normalize_ports(cfg.get("debug_ports"), default=[9222, 9223, 9333, 9444])
        self._auto_launch_browser = bool(cfg.get("auto_launch_browser", True))
        self._use_temp_profile_on_launch = bool(cfg.get("use_temp_profile_on_launch", True))
        self._use_persistent_profile_on_launch = bool(cfg.get("use_persistent_profile_on_launch", False))
        self._keep_browser_open_on_close = bool(cfg.get("keep_browser_open_on_close", False))
        self._persistent_profile_dir_cfg = str(cfg.get("persistent_profile_dir", "")).strip()

        launch_cmd = cfg.get("browser_launch_command")
        if isinstance(launch_cmd, list) and all(isinstance(x, str) for x in launch_cmd):
            self._browser_launch_command = launch_cmd
        else:
            self._browser_launch_command = []

        self._launched_browser_process: subprocess.Popen[Any] | None = None
        self._launched_browser_profile_dir: Path | None = None

        self._tool_eval = str(cfg.get("tool_evaluate", "evaluate_script"))
        self._tool_list = str(cfg.get("tool_list_requests", "list_network_requests"))
        self._tool_get = str(cfg.get("tool_get_request", "get_network_request"))
        self._request_timeout_seconds = float(cfg.get("request_timeout_seconds", 20))
        self._init_timeout_seconds = float(cfg.get("init_timeout_seconds", 60))

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._stdio_cm = None
        self._session_cm = None
        self._closed = False

        self._start_runtime()
        atexit.register(self.close)

    def evaluate_script(self, function: str) -> Any:
        self._ensure_page_selected()
        return self._call_tool(self._tool_eval, {"function": function})

    def list_network_requests(
        self,
        resource_types: list[str] | None = None,
        page_size: int = 200,
        include_preserved_requests: bool = True,
    ) -> Any:
        self._ensure_page_selected()
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
        self._ensure_page_selected()
        try:
            return self._call_tool(self._tool_get, {"reqid": reqid})
        except Exception:
            return self._call_tool(self._tool_get, {"requestId": reqid})

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        try:
            self._submit(self._shutdown_runtime(), timeout=max(2.0, self._request_timeout_seconds))
        except Exception:
            pass

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread is not None:
            self._thread.join(timeout=2)

        if not self._keep_browser_open_on_close:
            self._stop_launched_browser()

    def _start_runtime(self) -> None:
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            return

        ready = threading.Event()

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_runner, name="storecheck-mcp-client", daemon=True)
        self._thread.start()
        ready.wait(timeout=2)

        self._submit(self._initialize_runtime(), timeout=max(10.0, self._init_timeout_seconds))

    def _submit(self, coro: Any, timeout: float | None = None) -> Any:
        if self._loop is None:
            raise RuntimeError("Loop MCP no inicializado")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _initialize_runtime(self) -> None:
        server_command = self._build_server_command()
        command = server_command[0]
        args = server_command[1:]
        server = StdioServerParameters(command=command, args=args)

        self._stdio_cm = stdio_client(server)
        read_stream, write_stream = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def _shutdown_runtime(self) -> None:
        try:
            if self._session_cm is not None:
                await self._session_cm.__aexit__(None, None, None)
        finally:
            self._session_cm = None
            self._session = None

        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(None, None, None)
            self._stdio_cm = None

    async def _call_tool_async(self, tool_name: str, payload: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("Sesión MCP no inicializada")

        result = await self._session.call_tool(tool_name, payload)
        if result.isError:
            raise RuntimeError(f"Tool MCP devolvió error: {result.model_dump()}")
        return self._parse_call_result(result.model_dump())

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        payload = {k: v for k, v in arguments.items() if v is not None}

        try:
            return self._submit(
                self._call_tool_async(tool_name, payload),
                timeout=self._request_timeout_seconds,
            )
        except Exception as exc:
            if self._is_no_page_selected_error(exc):
                try:
                    self._ensure_page_selected()
                    return self._submit(
                        self._call_tool_async(tool_name, payload),
                        timeout=self._request_timeout_seconds,
                    )
                except Exception as retry_exc:
                    raise RuntimeError(f"Fallo MCP en '{tool_name}' tras auto-selección de página: {retry_exc}") from retry_exc
            raise RuntimeError(f"Fallo MCP en '{tool_name}': {exc}") from exc

    @staticmethod
    def _is_no_page_selected_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "no page selected" in text

    def _ensure_page_selected(self) -> None:
        try:
            self._submit(self._ensure_page_selected_async(), timeout=self._request_timeout_seconds)
        except Exception:
            return

    async def _ensure_page_selected_async(self) -> None:
        pages_payload = await self._call_tool_async("list_pages", {})
        page_id = self._extract_preferred_page_id(pages_payload)

        if page_id is None:
            raise RuntimeError(
                "No hay página Storecheck seleccionable en el browser de depuración. "
                "Abre manualmente la tarea de prueba en ese Chrome y reintenta."
            )

        await self._call_tool_async("select_page", {"pageId": int(page_id), "bringToFront": True})

    @staticmethod
    def _extract_page_id(payload: Any) -> int | None:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    candidate = item.get("pageId", item.get("id"))
                    if isinstance(candidate, int):
                        return candidate
                    if isinstance(candidate, str) and candidate.isdigit():
                        return int(candidate)

        if isinstance(payload, dict):
            for key in ("pages", "items", "data"):
                nested = payload.get(key)
                found = LocalMcpClientTemplate._extract_page_id(nested)
                if found is not None:
                    return found

            candidate = payload.get("pageId", payload.get("id"))
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)

        return None

    @staticmethod
    def _extract_preferred_page_id(payload: Any) -> int | None:
        candidates = LocalMcpClientTemplate._collect_page_candidates(payload)
        if not candidates:
            return None

        def _score(url: str) -> int:
            lower = url.lower()
            score = 0
            if "webapp.storecheck.com" in lower:
                score += 100
            if "/modulecapture/" in lower:
                score += 20
            if lower.startswith("http://") or lower.startswith("https://"):
                score += 5
            if "about:blank" in lower:
                score -= 100
            if "chrome://" in lower or "devtools://" in lower:
                score -= 50
            return score

        scored = sorted(((pid, url, _score(url)) for pid, url in candidates), key=lambda item: item[2], reverse=True)
        best_pid, _best_url, best_score = scored[0]
        if best_score <= 0:
            return None
        return best_pid

    @staticmethod
    def _collect_page_candidates(payload: Any) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []

        if isinstance(payload, list):
            for item in payload:
                out.extend(LocalMcpClientTemplate._collect_page_candidates(item))
            return out

        if isinstance(payload, dict):
            page_id = payload.get("pageId", payload.get("id"))
            url = payload.get("url")
            normalized_id: int | None = None
            if isinstance(page_id, int):
                normalized_id = page_id
            elif isinstance(page_id, str) and page_id.isdigit():
                normalized_id = int(page_id)

            if normalized_id is not None:
                out.append((normalized_id, str(url or "")))

            for key in ("pages", "items", "data"):
                out.extend(LocalMcpClientTemplate._collect_page_candidates(payload.get(key)))
            return out

        if isinstance(payload, str):
            for line in payload.splitlines():
                lower = line.lower()
                if "page" in lower and "http" in lower:
                    page_match = re.search(r"(pageid|id)\s*[:=]\s*(\d+)", line, re.IGNORECASE)
                    url_match = re.search(r"https?://\S+", line)
                    if page_match:
                        pid = int(page_match.group(2))
                        url = url_match.group(0) if url_match else ""
                        out.append((pid, url))

        return out

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
            return result_dump

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

    @staticmethod
    def _normalize_ports(raw: Any, default: list[int]) -> list[int]:
        if isinstance(raw, list):
            out: list[int] = []
            for item in raw:
                try:
                    value = int(item)
                    if 1 <= value <= 65535:
                        out.append(value)
                except Exception:
                    continue
            if out:
                return out
        return list(default)

    def _build_server_command(self) -> list[str]:
        cmd = list(self._server_command_template)
        browser_url = self._resolve_browser_url()

        if not browser_url:
            return cmd

        idx, inline_value = self._find_browser_url_arg(cmd)
        if idx is None:
            cmd.extend(["--browserUrl", browser_url])
            return cmd

        if inline_value is not None:
            cmd[idx] = f"--browserUrl={browser_url}"
        elif idx + 1 < len(cmd):
            cmd[idx + 1] = browser_url
        else:
            cmd.append(browser_url)

        return cmd

    @staticmethod
    def _find_browser_url_arg(cmd: list[str]) -> tuple[int | None, str | None]:
        for idx, token in enumerate(cmd):
            if token == "--browserUrl":
                return idx, None
            if token.startswith("--browserUrl="):
                return idx, token.split("=", 1)[1]
        return None, None

    def _resolve_browser_url(self) -> str | None:
        env_browser_url = os.getenv("STORECHECK_BROWSER_URL", "").strip()
        if env_browser_url:
            return env_browser_url

        idx, inline_value = self._find_browser_url_arg(self._server_command_template)
        template_browser_url = ""
        if idx is not None:
            if inline_value is not None:
                template_browser_url = inline_value.strip()
            elif idx + 1 < len(self._server_command_template):
                template_browser_url = self._server_command_template[idx + 1].strip()

        configured = self._configured_browser_url.strip()
        candidate = configured if configured and configured.lower() != "auto" else template_browser_url
        if candidate and candidate.lower() != "auto":
            return candidate

        found = self._discover_running_browser_url()
        if found is not None:
            return found

        if self._auto_launch_browser:
            return self._launch_browser_for_debugging()

        return None

    def _discover_running_browser_url(self) -> str | None:
        for port in self._debug_ports:
            base_url = f"http://127.0.0.1:{port}"
            if self._is_debug_endpoint_alive(base_url):
                return base_url
        return None

    @staticmethod
    def _is_debug_endpoint_alive(base_url: str) -> bool:
        url = f"{base_url.rstrip('/')}/json/version"
        try:
            with urlopen(url, timeout=1.2) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
                web_socket_url = payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
                return bool(web_socket_url)
        except (URLError, OSError, ValueError, TimeoutError):
            return False

    def _launch_browser_for_debugging(self) -> str | None:
        if self._launched_browser_process is not None:
            for port in self._debug_ports:
                base_url = f"http://127.0.0.1:{port}"
                if self._is_debug_endpoint_alive(base_url):
                    return base_url

        port = self._pick_available_port(preferred=self._debug_ports)
        if port is None:
            return None

        profile_dir: Path | None = self._resolve_launch_profile_dir()

        launch_cmd = self._build_browser_launch_command(port=port, profile_dir=profile_dir)
        if not launch_cmd:
            if profile_dir is not None:
                shutil.rmtree(profile_dir, ignore_errors=True)
            return None

        try:
            process = subprocess.Popen(
                launch_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            if profile_dir is not None and self._use_temp_profile_on_launch:
                shutil.rmtree(profile_dir, ignore_errors=True)
            return None

        base_url = f"http://127.0.0.1:{port}"
        for _ in range(30):
            if self._is_debug_endpoint_alive(base_url):
                self._launched_browser_process = process
                self._launched_browser_profile_dir = profile_dir
                return base_url
            time.sleep(0.2)

        try:
            process.terminate()
        except Exception:
            pass
        if profile_dir is not None and self._use_temp_profile_on_launch:
            shutil.rmtree(profile_dir, ignore_errors=True)
        return None

    def _resolve_launch_profile_dir(self) -> Path | None:
        if self._use_temp_profile_on_launch:
            return Path(tempfile.mkdtemp(prefix="storecheck-mcp-browser-"))

        if not self._use_persistent_profile_on_launch:
            return None

        if self._persistent_profile_dir_cfg:
            profile_dir = Path(self._persistent_profile_dir_cfg)
        else:
            profile_dir = _project_root() / ".mcp_browser_profile"

        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def _build_browser_launch_command(self, port: int, profile_dir: Path | None) -> list[str] | None:
        if self._browser_launch_command:
            rendered: list[str] = []
            for token in self._browser_launch_command:
                rendered.append(
                    token.replace("{port}", str(port)).replace("{profile_dir}", str(profile_dir or ""))
                )
            return rendered

        executable = self._find_browser_executable()
        if executable is None:
            return None

        cmd = [
            executable,
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            self._startup_url,
        ]
        if profile_dir is not None:
            cmd.insert(2, f"--user-data-dir={profile_dir}")
        return cmd

    @staticmethod
    def _find_browser_executable() -> str | None:
        candidates = [
            shutil.which("chrome"),
            shutil.which("msedge"),
            r"C:/Program Files/Google/Chrome/Application/chrome.exe",
            r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return str(path)
        return None

    @staticmethod
    def _pick_available_port(preferred: list[int]) -> int | None:
        for port in preferred:
            if LocalMcpClientTemplate._is_port_free(port):
                return port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            selected = sock.getsockname()[1]
        return int(selected)

    @staticmethod
    def _is_port_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) != 0

    def _stop_launched_browser(self) -> None:
        if self._launched_browser_process is not None:
            try:
                self._launched_browser_process.terminate()
                self._launched_browser_process.wait(timeout=2)
            except Exception:
                try:
                    self._launched_browser_process.kill()
                except Exception:
                    pass
            finally:
                self._launched_browser_process = None

        if self._launched_browser_profile_dir is not None:
            if self._use_temp_profile_on_launch:
                shutil.rmtree(self._launched_browser_profile_dir, ignore_errors=True)
            self._launched_browser_profile_dir = None


def create_mcp_client() -> LocalMcpClientTemplate:
    return LocalMcpClientTemplate()
