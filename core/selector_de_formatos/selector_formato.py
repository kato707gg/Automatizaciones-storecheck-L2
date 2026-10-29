from __future__ import annotations

import json
import os
import getpass
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import openpyxl


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class FormatTarget:
    channel_id: str
    chain_id: str
    format_name: str

    def dedupe_key(self) -> tuple[str, str, str]:
        return (
            self.channel_id.casefold(),
            self.chain_id.casefold(),
            self.format_name.casefold(),
        )

    def label(self) -> str:
        return f"Canal={self.channel_id} | Cadena={self.chain_id} | Formato={self.format_name}"


@dataclass
class SelectionSummary:
    total: int
    success: list[str]
    ignored: list[str]
    failed: list[tuple[str, str]]
    output_path: str

    def to_dict(self) -> dict:
        return {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": self.total,
            "exitosos": self.success,
            "ignorados": self.ignored,
            "fallidos": {item: error for item, error in self.failed},
            "archivo_resultado": self.output_path,
        }


def parse_items_from_text(raw_text: str) -> list[FormatTarget]:
    items: list[FormatTarget] = []
    seen: set[tuple[str, str, str]] = set()

    for line in raw_text.splitlines():
        value = line.strip()
        if not value:
            continue

        parts = [chunk.strip() for chunk in re.split(r"[\t;,]", value) if chunk.strip()]
        if len(parts) < 3:
            continue

        target = FormatTarget(
            channel_id=_normalize_id(parts[0]),
            chain_id=_normalize_id(parts[1]),
            format_name=parts[2],
        )
        key = target.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        items.append(target)

    return items


