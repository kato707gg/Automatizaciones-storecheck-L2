"""
Vista – Creador de tareas automático
Interfaz funcional para capturar prompt, generar base y guardar artefactos.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.semana2.autofix_stub import NoOpAutoCorrector
from core.semana2.evidence import EvidenceStore
from core.semana2.executor_h3 import PlaybookExecutor
from core.semana2.executor_h3 import ScopeTypePatternRunner
from core.semana2.mcp_backend import McpChromeBridge, McpScopeTypeBackend
from core.semana2.orchestrator import Semana2Orchestrator
from core.semana2.parser_mvp import RuleBasedTaskParser
from core.semana2.validator import TaskIRValidator


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
            "2. Presiona \"Comenzar proceso\" para generar y validar\n"
            "3. Revisa el preview JSON y guarda artefactos"
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

        actions.addWidget(self._btn_save)
        actions.addWidget(self._btn_copy)
        actions.addStretch()
        outer.addLayout(actions)
        outer.addSpacing(12)

        real_title = QLabel("Corrida real MCP")
        real_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        real_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(real_title)
        outer.addSpacing(8)

        real_row = QHBoxLayout()
        real_row.setSpacing(8)

        self._module_id = QLineEdit()
        self._module_id.setPlaceholderText("module_id")
        self._module_id.setFixedHeight(34)
        self._module_id.setStyleSheet(
            "QLineEdit { border: 1.2px solid #C9D1D6; border-radius: 8px; padding: 6px; }"
        )

        self._scope_original = QLineEdit()
        self._scope_original.setPlaceholderText("scope original")
        self._scope_original.setFixedHeight(34)
        self._scope_original.setStyleSheet(
            "QLineEdit { border: 1.2px solid #C9D1D6; border-radius: 8px; padding: 6px; }"
        )

        self._scope_target = QLineEdit()
        self._scope_target.setPlaceholderText("scope objetivo")
        self._scope_target.setFixedHeight(34)
        self._scope_target.setStyleSheet(
            "QLineEdit { border: 1.2px solid #C9D1D6; border-radius: 8px; padding: 6px; }"
        )

        self._btn_real = QPushButton("Ejecutar corrida real MCP")
        self._btn_real.setFixedHeight(38)
        self._btn_real.setCursor(Qt.PointingHandCursor)
        self._btn_real.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #006B88;
                border: 1.8px solid #006B88;
                border-radius: 19px;
                padding: 0 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #E9F7FB; }
        """)
        self._btn_real.clicked.connect(self._run_real_mcp)

        self._btn_test_mcp = QPushButton("Probar conexión MCP")
        self._btn_test_mcp.setFixedHeight(38)
        self._btn_test_mcp.setCursor(Qt.PointingHandCursor)
        self._btn_test_mcp.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #1565C0;
                border: 1.8px solid #1565C0;
                border-radius: 19px;
                padding: 0 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #EAF2FF; }
        """)
        self._btn_test_mcp.clicked.connect(self._test_mcp_connection)

        real_row.addWidget(self._module_id, 2)
        real_row.addWidget(self._scope_original, 1)
        real_row.addWidget(self._scope_target, 1)
        real_row.addWidget(self._btn_test_mcp, 2)
        real_row.addWidget(self._btn_real, 2)
        outer.addLayout(real_row)
        outer.addSpacing(10)

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

    def _start(self):
        prompt = self._input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Falta descripción", "Escribe la descripción de la tarea para continuar.")
            return

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

        try:
            module_id = int(self._module_id.text().strip())
            original_scope = int(self._scope_original.text().strip())
            target_scope = int(self._scope_target.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Campos inválidos", "module_id y scope deben ser numéricos.")
            return

        self._btn_real.setEnabled(False)
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

        if success:
            self._status.setStyleSheet("color: #2E7D32; font-size: 10pt;")
            self._status.setText(
                f"Corrida MCP real exitosa. reqids: {', '.join(reqids) if reqids else 'N/A'}"
            )
        else:
            self._status.setStyleSheet("color: #C62828; font-size: 10pt;")
            self._status.setText(
                f"Corrida MCP real finalizada con incidencias. reqids: {', '.join(reqids) if reqids else 'N/A'}"
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
        self._btn_real.setEnabled(True)

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
        self._btn_test_mcp.setEnabled(True)

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

    @staticmethod
    def _build_execution_result(execution_data: dict):
        from core.semana2.contracts import ExecutionResult, ExecutionStepEvidence

        steps = []
        for raw in execution_data.get("steps", []):
            steps.append(
                ExecutionStepEvidence(
                    action=raw.get("action", "unknown"),
                    endpoint=raw.get("endpoint"),
                    request_payload_excerpt=raw.get("request_payload_excerpt"),
                    response_excerpt=raw.get("response_excerpt"),
                    reqid=raw.get("reqid"),
                    success=bool(raw.get("success", False)),
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
