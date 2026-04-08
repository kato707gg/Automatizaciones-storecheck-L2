"""
Vista – Creador de tareas automático
Interfaz funcional para capturar prompt, generar base y guardar artefactos.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.creador_de_tareas.autofix_stub import NoOpAutoCorrector
from core.creador_de_tareas.evidence import EvidenceStore
from core.creador_de_tareas.executor_h3 import PlaybookExecutor
from core.creador_de_tareas.executor_h3 import ScopeTypePatternRunner
from core.creador_de_tareas.mcp_backend import McpChromeBridge, McpScopeTypeBackend
from core.creador_de_tareas.orchestrator import Semana2Orchestrator
from core.creador_de_tareas.parser_mvp import RuleBasedTaskParser
from core.creador_de_tareas.validator import TaskIRValidator


STORECHECK_HOME_URL = "https://webapp.storecheck.com/"
STORECHECK_TARGET_CREATE_URL = "https://webapp.storecheck.com/moduleCapture/create"


class _McpConnectionWorker(QObject):
    success = Signal(str)
    error = Signal(str)

    def __init__(self, bridge: McpChromeBridge):
        super().__init__()
        self._bridge = bridge

    def run(self):
        try:
            check = self._bridge.evaluate_script("() => document.title")
            preview = json.dumps(check, ensure_ascii=False)
            preview = preview[:220] + ("..." if len(preview) > 220 else "")
            self.success.emit(preview)
        except Exception as exc:
            self.error.emit(str(exc))


class _RealMcpRunWorker(QObject):
    success = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        bridge: McpChromeBridge,
        prompt: str,
        module_id: int,
        original_scope: int,
        target_scope: int,
        output_dir: str,
    ):
        super().__init__()
        self._bridge = bridge
        self._prompt = prompt
        self._module_id = module_id
        self._original_scope = original_scope
        self._target_scope = target_scope
        self._output_dir = output_dir

    def run(self):
        try:
            backend = McpScopeTypeBackend(bridge=self._bridge)
            runner = ScopeTypePatternRunner(
                module_id=self._module_id,
                original_scope_type=self._original_scope,
                target_scope_type=self._target_scope,
                backend=backend,
                restore_on_verify=True,
            )
            orchestrator = Semana2Orchestrator(
                parser=RuleBasedTaskParser(),
                validator=TaskIRValidator(),
                executor=PlaybookExecutor(runner=runner),
                auto_corrector=NoOpAutoCorrector(),
                max_retries=1,
            )
            result = orchestrator.run(prompt=self._prompt)
            payload = result.to_dict()

            artifacts: dict[str, str] = {}
            execution_data = payload.get("execution_result")
            if isinstance(execution_data, dict):
                execution_result = VistaCreadorTareas._build_execution_result(execution_data)
                store = EvidenceStore(self._output_dir)
                jsonl_path, summary_path = store.write_execution(
                    case_id="ui_real_mcp",
                    execution_result=execution_result,
                )
                artifacts["jsonl"] = os.path.abspath(jsonl_path)
                artifacts["summary"] = os.path.abspath(summary_path)

            slug = datetime.now().strftime("%Y%m%d_%H%M%S")
            payload_path = os.path.join(self._output_dir, f"{slug}_ui_real_mcp.payload.json")
            with open(payload_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)

            artifacts["payload"] = os.path.abspath(payload_path)
            self.success.emit({"payload": payload, "artifacts": artifacts})
        except Exception as exc:
            self.error.emit(str(exc))


class VistaCreadorTareas(QWidget):
    def __init__(self, back_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._last_payload: dict | None = None
        self._last_artifacts: dict | None = None
        self._mcp_bridge: McpChromeBridge | None = None
        self._mcp_test_thread: QThread | None = None
        self._mcp_test_worker: _McpConnectionWorker | None = None
        self._mcp_real_thread: QThread | None = None
        self._mcp_real_worker: _RealMcpRunWorker | None = None
        self._awaiting_continue = False
        self._start_triggered_real_run = False
        self._runtime_module_id: int | None = None
        self._runtime_scope_original: int | None = None
        self._runtime_scope_target: int | None = None
        self.setStyleSheet("VistaCreadorTareas { background-color: #FFFFFF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.setSpacing(0)

        # ── Botón volver ─────────────────────────────────────────────
        self._btn_back = QPushButton("← Volver")
        self._btn_back.setFixedSize(120, 36)
        self._btn_back.setFont(QFont("Segoe UI", 10))
        self._btn_back.setCursor(Qt.PointingHandCursor)
        self._btn_back.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #0098C4;
                border: 1.5px solid #0098C4;
                border-radius: 18px;
            }
            QPushButton:hover { background-color: #E8F7FC; }
        """)
        if back_cb:
            self._btn_back.clicked.connect(back_cb)
        outer.addWidget(self._btn_back, 0, Qt.AlignLeft)
        outer.addSpacing(30)

        self._title = QLabel("Creador de tareas automático")
        self._title.setFont(QFont("Segoe UI", 32, QFont.Bold))
        self._title.setStyleSheet("color: #0098C4;")
        outer.addWidget(self._title)
        outer.addSpacing(14)

        self._desc = QLabel(
            "Esta automatización te permite crear tareas a partir de texto. "
            "Describe la tarea y el sistema genera una configuración base validada "
            "para Storecheck, reduciendo trabajo manual y repeticiones."
        )
        self._desc.setWordWrap(True)
        self._desc.setFont(QFont("Segoe UI", 11))
        self._desc.setStyleSheet("color: #333;")
        outer.addWidget(self._desc)
        outer.addSpacing(22)

        self._section_title = QLabel("Pasos para usar la herramienta")
        self._section_title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        self._section_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(self._section_title)
        outer.addSpacing(8)

        self._steps = QLabel(
            "1. Escribe lo que hará la tarea\n"
            "2. Presiona \"Comenzar proceso\" para abrir Storecheck\n"
            "3. Inicia sesión y navega a la tarea en creación\n"
            "4. Presiona \"Continuar proceso\" para generar bloques y condiciones"
        )
        self._steps.setWordWrap(True)
        self._steps.setFont(QFont("Segoe UI", 11))
        self._steps.setStyleSheet("color: #222;")
        outer.addWidget(self._steps)
        outer.addSpacing(20)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Describe la tarea…")
        self._input.setFixedHeight(210)
        self._input.setFont(QFont("Segoe UI", 13))
        self._input.setStyleSheet("""
            QTextEdit {
                background: #F7F7F7;
                border: 1.5px solid #D9D9D9;
                border-radius: 14px;
                color: #222;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 2px solid #0098C4;
                background: #FFFFFF;
            }
        """)
        outer.addWidget(self._input)
        outer.addSpacing(22)

        self._btn_start = QPushButton("Comenzar proceso")
        self._btn_start.setFixedSize(300, 58)
        self._btn_start.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.setStyleSheet("""
            QPushButton {
                background-color: #0098C4;
                color: #FFFFFF;
                border: none;
                border-radius: 29px;
            }
            QPushButton:hover   { background-color: #007BA3; }
            QPushButton:pressed { background-color: #006080; }
        """)
        self._btn_start.clicked.connect(self._start)
        outer.addWidget(self._btn_start, 0, Qt.AlignHCenter)
        outer.addSpacing(12)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self._btn_save = QPushButton("Guardar resultado")
        self._btn_save.setFixedSize(180, 42)
        self._btn_save.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #0098C4;
                border: 1.8px solid #0098C4;
                border-radius: 21px;
            }
            QPushButton:hover { background-color: #E8F7FC; }
            QPushButton:disabled {
                color: #9AA3A8;
                border: 1.2px solid #C9D1D6;
                background-color: #F3F5F6;
            }
        """)
        self._btn_save.clicked.connect(self._save_result)

        self._btn_copy = QPushButton("Copiar JSON")
        self._btn_copy.setFixedSize(140, 42)
        self._btn_copy.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_copy.setCursor(Qt.PointingHandCursor)
        self._btn_copy.setEnabled(False)
        self._btn_copy.setStyleSheet(self._btn_save.styleSheet())
        self._btn_copy.clicked.connect(self._copy_json)

        self._btn_diag = QPushButton("Capturar diagnóstico UI")
        self._btn_diag.setFixedSize(220, 42)
        self._btn_diag.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_diag.setCursor(Qt.PointingHandCursor)
        self._btn_diag.setEnabled(False)
        self._btn_diag.setStyleSheet(self._btn_save.styleSheet())
        self._btn_diag.clicked.connect(self._capture_publish_diagnostic)

        actions.addWidget(self._btn_save)
        actions.addWidget(self._btn_copy)
        actions.addWidget(self._btn_diag)
        actions.addStretch()
        outer.addLayout(actions)
        outer.addSpacing(12)

        self._summary = QLabel("Esperando descripción…")
        self._summary.setWordWrap(True)
        self._summary.setFont(QFont("Segoe UI", 10))
        self._summary.setStyleSheet("color: #2F3A40;")
        outer.addWidget(self._summary)
        outer.addSpacing(8)

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(220)
        self._preview.setFont(QFont("Consolas", 10))
        self._preview.setStyleSheet("""
            QPlainTextEdit {
                background: #FBFCFD;
                border: 1.2px solid #D7DEE3;
                border-radius: 10px;
                color: #1E2A30;
                padding: 8px;
            }
        """)
        self._preview.setPlainText("Aquí aparecerá el JSON generado.")
        outer.addWidget(self._preview)
        outer.addSpacing(10)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setFont(QFont("Segoe UI", 10))
        self._status.setStyleSheet("color: #555;")
        outer.addWidget(self._status)
        outer.addStretch()

    def set_mcp_bridge(self, bridge: McpChromeBridge) -> None:
        self._mcp_bridge = bridge
        self._btn_diag.setEnabled(True)

    def _start(self):
        prompt = self._input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Falta descripción", "Escribe la descripción de la tarea para continuar.")
            return

        if self._mcp_bridge is None:
            QMessageBox.warning(
                self,
                "Bridge MCP no configurado",
                "No se encontró bridge MCP para navegación automática. Revisa config/mcp_bridge.local.json."
            )
            return

        if self._mcp_real_thread is not None and self._mcp_real_thread.isRunning():
            QMessageBox.information(
                self,
                "Proceso en curso",
                "Ya hay una corrida real ejecutándose. Espera a que termine."
            )
            return

        if not self._awaiting_continue:
            current_context = self._read_runtime_context()
            current_url = current_context.get("url", "") if isinstance(current_context, dict) else ""
            current_module_id = current_context.get("moduleId") if isinstance(current_context, dict) else None

            already_in_target = (
                isinstance(current_url, str)
                and current_url.startswith(STORECHECK_TARGET_CREATE_URL)
                and current_module_id is not None
            )

            if already_in_target:
                self._awaiting_continue = True
            else:
                try:
                    self._mcp_bridge.evaluate_script(
                        f"""() => {{
    window.location.href = {json.dumps(STORECHECK_HOME_URL, ensure_ascii=False)};
    return {{ redirectedTo: window.location.href }};
}}"""
                    )
                except Exception as exc:
                    QMessageBox.critical(
                        self,
                        "No se pudo abrir Storecheck",
                        f"Error al abrir la URL objetivo: {exc}",
                    )
                    return

                self._awaiting_continue = True
                self._btn_start.setText("Continuar proceso")
                self._status.setStyleSheet("color: #1565C0; font-size: 10pt;")
                self._status.setText(
                    "Dirígete a la sección donde se creará la tarea. "
                    "URL esperada: https://webapp.storecheck.com/moduleCapture/create"
                )
                return

        runtime_context = self._read_runtime_context()
        current_url = runtime_context.get("url", "") if isinstance(runtime_context, dict) else ""
        if not current_url.startswith(STORECHECK_TARGET_CREATE_URL):
            QMessageBox.warning(
                self,
                "URL objetivo requerida",
                "Antes de continuar, navega manualmente a:\n"
                "https://webapp.storecheck.com/moduleCapture/create"
            )
            self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
            self._status.setText(
                "URL actual no válida para ejecutar. "
                "Debes estar en /moduleCapture/create."
            )
            return

        detected_module_id = runtime_context.get("moduleId") if isinstance(runtime_context, dict) else None
        detected_scope = runtime_context.get("moduleScopeTypeId") if isinstance(runtime_context, dict) else None

        try:
            self._runtime_module_id = int(detected_module_id) if detected_module_id is not None else None
        except Exception:
            self._runtime_module_id = None

        try:
            self._runtime_scope_original = int(detected_scope) if detected_scope is not None else None
        except Exception:
            self._runtime_scope_original = None

        self._runtime_scope_target = self._runtime_scope_original

        if self._runtime_module_id is None:
            QMessageBox.warning(
                self,
                "Contexto incompleto",
                "No se pudo detectar module_id desde la URL actual. Asegúrate de estar en una tarea existente dentro de /moduleCapture/create."
            )
            self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
            self._status.setText("No se detectó module_id en la pantalla actual.")
            return

        if self._runtime_scope_original is None:
            self._runtime_scope_original = 0
            self._runtime_scope_target = 0

        orchestrator = Semana2Orchestrator(
            parser=RuleBasedTaskParser(),
            validator=TaskIRValidator(),
            executor=PlaybookExecutor(),
            auto_corrector=NoOpAutoCorrector(),
            max_retries=1,
        )

        result = orchestrator.run(prompt=prompt)
        payload = result.to_dict()
        self._last_payload = payload
        self._last_artifacts = None

        parse_data = payload.get("parse_result", {}).get("ir", {})
        validation_data = payload.get("validation_result", {})
        task_name = parse_data.get("task_name", "(sin nombre)")
        blocks = parse_data.get("blocks", [])
        edges = parse_data.get("edges", [])
        issues = validation_data.get("issues", [])
        valid = validation_data.get("valid", False)

        self._preview.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        self._btn_save.setEnabled(True)
        self._btn_copy.setEnabled(True)

        if valid:
            self._summary.setText(
                f"Tarea: {task_name} | Bloques: {len(blocks)} | Condiciones: {len(edges)} | Validación: OK"
            )
            status_color = "#2E7D32"
            status_msg = "Generación completada. Puedes guardar el resultado en docs/runs."
        else:
            self._summary.setText(
                f"Tarea: {task_name} | Bloques: {len(blocks)} | Condiciones: {len(edges)} | Validación: con incidencias"
            )
            status_color = "#C62828"
            status_msg = "Se generó salida, pero hay incidencias de validación. Revisa el preview JSON."

        self._status.setStyleSheet(f"color: {status_color}; font-size: 10pt;")
        self._status.setText(status_msg)

        details = {
            "task_name": task_name,
            "blocks": len(blocks),
            "edges": len(edges),
            "valid": valid,
            "issues": issues,
        }
        QMessageBox.information(
            self,
            "Proceso inicial completado",
            "Se generó la configuración base.\n\n"
            + json.dumps(details, ensure_ascii=False, indent=2),
        )

        self._start_triggered_real_run = True
        self._btn_start.setEnabled(False)
        self._status.setStyleSheet("color: #1565C0; font-size: 10pt;")
        self._status.setText("Contexto validado. Ejecutando generación real MCP...")
        self._run_real_mcp()

    def _save_result(self):
        if not self._last_payload:
            QMessageBox.warning(self, "Sin resultado", "Primero ejecuta \"Comenzar proceso\".")
            return

        execution_data = self._last_payload.get("execution_result")
        if not isinstance(execution_data, dict):
            QMessageBox.warning(self, "Sin ejecución", "No existe resultado de ejecución para guardar.")
            return

        execution_result = self._build_execution_result(execution_data)
        output_dir = self._default_runs_dir()
        store = EvidenceStore(output_dir)
        jsonl_path, summary_path = store.write_execution(
            case_id="ui_creador_tareas",
            execution_result=execution_result,
        )

        slug = datetime.now().strftime("%Y%m%d_%H%M%S")
        payload_path = os.path.join(output_dir, f"{slug}_ui_creador_tareas.payload.json")
        with open(payload_path, "w", encoding="utf-8") as fp:
            json.dump(self._last_payload, fp, ensure_ascii=False, indent=2)

        self._last_artifacts = {
            "jsonl": os.path.abspath(jsonl_path),
            "summary": os.path.abspath(summary_path),
            "payload": os.path.abspath(payload_path),
        }

        self._status.setStyleSheet("color: #2E7D32; font-size: 10pt;")
        self._status.setText("Artefactos guardados correctamente en docs/runs.")
        QMessageBox.information(
            self,
            "Guardado completado",
            "Se guardaron artefactos:\n\n"
            f"- {self._last_artifacts['jsonl']}\n"
            f"- {self._last_artifacts['summary']}\n"
            f"- {self._last_artifacts['payload']}"
        )

    def _run_real_mcp(self):
        prompt = self._input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Falta descripción", "Escribe la descripción de la tarea antes de correr MCP real.")
            return

        if self._mcp_bridge is None:
            QMessageBox.warning(
                self,
                "Bridge MCP no configurado",
                "Esta pantalla ya está conectada al flujo real, pero falta inyectar el bridge MCP en runtime.\n\n"
                "Opciones:\n"
                "1) Inyectar por código con set_mcp_bridge(...).\n"
                "2) Configurar archivo config/mcp_bridge.local.json y reiniciar la app."
            )
            return

        if self._mcp_real_thread is not None and self._mcp_real_thread.isRunning():
            QMessageBox.information(
                self,
                "Corrida en curso",
                "La corrida real MCP ya está ejecutándose. Espera a que termine."
            )
            return

        if self._runtime_module_id is None:
            QMessageBox.warning(
                self,
                "Contexto faltante",
                "Primero usa el flujo Comenzar/Continuar para detectar automáticamente la tarea destino."
            )
            return

        module_id = self._runtime_module_id
        original_scope = self._runtime_scope_original if self._runtime_scope_original is not None else 0
        target_scope = self._runtime_scope_target if self._runtime_scope_target is not None else original_scope

        self._btn_start.setEnabled(False)
        self._status.setStyleSheet("color: #1565C0; font-size: 10pt;")
        self._status.setText("Ejecutando corrida real MCP...")

        output_dir = self._default_runs_dir()
        self._mcp_real_thread = QThread(self)
        self._mcp_real_worker = _RealMcpRunWorker(
            bridge=self._mcp_bridge,
            prompt=prompt,
            module_id=module_id,
            original_scope=original_scope,
            target_scope=target_scope,
            output_dir=output_dir,
        )
        self._mcp_real_worker.moveToThread(self._mcp_real_thread)

        self._mcp_real_thread.started.connect(self._mcp_real_worker.run)
        self._mcp_real_worker.success.connect(self._on_real_mcp_success)
        self._mcp_real_worker.error.connect(self._on_real_mcp_error)
        self._mcp_real_worker.success.connect(self._mcp_real_thread.quit)
        self._mcp_real_worker.error.connect(self._mcp_real_thread.quit)
        self._mcp_real_thread.finished.connect(self._cleanup_real_mcp_thread)
        self._mcp_real_thread.start()

    def _test_mcp_connection(self):
        if self._mcp_bridge is None:
            QMessageBox.warning(
                self,
                "Bridge MCP no configurado",
                "No se encontró bridge MCP en runtime. Revisa config/mcp_bridge.local.json."
            )
            return

        if self._mcp_test_thread is not None and self._mcp_test_thread.isRunning():
            QMessageBox.information(
                self,
                "Prueba en curso",
                "La prueba de conexión MCP ya está ejecutándose. Espera unos segundos."
            )
            return

        self._btn_test_mcp.setEnabled(False)
        self._status.setStyleSheet("color: #1565C0; font-size: 10pt;")
        self._status.setText("Probando conexión MCP...")

        self._mcp_test_thread = QThread(self)
        self._mcp_test_worker = _McpConnectionWorker(self._mcp_bridge)
        self._mcp_test_worker.moveToThread(self._mcp_test_thread)

        self._mcp_test_thread.started.connect(self._mcp_test_worker.run)
        self._mcp_test_worker.success.connect(self._on_mcp_test_success)
        self._mcp_test_worker.error.connect(self._on_mcp_test_error)
        self._mcp_test_worker.success.connect(self._mcp_test_thread.quit)
        self._mcp_test_worker.error.connect(self._mcp_test_thread.quit)
        self._mcp_test_thread.finished.connect(self._cleanup_mcp_test_thread)
        self._mcp_test_thread.start()

    def _on_real_mcp_success(self, data: object):
        payload = {}
        artifacts = {}
        if isinstance(data, dict):
            raw_payload = data.get("payload")
            raw_artifacts = data.get("artifacts")
            if isinstance(raw_payload, dict):
                payload = raw_payload
            if isinstance(raw_artifacts, dict):
                artifacts = raw_artifacts

        self._last_payload = payload
        self._last_artifacts = artifacts if artifacts else None
        self._preview.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

        steps = payload.get("execution_result", {}).get("steps", [])
        reqids = [str(step.get("reqid")) for step in steps if step.get("reqid") is not None]
        success = payload.get("execution_result", {}).get("success", False)
        critical_actions = {"create_block", "update_block", "attach_condition", "save_task", "verify_task"}
        missing_critical = [
            step.get("action", "unknown")
            for step in steps
            if step.get("action") in critical_actions
            and (step.get("reqid") is None or not bool(step.get("success")))
        ]

        if success:
            self._status.setStyleSheet("color: #2E7D32; font-size: 10pt;")
            self._status.setText(
                f"Corrida MCP real exitosa. reqids: {', '.join(reqids) if reqids else 'N/A'}"
            )
            if self._mcp_bridge is not None:
                try:
                    self._mcp_bridge.evaluate_script(
                        """() => {
    setTimeout(() => {
        try { window.location.reload(); } catch (_e) {}
    }, 300);
    return { reloading: true };
}"""
                    )
                except Exception:
                    pass
        else:
            self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
            missing_text = ", ".join(missing_critical) if missing_critical else "N/A"
            self._status.setText(
                "Corrida MCP real finalizada con incidencias. "
                f"reqids: {', '.join(reqids) if reqids else 'N/A'} | "
                f"faltantes críticos: {missing_text}"
            )

        QMessageBox.information(
            self,
            "Corrida real completada",
            "Se ejecutó el flujo real MCP y se guardaron artefactos en docs/runs."
        )

    def _on_real_mcp_error(self, error_text: str):
        self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
        self._status.setText(f"Error en corrida real MCP: {error_text}")
        QMessageBox.critical(self, "Error MCP", error_text)

    def _cleanup_real_mcp_thread(self):
        self._btn_start.setEnabled(True)

        if self._start_triggered_real_run:
            self._awaiting_continue = False
            self._start_triggered_real_run = False
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Comenzar proceso")

        if self._mcp_real_worker is not None:
            self._mcp_real_worker.deleteLater()
            self._mcp_real_worker = None

        if self._mcp_real_thread is not None:
            self._mcp_real_thread.deleteLater()
            self._mcp_real_thread = None

    def _on_mcp_test_success(self, preview: str):
        self._status.setStyleSheet("color: #2E7D32; font-size: 10pt;")
        self._status.setText("Conexión MCP OK. Puedes ejecutar corrida real.")
        QMessageBox.information(
            self,
            "Conexión MCP exitosa",
            "Se pudo consultar red vía MCP correctamente.\n\n"
            f"Muestra: {preview}"
        )

    def _on_mcp_test_error(self, error_text: str):
        self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
        self._status.setText(f"Conexión MCP con error: {error_text}")
        QMessageBox.critical(
            self,
            "Error de conexión MCP",
            error_text,
        )

    def _cleanup_mcp_test_thread(self):
        self._btn_start.setEnabled(True)

        if self._mcp_test_worker is not None:
            self._mcp_test_worker.deleteLater()
            self._mcp_test_worker = None

        if self._mcp_test_thread is not None:
            self._mcp_test_thread.deleteLater()
            self._mcp_test_thread = None

    def _copy_json(self):
        if not self._last_payload:
            QMessageBox.warning(self, "Sin resultado", "No hay JSON para copiar todavía.")
            return

        text = json.dumps(self._last_payload, ensure_ascii=False, indent=2)
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        self._status.setStyleSheet("color: #1565C0; font-size: 10pt;")
        self._status.setText("JSON copiado al portapapeles.")

    def _capture_publish_diagnostic(self):
        if self._mcp_bridge is None:
            QMessageBox.warning(
                self,
                "Bridge MCP no configurado",
                "No se encontró bridge MCP para capturar diagnóstico.",
            )
            return

        try:
            runtime_context = self._read_runtime_context()
            page_diagnostic = self._mcp_bridge.evaluate_script(
                """() => {
    const title = String(document && document.title ? document.title : '');
    const url = String(window.location && window.location.href ? window.location.href : '');
    const bodyText = String(document && document.body ? document.body.innerText || '' : '');
    const alertTexts = Array.from(document.querySelectorAll('.alert, .toast, .modal-body, [role=\"alert\"]'))
        .map((node) => String(node.textContent || '').trim())
        .filter(Boolean)
        .slice(0, 20);

    const lowered = bodyText.toLowerCase();
    const keywordHits = [];
    const keywords = ['grails', 'error', 'servidor', 'server', 'timeout', 'procesando'];
    for (const keyword of keywords) {
        if (lowered.includes(keyword)) {
            keywordHits.push(keyword);
        }
    }

    return {
        title,
        url,
        alertTexts,
        keywordHits,
    };
}"""
            )
            listings: list[object] = []
            request_plans = [
                {"resource_types": ["xhr", "fetch"], "include_preserved_requests": False},
                {"resource_types": ["xhr", "fetch"], "include_preserved_requests": True},
                {"resource_types": None, "include_preserved_requests": False},
                {"resource_types": None, "include_preserved_requests": True},
            ]

            for plan in request_plans:
                captured_any = False
                for page_idx in (0, 1):
                    try:
                        listing = self._mcp_bridge.list_network_requests(
                            resource_types=plan["resource_types"],
                            page_size=250,
                            include_preserved_requests=plan["include_preserved_requests"],
                            page_idx=page_idx,
                        )
                        listings.append(listing)
                        captured_any = True
                    except Exception:
                        continue
                if captured_any:
                    break

            if not listings:
                listings.append(
                    self._mcp_bridge.list_network_requests(
                        resource_types=["xhr", "fetch"],
                        page_size=250,
                        include_preserved_requests=False,
                    )
                )

            reqid_set: set[int] = set()
            parsed_listing_items: list[dict] = []
            raw_listing_parts: list[str] = []
            for listing in listings:
                reqid_set.update(self._extract_reqids(listing))
                parsed_listing_items.extend(self._extract_requests_from_listing(listing))
                raw_listing_parts.append(listing if isinstance(listing, str) else json.dumps(listing, ensure_ascii=False))

            reqids = sorted(reqid_set, reverse=True)
            failed_requests: list[dict] = []
            recent_requests: list[dict] = []

            dedup_parsed: dict[tuple[int, str], dict] = {}
            for item in sorted(parsed_listing_items, key=lambda x: int(x.get("reqid", 0)), reverse=True):
                key = (int(item.get("reqid", 0)), str(item.get("endpoint", "")))
                if key not in dedup_parsed:
                    dedup_parsed[key] = item

            for item in list(dedup_parsed.values())[:60]:
                if len(recent_requests) < 20:
                    recent_requests.append(item)
                if int(item.get("status", 0)) >= 400:
                    failed_requests.append(item)

            for reqid in reqids[:80]:
                request_details = self._safe_get_request_details(reqid)
                status = self._extract_status(request_details)
                endpoint = self._extract_endpoint(request_details)
                method = self._extract_method(request_details)
                item = {
                    "reqid": reqid,
                    "status": status,
                    "endpoint": endpoint,
                    "method": method,
                }
                if len(recent_requests) < 20 and not any(r.get("reqid") == reqid for r in recent_requests):
                    recent_requests.append(item)

                if status >= 400 and not any(r.get("reqid") == reqid for r in failed_requests):
                    failed_requests.append(item)

            severe_failed_requests = [
                item for item in failed_requests
                if int(item.get("status", 0)) >= 500
            ]

            for item in severe_failed_requests[:8]:
                try:
                    reqid_value = int(item.get("reqid", 0))
                except (TypeError, ValueError):
                    continue

                details = self._safe_get_request_details(reqid_value)
                if details:
                    item["details_excerpt"] = self._summarize_request_details(details)

            output_dir = self._default_runs_dir()
            slug = datetime.now().strftime("%Y%m%d_%H%M%S")
            diagnostic_path = os.path.join(output_dir, f"{slug}_ui_publish_diagnostic.json")

            payload = {
                "captured_at": datetime.now().isoformat(),
                "runtime_context": runtime_context,
                "page": page_diagnostic if isinstance(page_diagnostic, dict) else {"raw": page_diagnostic},
                "analysis": {
                    "has_validation_alert": (
                        isinstance(page_diagnostic, dict)
                        and any(
                            "campos por validar" in str(text).lower()
                            for text in page_diagnostic.get("alertTexts", [])
                        )
                    ),
                    "has_server_error_text": (
                        isinstance(page_diagnostic, dict)
                        and any(
                            "an error has occurred" in str(text).lower()
                            for text in page_diagnostic.get("alertTexts", [])
                        )
                    ),
                },
                "network": {
                    "failed_requests": failed_requests,
                    "severe_failed_requests": severe_failed_requests,
                    "recent_requests": recent_requests,
                    "reqids_count": len(reqids),
                    "parsed_listing_count": len(dedup_parsed),
                    "listings_count": len(listings),
                    "raw_listing": "\n\n--- PAGE BREAK ---\n\n".join(raw_listing_parts),
                },
                "last_artifacts": self._last_artifacts or {},
            }

            with open(diagnostic_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)

            self._status.setStyleSheet("color: #2E7D32; font-size: 10pt;")
            self._status.setText(
                "Diagnóstico UI guardado en docs/runs. "
                f"Errores de red detectados: {len(failed_requests)}"
            )
            QMessageBox.information(
                self,
                "Diagnóstico capturado",
                "Se guardó el diagnóstico UI en:\n\n"
                f"{os.path.abspath(diagnostic_path)}\n\n"
                f"Errores de red detectados: {len(failed_requests)}",
            )
        except Exception as exc:
            self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
            self._status.setText(f"No se pudo capturar diagnóstico UI: {exc}")
            QMessageBox.critical(self, "Error al capturar diagnóstico", str(exc))

    def _safe_get_request_details(self, reqid: int) -> object:
        if self._mcp_bridge is None:
            return {}
        try:
            return self._mcp_bridge.get_network_request(reqid)
        except Exception:
            return {}

    @staticmethod
    def _extract_reqids(payload: object) -> set[int]:
        reqids: set[int] = set()

        if isinstance(payload, dict):
            for key in ("requests", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    reqids.update(VistaCreadorTareas._extract_reqids(value))

            direct = payload.get("reqid")
            if isinstance(direct, int):
                reqids.add(direct)

        if isinstance(payload, list):
            for item in payload:
                reqids.update(VistaCreadorTareas._extract_reqids(item))

        if isinstance(payload, str):
            for match in re.findall(r"reqid\s*=\s*(\d+)", payload):
                reqids.add(int(match))

        return reqids

    @staticmethod
    def _extract_endpoint(request_details: object) -> str:
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
            match = re.search(r"https?://\S+", request_details)
            if match:
                return match.group(0)

        return ""

    @staticmethod
    def _extract_status(request_details: object) -> int:
        if isinstance(request_details, dict):
            for key in ("status", "status_code", "http_status"):
                value = request_details.get(key)
                if isinstance(value, int):
                    return value

            response_obj = request_details.get("response")
            if isinstance(response_obj, dict):
                value = response_obj.get("status")
                if isinstance(value, int):
                    return value

        if isinstance(request_details, str):
            match = re.search(r"\[(\d{3})\]", request_details)
            if match:
                return int(match.group(1))

            match = re.search(r"\b(\d{3})\b", request_details)
            if match:
                return int(match.group(1))

        return 0

    @staticmethod
    def _extract_method(request_details: object) -> str:
        if isinstance(request_details, dict):
            direct_method = request_details.get("method")
            if isinstance(direct_method, str) and direct_method:
                return direct_method.upper()

            request_obj = request_details.get("request")
            if isinstance(request_obj, dict):
                nested_method = request_obj.get("method")
                if isinstance(nested_method, str) and nested_method:
                    return nested_method.upper()

        if isinstance(request_details, str):
            match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b", request_details)
            if match:
                return match.group(1)

        return ""

    @staticmethod
    def _extract_request_body_excerpt(request_details: object) -> str | None:
        if isinstance(request_details, dict):
            for key in ("requestBody", "request_body", "postData"):
                value = request_details.get(key)
                if isinstance(value, str) and value.strip():
                    return value[:1500]

            request_obj = request_details.get("request")
            if isinstance(request_obj, dict):
                for key in ("postData", "body", "requestBody"):
                    value = request_obj.get(key)
                    if isinstance(value, str) and value.strip():
                        return value[:1500]

        if isinstance(request_details, str):
            match = re.search(r"Request Body\n([\s\S]*?)(?:\n(?:Response Body|Headers)\n|$)", request_details)
            if match:
                return match.group(1).strip()[:1500]

        return None

    @staticmethod
    def _extract_response_body_excerpt(request_details: object) -> str | None:
        if isinstance(request_details, dict):
            for key in ("responseBody", "response_body", "body", "body_preview"):
                value = request_details.get(key)
                if isinstance(value, str) and value.strip():
                    return value[:1500]

            response_obj = request_details.get("response")
            if isinstance(response_obj, dict):
                for key in ("body", "responseBody", "text"):
                    value = response_obj.get(key)
                    if isinstance(value, str) and value.strip():
                        return value[:1500]

        if isinstance(request_details, str):
            match = re.search(r"Response Body\n([\s\S]*?)(?:\nHeaders\n|$)", request_details)
            if match:
                return match.group(1).strip()[:1500]

        return None

    @staticmethod
    def _summarize_request_details(request_details: object) -> dict:
        summary: dict[str, object] = {
            "status": VistaCreadorTareas._extract_status(request_details),
            "endpoint": VistaCreadorTareas._extract_endpoint(request_details),
            "method": VistaCreadorTareas._extract_method(request_details),
            "request_body_excerpt": VistaCreadorTareas._extract_request_body_excerpt(request_details),
            "response_body_excerpt": VistaCreadorTareas._extract_response_body_excerpt(request_details),
        }

        if isinstance(request_details, dict):
            request_obj = request_details.get("request")
            response_obj = request_details.get("response")
            if isinstance(request_obj, dict):
                headers = request_obj.get("headers")
                if isinstance(headers, dict):
                    summary["request_headers"] = headers
            if isinstance(response_obj, dict):
                headers = response_obj.get("headers")
                if isinstance(headers, dict):
                    summary["response_headers"] = headers

        return summary

    @staticmethod
    def _extract_requests_from_listing(payload: object) -> list[dict]:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        items: list[dict] = []
        pattern = re.compile(
            r"reqid\s*=\s*(\d+)\s+([A-Z]+)\s+(https?://\S+)\s+\[(\d{3})\]"
        )
        for match in pattern.finditer(text):
            items.append(
                {
                    "reqid": int(match.group(1)),
                    "method": match.group(2),
                    "endpoint": match.group(3),
                    "status": int(match.group(4)),
                }
            )
        return items

    @staticmethod
    def _build_execution_result(execution_data: dict):
        from core.creador_de_tareas.contracts import ExecutionResult, ExecutionStepEvidence

        steps = []
        for raw in execution_data.get("steps", []):
            steps.append(
                ExecutionStepEvidence(
                    action=raw.get("action", "unknown"),
                    endpoint=raw.get("endpoint"),
                    http_status=raw.get("http_status"),
                    request_payload_excerpt=raw.get("request_payload_excerpt"),
                    response_excerpt=raw.get("response_excerpt"),
                    response_json=raw.get("response_json"),
                    reqid=raw.get("reqid"),
                    success=bool(raw.get("success", False)),
                    operational_success_reason=raw.get("operational_success_reason"),
                    notes=raw.get("notes", ""),
                )
            )

        return ExecutionResult(
            executed=bool(execution_data.get("executed", False)),
            success=bool(execution_data.get("success", False)),
            steps=steps,
            final_snapshot=execution_data.get("final_snapshot") or {},
        )

    @staticmethod
    def _default_runs_dir() -> str:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        runs_dir = os.path.join(root, "docs", "runs")
        os.makedirs(runs_dir, exist_ok=True)
        return runs_dir

    def _read_runtime_context(self) -> dict:
        if self._mcp_bridge is None:
            return {}

        script = """() => {
    const module = window.module || {};
    const capture = module.moduleCapture || {};
    return {
        url: String(window.location && window.location.href ? window.location.href : ''),
        title: String(document && document.title ? document.title : ''),
        moduleId: capture.id ?? null,
        moduleScopeTypeId: capture.moduleScopeTypeId ?? null,
    };
}"""

        try:
            payload = self._mcp_bridge.evaluate_script(script)
        except Exception:
            return {}

        if isinstance(payload, dict):
            return payload

        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"url": payload}

        return {}
