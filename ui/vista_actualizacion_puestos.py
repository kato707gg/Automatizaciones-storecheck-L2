"""
Vista - Actualizacion de puestos
Interfaz funcional: drag & drop de archivos requeridos, validacion visual y ejecucion en hilo.
"""

from __future__ import annotations

import os
from datetime import datetime

import openpyxl
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.actualizacion_puestos import procesar_actualizacion_puestos
from ui.components.action_buttons import (
    create_back_button,
    create_primary_action_button,
    create_status_action_button,
)
from ui.components.drop_zone import DropZone


class _ProcesoThread(QThread):
    terminado = Signal(str)
    error_ocurrido = Signal(str)

    def __init__(self, ruta_catalogo_puestos: str, ruta_layout_roles: str):
        super().__init__()
        self._ruta_catalogo_puestos = ruta_catalogo_puestos
        self._ruta_layout_roles = ruta_layout_roles

    def run(self):
        try:
            carpeta_salida = os.path.join(
                os.path.expanduser("~/Downloads"),
                f"Actualizacion_puestos_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            ruta_salida = procesar_actualizacion_puestos(
                self._ruta_catalogo_puestos,
                self._ruta_layout_roles,
                carpeta_salida,
            )
            self.terminado.emit(ruta_salida)
        except BaseException as exc:
            self.error_ocurrido.emit(str(exc))


