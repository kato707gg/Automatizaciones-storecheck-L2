"""
Vista – Actualizar catálogo de lugares
Interfaz funcional: drag & drop, validación, proceso en hilo, salida a Descargas.
"""

import os
import sys
import shutil
import openpyxl
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QProgressBar,
    QFileDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QCursor

from ui.components.drop_zone import DropZone


# ── Suprimir prints de los scripts de procesamiento ──────────────────
class _NullIO:
    def write(self, *a): pass
    def flush(self): pass


def _ruta_base_app() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # __file__ está en ui/ → subir un nivel para obtener la raíz del proyecto
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Hilo de procesamiento ─────────────────────────────────────────────
class _ProcesoThread(QThread):
    terminado      = Signal(str)   # carpeta de salida en Descargas
    error_ocurrido = Signal(str)   # mensaje de error

    def __init__(self, ruta_maestro, ruta_layout_places):
        super().__init__()
        self._ruta_maestro       = ruta_maestro
        self._ruta_layout_places = ruta_layout_places

    def run(self):
        _out, _err = sys.stdout, sys.stderr
        sys.stdout = _NullIO()
        sys.stderr = _NullIO()
        try:
            from core.catalogo_lugares import actualizar_catalogo_lugares

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            carpeta_salida = os.path.join(
                os.path.expanduser("~/Downloads"),
                f"Actualizacion_lugares_{ts}")
            os.makedirs(carpeta_salida, exist_ok=True)

            if not actualizar_catalogo_lugares(
                    self._ruta_maestro,
                    self._ruta_layout_places,
                    carpeta_salida):
                raise RuntimeError("El proceso terminó sin resultados.")

            self.terminado.emit(carpeta_salida)

        except ImportError:
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                carpeta_salida = os.path.join(
                    os.path.expanduser("~/Downloads"),
                    f"Actualizacion_lugares_{ts}")
                os.makedirs(carpeta_salida, exist_ok=True)
                ext = os.path.splitext(self._ruta_layout_places)[1]
                shutil.copy2(
                    self._ruta_layout_places,
                    os.path.join(carpeta_salida, f"layout_places_actualizado_{ts}{ext}"))
                self.terminado.emit(carpeta_salida)
            except Exception as exc:
                self.error_ocurrido.emit(str(exc))
        except BaseException as exc:
            self.error_ocurrido.emit(str(exc))
        finally:
            sys.stdout = _out
            sys.stderr = _err


