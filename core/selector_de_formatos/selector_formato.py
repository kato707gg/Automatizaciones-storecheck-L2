from __future__ import annotations

import json
import os
import getpass
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import openpyxl


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, str], None]


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


def parse_items_from_text(raw_text: str) -> list[str]:
    separators = ["\n", ",", ";", "\t"]
    normalized = raw_text
    for separator in separators[1:]:
        normalized = normalized.replace(separator, "\n")

    items: list[str] = []
    seen: set[str] = set()
    for chunk in normalized.split("\n"):
        value = chunk.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(value)
    return items


def load_items_from_excel(path: str) -> list[str]:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook.active
        values: list[str] = []
        seen: set[str] = set()

        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            first_non_empty = next((cell for cell in row if cell is not None and str(cell).strip()), None)
            if first_non_empty is None:
                continue

            value = str(first_non_empty).strip()
            if row_index == 1 and value.casefold() in {
                "elemento",
                "elementos",
                "cadena",
                "formato",
                "nombre",
            }:
                continue

            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            values.append(value)

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

    @property
    def browser(self):
        return self._browser

    def start(self, url: str, status_cb: StatusCallback | None = None) -> None:
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

        chrome_options = Options()
        chrome_options.add_argument("--window-size=1920,1080")
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
        items: list[str],
        target_button: str,
        progress_cb: ProgressCallback | None = None,
        status_cb: StatusCallback | None = None,
        output_dir: str = "docs/runs",
    ) -> SelectionSummary:
        if self._browser is None:
            raise RuntimeError("No hay sesion de Chrome activa. Primero abre la sesion.")

        if not items:
            raise ValueError("No hay elementos para procesar.")

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
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

        wait = WebDriverWait(self._browser, 25)

        max_retries = 2
        post_confirm_wait_s = 2.5

        def _normalize_action(text: str) -> str:
            value = text.strip().casefold()
            if "deseleccionar" in value:
                return "deseleccionar"
            if "agregar" in value:
                return "agregar"
            return value

        def _safe_click(element):
            try:
                element.click()
            except Exception:
                self._browser.execute_script("arguments[0].click();", element)

        def _visible_modal_buttons():
            forms = self._browser.find_elements(By.ID, "confirmationFrm")
            for form in forms:
                if not form.is_displayed():
                    continue

                confirm = None
                cancel = None
                buttons = form.find_elements(By.TAG_NAME, "button")

                for button in buttons:
                    text = button.text.strip().casefold()
                    button_type = (button.get_attribute("type") or "").casefold()
                    classes = (button.get_attribute("class") or "").casefold()
                    button_id = (button.get_attribute("id") or "").casefold()

                    if cancel is None and (
                        "cancelar" in text
                        or button_id == "cancelconfirmationbtn"
                        or "dismiss" in (button.get_attribute("data-dismiss") or "").casefold()
                    ):
                        cancel = button

                    if confirm is None and (
                        "agregar" in text
                        or "deseleccionar" in text
                        or "aceptar" in text
                        or button_type == "submit"
                        or "btn-modal" in classes
                    ):
                        confirm = button

                if confirm is not None:
                    return form, confirm, cancel

            return None

        def _wait_modal_open():
            return wait.until(lambda _driver: _visible_modal_buttons())

        def _wait_modal_closed(timeout: float = 12.0):
            end_time = time.time() + timeout
            while time.time() < end_time:
                if _visible_modal_buttons() is None:
                    return
                time.sleep(0.1)
            raise TimeoutError("El modal no cerro despues de confirmar/cancelar.")

        def _close_modal_safely():
            modal_data = _visible_modal_buttons()
            if modal_data is None:
                return
            _form, _confirm, cancel = modal_data
            if cancel is not None:
                _safe_click(cancel)
                _wait_modal_closed()

        def _open_modal_for_item(item_name: str):
            span = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//span[@id='formatDsc' and normalize-space(text())='{item_name}']")
                )
            )
            heading = span.find_element(By.XPATH, "./ancestor::h6[1]")
            self._browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", heading)
            time.sleep(0.2)

            # Algunos formatos solo abren confirmacion con doble clic.
            open_attempts = [
                lambda: ActionChains(self._browser).double_click(heading).perform(),
                lambda: (heading.click(), heading.click()),
                lambda: (span.click(), span.click()),
            ]

            last_error: Exception | None = None
            for trigger in open_attempts:
                try:
                    trigger()
                    return _wait_modal_open()
                except Exception as exc:
                    last_error = exc

            if last_error is not None:
                raise last_error
            raise RuntimeError("No se pudo abrir el modal del formato.")

        for index, item in enumerate(items, start=1):
            if status_cb:
                status_cb(f"Procesando {index}/{len(items)}: {item}")
            if progress_cb:
                progress_cb(index, len(items), item)

            try:
                expected_after = "deseleccionar" if expected_action == "agregar" else "agregar"
                applied = False

                for attempt in range(max_retries + 1):
                    _form, confirm, _cancel = _open_modal_for_item(item)
                    current_action = _normalize_action(confirm.text)

                    if current_action != expected_action:
                        ignored.append(item)
                        _close_modal_safely()
                        applied = True
                        break

                    _safe_click(confirm)
                    try:
                        _wait_modal_closed()
                    except Exception:
                        # Si no cierra visualmente, seguimos con una espera breve para dar tiempo al backend.
                        pass
                    time.sleep(post_confirm_wait_s)

                    # Verifica si realmente cambió el estado del formato.
                    _verify_form, verify_confirm, _verify_cancel = _open_modal_for_item(item)
                    verify_action = _normalize_action(verify_confirm.text)
                    _close_modal_safely()

                    if verify_action == expected_after:
                        success.append(item)
                        applied = True
                        break

                    if attempt < max_retries and status_cb:
                        status_cb(
                            f"Reintentando {item} ({attempt + 1}/{max_retries}) porque el cambio no se reflejo todavia..."
                        )

                if not applied:
                    failed.append((item, "No se reflejo el cambio despues de reintentos."))
            except Exception as exc:
                try:
                    _close_modal_safely()
                except Exception:
                    pass
                failed.append((item, str(exc)))

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
        return summary


def run_web_selection(
    url: str,
    items: list[str],
    use_profile: bool = True,
    target_button: str = "Agregar",
    output_dir: str = "docs/runs",
    progress_cb: ProgressCallback | None = None,
    status_cb: StatusCallback | None = None,
) -> SelectionSummary:
    session = WebSelectionSession(use_profile=use_profile)
    try:
        session.start(url=url, status_cb=status_cb)
        return session.run_selection(
            items=items,
            target_button=target_button,
            progress_cb=progress_cb,
            status_cb=status_cb,
            output_dir=output_dir,
        )
    finally:
        session.close()