class VistaActualizacionPuestos(QWidget):
    def __init__(self, back_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._hilo = None
        self.setStyleSheet("VistaActualizacionPuestos { background-color: #FFFFFF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.setSpacing(0)

        self._btn_back = create_back_button(on_click=back_cb)
        outer.addWidget(self._btn_back, 0, Qt.AlignLeft)
        outer.addSpacing(24)

        title = QLabel("Actualización de puestos")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet("color: #0098C4;")
        outer.addWidget(title)
        outer.addSpacing(10)

        desc = QLabel(
            "Esta automatización revisa los datos nuevos para cambiar el nombre del puesto, "
            "reasignarlo a un usuario distinto o crear el puesto cuando se detecta un usuario nuevo."
        )
        desc.setFont(QFont("Segoe UI", 13))
        desc.setStyleSheet("color: #333;")
        desc.setWordWrap(True)
        outer.addWidget(desc)
        outer.addSpacing(22)

        section_title = QLabel("Qué hace el flujo")
        section_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        section_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(section_title)
        outer.addSpacing(8)

        steps_frame = QWidget()
        steps_frame.setStyleSheet(
            "QWidget { background-color: #F8FAFB; border: 1px solid #D7DEE3; border-radius: 12px; }"
        )
        steps_layout = QVBoxLayout(steps_frame)
        steps_layout.setContentsMargins(18, 14, 18, 14)
        steps_layout.setSpacing(6)

        steps = QLabel(
            "1. Verifica los datos nuevos del catálogo de puestos.\n"
            "2. Cambia el nombre del puesto cuando exista una actualización.\n"
            "3. Reasigna el puesto a un nuevo usuario cuando corresponda.\n"
            "4. Si detecta un usuario nuevo, prepara también su puesto."
        )
        steps.setFont(QFont("Segoe UI", 11))
        steps.setStyleSheet("color: #222;")
        steps.setWordWrap(True)
        steps_layout.addWidget(steps)
        outer.addWidget(steps_frame)
        outer.addSpacing(18)

        req_title = QLabel("Requerimientos")
        req_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        req_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(req_title)
        outer.addSpacing(6)

        req_body = QLabel("  · Catálogo de puestos\n  · layout_roles")
        req_body.setFont(QFont("Segoe UI", 12))
        req_body.setStyleSheet("color: #333;")
        outer.addWidget(req_body)
        outer.addSpacing(18)

        drops = QHBoxLayout()
        drops.setSpacing(20)
        self._dz_catalogo = DropZone(
            "Arrastra aquí el archivo\nCatálogo de puestos",
            patron="puestos",
        )
        self._dz_layout_roles = DropZone(
            "Arrastra aquí la plantilla\nlayout_roles",
            patron="layout_roles",
        )
        drops.addWidget(self._dz_catalogo)
        drops.addWidget(self._dz_layout_roles)
        outer.addLayout(drops)
        outer.addSpacing(22)

        self._estado = QStackedWidget()
        self._estado.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        outer.addWidget(self._estado)

        idle = QWidget()
        idle_layout = QVBoxLayout(idle)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setAlignment(Qt.AlignCenter)

        self._btn_validar = create_primary_action_button(
            "Comenzar proceso",
            on_click=self._comenzar,
        )
        idle_layout.addWidget(self._btn_validar)
        self._estado.addWidget(idle)

        progress = QWidget()
        progress_layout = QVBoxLayout(progress)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setAlignment(Qt.AlignCenter)
        progress_layout.setSpacing(12)
        progress_label = QLabel("Procesando archivos…")
        progress_label.setFont(QFont("Segoe UI", 11))
        progress_label.setStyleSheet("color: #555;")
        progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(progress_label)
        self._estado.addWidget(progress)

        error = QWidget()
        error_layout = QVBoxLayout(error)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.setAlignment(Qt.AlignCenter)
        error_layout.setSpacing(10)
        self._lbl_error = QLabel()
        self._lbl_error.setFont(QFont("Segoe UI", 10))
        self._lbl_error.setStyleSheet("color: #C62828;")
        self._lbl_error.setWordWrap(True)
        self._lbl_error.setAlignment(Qt.AlignCenter)
        error_layout.addWidget(self._lbl_error)
        btn_retry = create_status_action_button(
            "↺  Volver a intentar",
            on_click=self._reiniciar,
            tone="error",
        )
        error_layout.addWidget(btn_retry, 0, Qt.AlignHCenter)
        self._estado.addWidget(error)

        success = QWidget()
        success_layout = QVBoxLayout(success)
        success_layout.setContentsMargins(0, 0, 0, 0)
        success_layout.setAlignment(Qt.AlignCenter)
        success_layout.setSpacing(10)
        self._lbl_ok = QLabel()
        self._lbl_ok.setFont(QFont("Segoe UI", 11))
        self._lbl_ok.setStyleSheet("color: #2E7D32;")
        self._lbl_ok.setWordWrap(True)
        self._lbl_ok.setAlignment(Qt.AlignCenter)
        success_layout.addWidget(self._lbl_ok)
        btn_again = create_status_action_button(
            "↺  Preparar de nuevo",
            on_click=self._reiniciar,
            tone="success",
        )
        success_layout.addWidget(btn_again, 0, Qt.AlignHCenter)
        self._estado.addWidget(success)

        self._estado.setCurrentIndex(0)
        outer.addStretch()

    def _validar(self) -> str | None:
        faltantes = []
        if not self._dz_catalogo.tiene_archivo():
            faltantes.append("catálogo de puestos")
        if not self._dz_layout_roles.tiene_archivo():
            faltantes.append("layout_roles")

        if faltantes:
            return "Faltan archivos requeridos: " + ", ".join(faltantes) + "."

        for ruta, etiqueta in (
            (self._dz_catalogo.ruta, "catálogo de puestos"),
            (self._dz_layout_roles.ruta, "layout_roles"),
        ):
            try:
                wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
                wb.close()
            except PermissionError:
                return f"El archivo {etiqueta} está abierto en Excel. Ciérralo e intenta de nuevo."
            except Exception:
                return f"No se pudo leer el archivo {etiqueta}. Asegúrate de que no esté dañado."

        return None

    def _comenzar(self):
        error = self._validar()
        if error:
            self._mostrar_error(error)
            return

        self._btn_back.setEnabled(False)
        self._dz_catalogo.setEnabled(False)
        self._dz_layout_roles.setEnabled(False)
        self._estado.setCurrentIndex(1)

        self._hilo = _ProcesoThread(
            ruta_catalogo_puestos=self._dz_catalogo.ruta,
            ruta_layout_roles=self._dz_layout_roles.ruta,
        )
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.error_ocurrido.connect(self._on_error)
        self._hilo.finished.connect(self._on_hilo_finalizado)
        self._hilo.start()

    def _on_terminado(self, ruta_salida: str):
        self._btn_back.setEnabled(True)
        self._lbl_ok.setText(
            f"✓  Proceso terminado\nArchivo guardado en:\n{ruta_salida}"
        )
        self._estado.setCurrentIndex(3)

    def _on_error(self, msg: str):
        self._btn_back.setEnabled(True)
        self._mostrar_error(msg)

    def _on_hilo_finalizado(self):
        self._hilo = None

    def _mostrar_error(self, msg: str):
        self._lbl_error.setText(f"⚠  {msg}")
        self._estado.setCurrentIndex(2)

    def _reiniciar(self):
        self._estado.setCurrentIndex(0)
        self._btn_back.setEnabled(True)
        self._dz_catalogo.reset()
        self._dz_layout_roles.reset()
        self._dz_catalogo.setEnabled(True)
        self._dz_layout_roles.setEnabled(True)