# ── Vista principal ───────────────────────────────────────────────────
class VistaActualizarCatalogoLugares(QWidget):
    def __init__(self, back_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._hilo    = None
        self.setStyleSheet(
            "VistaActualizarCatalogoLugares { background-color: #FFFFFF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
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

        content = outer

        # ── Título ───────────────────────────────────────────────────
        lbl_title = QLabel("Actualizar catalogo lugares")
        lbl_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        lbl_title.setStyleSheet("color: #0098C4;")
        content.addWidget(lbl_title)
        content.addSpacing(10)

        # ── Descripción ──────────────────────────────────────────────
        lbl_desc = QLabel(
            "Dependiendo el maestro de lugares se detectara si hay cambios en el valor de "
            "algun dato de las tiendas y se actualizara, asi como detectara si hay nuevos "
            "lugares y los agregara. Este proceso dara como resultado un archivo layout_places "
            "listo para subir al sistema"
        )
        lbl_desc.setFont(QFont("Segoe UI", 13))
        lbl_desc.setStyleSheet("color: #333;")
        lbl_desc.setWordWrap(True)
        content.addWidget(lbl_desc)
        content.addSpacing(28)

        # ── Requerimientos ───────────────────────────────────────────
        lbl_req_titulo = QLabel("Requerimientos")
        lbl_req_titulo.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_req_titulo.setStyleSheet("color: #0098C4;")
        content.addWidget(lbl_req_titulo)
        content.addSpacing(6)

        lbl_req_body = QLabel("  · Maestro de lugares\n  · layout_places")
        lbl_req_body.setFont(QFont("Segoe UI", 12))
        lbl_req_body.setStyleSheet("color: #333;")
        content.addWidget(lbl_req_body)
        content.addSpacing(32)

        # ── Zonas de drop ────────────────────────────────────────────
        drops_layout = QHBoxLayout()
        drops_layout.setSpacing(20)
        self._dz_maestro = DropZone("Arrastra aqui el archivo\nMaestro de lugares")
        self._dz_places  = DropZone(
            "Arrastra aqui el archivo\nlayout_places",
            patron="layout_places")
        drops_layout.addWidget(self._dz_maestro)
        drops_layout.addWidget(self._dz_places)
        content.addLayout(drops_layout)
        content.addSpacing(32)

        # ── Zona inferior intercambiable: 0=idle 1=procesando 2=error 3=éxito
        self._estado = QStackedWidget()
        content.addWidget(self._estado)

        # Estado 0 – botón
        w0 = QWidget()
        l0 = QVBoxLayout(w0)
        l0.setContentsMargins(0, 0, 0, 0)
        l0.setAlignment(Qt.AlignCenter)
        self._btn_iniciar = QPushButton("Comenzar proceso")
        self._btn_iniciar.setFixedSize(240, 50)
        self._btn_iniciar.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._btn_iniciar.setCursor(Qt.PointingHandCursor)
        self._btn_iniciar.setStyleSheet("""
            QPushButton {
                background-color: #0098C4; color: #FFFFFF;
                border: none; border-radius: 25px;
            }
            QPushButton:hover   { background-color: #007BA3; }
            QPushButton:pressed { background-color: #006080; }
        """)
        self._btn_iniciar.clicked.connect(self._comenzar)
        l0.addWidget(self._btn_iniciar)
        self._estado.addWidget(w0)

        # Estado 1 – progreso
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setAlignment(Qt.AlignCenter)
        l1.setSpacing(12)
        self._pbar = QProgressBar()
        self._pbar.setRange(0, 0)
        self._pbar.setFixedSize(340, 10)
        self._pbar.setTextVisible(False)
        self._pbar.setStyleSheet("""
            QProgressBar { border: none; border-radius: 5px;
                           background-color: #E0E0E0; }
            QProgressBar::chunk { background-color: #0098C4;
                                  border-radius: 5px; }
        """)
        l1.addWidget(self._pbar, 0, Qt.AlignHCenter)
        lbl_prog = QLabel("Procesando… Por favor no cierres la aplicación.")
        lbl_prog.setAlignment(Qt.AlignCenter)
        lbl_prog.setFont(QFont("Segoe UI", 11))
        lbl_prog.setStyleSheet("color: #555;")
        l1.addWidget(lbl_prog)
        self._estado.addWidget(w1)

        # Estado 2 – error
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setAlignment(Qt.AlignCenter)
        l2.setSpacing(10)
        self._lbl_error = QLabel()
        self._lbl_error.setAlignment(Qt.AlignCenter)
        self._lbl_error.setFont(QFont("Segoe UI", 10))
        self._lbl_error.setStyleSheet("color: #C62828;")
        self._lbl_error.setWordWrap(True)
        l2.addWidget(self._lbl_error)
        btn_retry = QPushButton("↺  Volver a intentar")
        btn_retry.setFixedSize(200, 42)
        btn_retry.setFont(QFont("Segoe UI", 10, QFont.Bold))
        btn_retry.setCursor(Qt.PointingHandCursor)
        btn_retry.setStyleSheet("""
            QPushButton { background-color: #FFEBEE; color: #C62828;
                border: 1.5px solid #C62828; border-radius: 21px; }
            QPushButton:hover { background-color: #FFCDD2; }
        """)
        btn_retry.clicked.connect(self._reiniciar)
        l2.addWidget(btn_retry, 0, Qt.AlignHCenter)
        self._estado.addWidget(w2)

        # Estado 3 – éxito
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        l3.setContentsMargins(0, 0, 0, 0)
        l3.setAlignment(Qt.AlignCenter)
        l3.setSpacing(10)
        self._lbl_ok = QLabel()
        self._lbl_ok.setAlignment(Qt.AlignCenter)
        self._lbl_ok.setFont(QFont("Segoe UI", 11))
        self._lbl_ok.setStyleSheet("color: #2E7D32;")
        self._lbl_ok.setWordWrap(True)
        l3.addWidget(self._lbl_ok)
        btn_nueva = QPushButton("↺  Nuevo intento")
        btn_nueva.setFixedSize(200, 42)
        btn_nueva.setFont(QFont("Segoe UI", 10, QFont.Bold))
        btn_nueva.setCursor(Qt.PointingHandCursor)
        btn_nueva.setStyleSheet("""
            QPushButton { background-color: #E8F5E9; color: #2E7D32;
                border: 1.5px solid #2E7D32; border-radius: 21px; }
            QPushButton:hover { background-color: #C8E6C9; }
        """)
        btn_nueva.clicked.connect(self._reiniciar)
        l3.addWidget(btn_nueva, 0, Qt.AlignHCenter)
        self._estado.addWidget(w3)

        self._estado.setCurrentIndex(0)
        content.addStretch()

    # ── Lógica ───────────────────────────────────────────────────────
    def _validar(self) -> str | None:
        if not self._dz_maestro.tiene_archivo():
            return "Falta el archivo Maestro de lugares."
        if not self._dz_places.tiene_archivo():
            return "Falta el archivo layout_places."
        try:
            wb = openpyxl.load_workbook(
                self._dz_maestro.ruta, read_only=True, data_only=True)
            wb.close()
        except PermissionError:
            return ("El archivo Maestro de lugares está abierto en Excel.\n"
                    "Ciérralo e intenta de nuevo.")
        except Exception:
            return ("No se pudo leer el Maestro de lugares.\n"
                    "Asegúrate de que no esté dañado.")
        return None

    def _comenzar(self):
        error = self._validar()
        if error:
            self._mostrar_error(error)
            return

        self._btn_back.setEnabled(False)
        self._dz_maestro.setEnabled(False)
        self._dz_places.setEnabled(False)
        self._estado.setCurrentIndex(1)

        self._hilo = _ProcesoThread(
            ruta_maestro       = self._dz_maestro.ruta,
            ruta_layout_places = self._dz_places.ruta,
        )
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.error_ocurrido.connect(self._on_error)
        self._hilo.finished.connect(self._on_hilo_finalizado)
        self._hilo.start()

    def _on_terminado(self, carpeta: str):
        self._btn_back.setEnabled(True)
        self._lbl_ok.setText(
            f"✓  Proceso terminado\n"
            f"Archivos guardados en Descargas /\n"
            f"{os.path.basename(carpeta)}"
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
        self._dz_maestro.reset()
        self._dz_places.reset()
        self._btn_back.setEnabled(True)
        self._estado.setCurrentIndex(0)