def _normalize_id(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""

    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except Exception:
        pass
    return text


def load_items_from_excel(path: str) -> list[FormatTarget]:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook.active
        values: list[FormatTarget] = []
        seen: set[tuple[str, str, str]] = set()

        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            first_three = list(row[:3])
            while len(first_three) < 3:
                first_three.append(None)

            row_values = [str(cell).strip() if cell is not None else "" for cell in first_three]
            if not any(row_values):
                continue

            if row_index == 1:
                headers = {cell.casefold() for cell in row_values if cell}
                if headers.intersection(
                    {
                        "canal",
                        "channel",
                        "channel_id",
                        "cadena",
                        "chain",
                        "chain_id",
                        "formato",
                        "format",
                        "nombre",
                        "elemento",
                        "elementos",
                    }
                ):
                    continue

            target = FormatTarget(
                channel_id=_normalize_id(row_values[0]),
                chain_id=_normalize_id(row_values[1]),
                format_name=row_values[2],
            )
            if not target.format_name:
                continue

            key = target.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            values.append(target)

        return values
    finally:
        workbook.close()


def _resolve_chrome_profile_path() -> str:
    user = getpass.getuser()
    if os.name == "nt":
        return f"C:\\Users\\{user}\\AppData\\Local\\Google\\Chrome\\User Data"

    if os.path.exists(f"/Users/{user}"):
        return f"/Users/{user}/Library/Application Support/Google/Chrome"
    return f"/home/{user}/.config/google-chrome"


class WebSelectionSession:
    """Sesion reutilizable de Chrome para flujo de dos fases en la vista UI."""

    def __init__(self, use_profile: bool = True):
        self._use_profile = use_profile
        self._browser = None
        self._network_trace_enabled = False

    @property
    def browser(self):
        return self._browser

    def _browser_cookie_header(self) -> str:
        cookies = []
        for cookie in self._browser.get_cookies():
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookies.append(f"{name}={value}")
        return "; ".join(cookies)

    def _send_place_classification_action(self, format_id: str, action: str) -> tuple[int, str]:
        if action == "ADD_FORMAT_ON_PROJECT":
            endpoint = "/placeClassification/saveOnProjectPlace"
        elif action == "DELETE_FORMAT_ON_PROJECT":
            endpoint = "/placeClassification/deleteOnProjectPlace"
        else:
            raise ValueError(f"Accion no soportada: {action}")

        base_url = self._browser.current_url.split("/placeClassification/")[0]
        url = f"{base_url}{endpoint}"
        payload = urlencode({"formatId": str(format_id)}).encode("utf-8")

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": base_url,
            "Referer": self._browser.current_url,
            "Cookie": self._browser_cookie_header(),
        }

        try:
            user_agent = self._browser.execute_script("return navigator.userAgent")
            if user_agent:
                headers["User-Agent"] = user_agent
        except Exception:
            pass

        try:
            self._browser.set_script_timeout(20)
        except Exception:
            pass

        try:
            result = self._browser.execute_async_script(
                """
                const [targetUrl, formatId, actionName, timeoutMs, done] = arguments;
                if (!window.jQuery || !window.jQuery.ajax) {
                    done({error: 'jQuery.ajax no esta disponible en la pagina', actionName});
                    return;
                }

                const timer = setTimeout(() => {
                    done({error: 'timeout de AJAX en la pagina', actionName});
                }, timeoutMs);

                window.jQuery.ajax({
                    method: 'POST',
                    url: targetUrl,
                    data: { formatId },
                    timeout: timeoutMs,
                })
                .done((data, _textStatus, jqXHR) => {
                    clearTimeout(timer);
                    done({status: jqXHR.status, text: typeof data === 'string' ? data : JSON.stringify(data)});
                })
                .fail((jqXHR, textStatus, errorThrown) => {
                    clearTimeout(timer);
                    done({
                        status: jqXHR && typeof jqXHR.status === 'number' ? jqXHR.status : 0,
                        text: jqXHR && jqXHR.responseText ? jqXHR.responseText : '',
                        error: errorThrown || textStatus || 'AJAX fallo sin detalle',
                        actionName,
                    });
                });
                """,
                url,
                str(format_id),
                action,
                30000,
            )

            if isinstance(result, dict):
                if result.get("error") and not result.get("status"):
                    raise RuntimeError(f"La peticion AJAX fallo en {endpoint}: {result['error']}")

                status = int(result.get("status") or 0)
                text = str(result.get("text") or "")
                return status, text
        except Exception:
            pass

        request = Request(url=url, data=payload, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.getcode(), body
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, body
        except URLError as exc:
            raise RuntimeError(f"No se pudo enviar la peticion a {endpoint}: {exc}") from exc

    def start(
        self,
        url: str,
        status_cb: StatusCallback | None = None,
        trace_network: bool = False,
    ) -> None:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except Exception as exc:  # pragma: no cover - depende del entorno local
            raise RuntimeError(
                "No se pudo importar selenium. Instala el paquete con: pip install selenium"
            ) from exc

        if self._browser is not None:
            return

        if status_cb:
            status_cb("Abriendo Chrome...")

        self._network_trace_enabled = trace_network
        chrome_options = Options()
        chrome_options.add_argument("--window-size=1920,1080")
        if trace_network:
            chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        if self._use_profile:
            profile_path = _resolve_chrome_profile_path()
            chrome_options.add_argument(f"user-data-dir={profile_path}")
            chrome_options.add_argument("profile-directory=Default")

        self._browser = webdriver.Chrome(options=chrome_options)
        self._browser.get(url)
        if status_cb:
            status_cb("Chrome abierto. Inicia sesion y navega a la pantalla objetivo.")

    def close(self):
        if self._browser is not None:
            try:
                self._browser.quit()
            finally:
                self._browser = None

    def run_selection(
        self,
        items: list[FormatTarget],
        target_button: str,
        progress_cb: ProgressCallback | None = None,
        status_cb: StatusCallback | None = None,
        output_dir: str = "docs/runs",
        trace_network: bool = False,
        network_trace_path: str | None = None,
    ) -> SelectionSummary:
        if self._browser is None:
            raise RuntimeError("No hay sesion de Chrome activa. Primero abre la sesion.")

        if not items:
            raise ValueError("No hay elementos para procesar.")

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.common.exceptions import TimeoutException
        except Exception as exc:  # pragma: no cover - depende del entorno local
            raise RuntimeError(
                "No se pudieron importar utilidades de selenium."
            ) from exc

        expected_action = target_button.strip().lower()
        if expected_action not in {"agregar", "deseleccionar"}:
            raise ValueError("target_button debe ser 'Agregar' o 'Deseleccionar'.")

        success: list[str] = []
        ignored: list[str] = []
        failed: list[tuple[str, str]] = []

        item_wait = WebDriverWait(self._browser, 6)

        def _normalize_action(text: str) -> str:
            value = text.strip().casefold()
            if "deseleccionar" in value:
                return "deseleccionar"
            if "agregar" in value:
                return "agregar"
            return value

        def _normalize_text(value: str) -> str:
            return " ".join(value.split()).casefold()

        def _split_small_text(small_text: str) -> tuple[str, str]:
            parts = [part.strip() for part in small_text.replace("&gt;", ">" ).split(">")]
            if len(parts) >= 2:
                return _normalize_text(parts[0]), _normalize_text(parts[1])
            return "", ""

        def _find_matching_spans(item: FormatTarget):
            target_format = _normalize_text(item.format_name)
            target_channel = _normalize_text(_normalize_id(item.channel_id))
            target_chain = _normalize_text(_normalize_id(item.chain_id))

            candidates = []
            spans = self._browser.find_elements(By.XPATH, "//span[@id='formatDsc']")
            for span in spans:
                try:
                    if _normalize_text(span.text) != target_format:
                        continue

                    badge = span.find_element(
                        By.XPATH,
                        "./ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' badge ')][1]",
                    )
                    small = badge.find_element(By.XPATH, ".//small[1]")

                    attr_channel = _normalize_text(_normalize_id(small.get_attribute("channel-id") or ""))
                    attr_chain = _normalize_text(_normalize_id(small.get_attribute("chain-id") or ""))
                    text_channel, text_chain = _split_small_text(small.text or "")

                    channel_match = target_channel in {attr_channel, text_channel}
                    chain_match = target_chain in {attr_chain, text_chain}

                    if channel_match and chain_match:
                        candidates.append(span)
                except Exception:
                    continue

            return candidates

        def _find_matching_item(item: FormatTarget, expected_action: str):
            try:
                spans = item_wait.until(lambda _driver: _find_matching_spans(item))
            except TimeoutException as exc:
                raise RuntimeError(
                    "No se encontro tarjeta que coincida con Canal/Cadena/Formato."
                ) from exc

            if not spans:
                raise RuntimeError("No se encontro tarjeta que coincida con Canal/Cadena/Formato.")

            candidates = []
            for span in spans:
                try:
                    li = span.find_element(By.XPATH, "./ancestor::li[1]")
                    candidates.append((span, li))
                except Exception:
                    continue

            if not candidates:
                raise RuntimeError("No se encontro tarjeta que coincida con Canal/Cadena/Formato.")

            chosen = candidates[0]
            return chosen[0], chosen[1]

        for index, item in enumerate(items, start=1):
            item_label = item.label()
            if status_cb:
                status_cb(f"Procesando {index}/{len(items)}: {item_label}")
            if progress_cb:
                progress_cb(index, len(items), item_label)

            try:
                try:
                    _span, li = _find_matching_item(item, expected_action)
                except RuntimeError as exc:
                    if "No se encontro tarjeta" in str(exc):
                        failed.append((item_label, str(exc)))
                        continue
                    raise

                item_id = (li.get_attribute("data-element-id") or "").strip()

                action_name = "ADD_FORMAT_ON_PROJECT" if expected_action == "agregar" else "DELETE_FORMAT_ON_PROJECT"

                if not item_id:
                    failed.append((item_label, "No se pudo obtener el identificador del formato."))
                    continue

                status_code, response_text = self._send_place_classification_action(item_id, action_name)

                if 200 <= status_code < 300:
                    success.append(item_label)
                else:
                    failed.append((item_label, f"El backend respondio {status_code}: {response_text[:200]}"))
            except Exception as exc:
                failed.append((item_label, str(exc)))

        os.makedirs(output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"{stamp}_automatizacion5_seleccion.json")
        summary = SelectionSummary(
            total=len(items),
            success=success,
            ignored=ignored,
            failed=failed,
            output_path=os.path.abspath(output_path),
        )
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(summary.to_dict(), fp, ensure_ascii=False, indent=2)

        if trace_network and self._network_trace_enabled:
            trace_path = network_trace_path or os.path.splitext(output_path)[0] + "_network.json"
            try:
                performance_logs = self._browser.get_log("performance")
            except Exception:
                performance_logs = []

            os.makedirs(os.path.dirname(trace_path) or ".", exist_ok=True)
            with open(trace_path, "w", encoding="utf-8") as trace_fp:
                json.dump(performance_logs, trace_fp, ensure_ascii=False, indent=2)

        return summary


def run_web_selection(
    url: str,
    items: list[FormatTarget],
    use_profile: bool = True,
    target_button: str = "Agregar",
    output_dir: str = "docs/runs",
    progress_cb: ProgressCallback | None = None,
    status_cb: StatusCallback | None = None,
    trace_network: bool = False,
    network_trace_path: str | None = None,
) -> SelectionSummary:
    session = WebSelectionSession(use_profile=use_profile)
    try:
        session.start(url=url, status_cb=status_cb, trace_network=trace_network)
        return session.run_selection(
            items=items,
            target_button=target_button,
            progress_cb=progress_cb,
            status_cb=status_cb,
            output_dir=output_dir,
            trace_network=trace_network,
            network_trace_path=network_trace_path,
        )
    finally:
        session.close()
