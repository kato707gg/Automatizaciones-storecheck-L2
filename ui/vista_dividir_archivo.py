"""
Vista – Dividir archivo Excel en partes
Interfaz funcional: drag & drop, límite de filas configurable,
proceso en hilo separado, salida a carpeta en Descargas.
"""

import os
import sys
from datetime import datetime

import openpyxl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QProgressBar,
    QStackedWidget, QLineEdit,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIntValidator

from ui.components.drop_zone import DropZone


# ── Hilo de procesamiento ─────────────────────────────────────────────
class _DividirThread(QThread):
    progreso       = Signal(int, int)   # (parte_actual, total_partes)
    terminado      = Signal(str, int)   # (carpeta_salida, total_partes)
    error_ocurrido = Signal(str)

    def __init__(self, ruta_archivo: str, nombre_hoja: str,
                 max_filas: int, carpeta_salida: str):
        super().__init__()
        self._ruta_archivo   = ruta_archivo
        self._nombre_hoja    = nombre_hoja
        self._max_filas      = max_filas
        self._carpeta_salida = carpeta_salida

    def run(self):
        try:
            from core.dividir_archivo import dividir_archivo

            total = dividir_archivo(
                self._ruta_archivo,
                self._nombre_hoja,
                self._max_filas,
                self._carpeta_salida,
                progreso_cb=lambda a, t: self.progreso.emit(a, t),
            )
            self.terminado.emit(self._carpeta_salida, total)
        except BaseException as exc:
            self.error_ocurrido.emit(str(exc))


# ── Helpers de UI ─────────────────────────────────────────────────────
def _campo(label_text: str, placeholder: str,
           validator=None) -> tuple[QLabel, QLineEdit]:
    lbl = QLabel(label_text)
    lbl.setFont(QFont("Segoe UI", 11))
    lbl.setStyleSheet("color: #333; background: transparent;")

    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFont(QFont("Segoe UI", 11))
    inp.setFixedHeight(38)
    inp.setStyleSheet("""
        QLineEdit {
            border: 1.5px solid #DADADA;
            border-radius: 8px;
            padding: 0 10px;
            background: #FAFAFA;
            color: #222;
        }
        QLineEdit:focus {
            border: 1.5px solid #0098C4;
            background: #F0FBFF;
        }
    """)
    if validator:
        inp.setValidator(validator)
    return lbl, inp


# ── Vista principal ───────────────────────────────────────────────────
class VistaDividirArchivo(QWidget):

    def __init__(self, back_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._hilo    = None
        self.setStyleSheet("VistaDividirArchivo { background-color: #FFFFFF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.setSpacing(0)

        # ── Botón volver ──────────────────────────────────────────────
        self._btn_back = QPushButton("← Volver")
        self._btn_back.setFixedSize(120, 36)
        self._btn_back.setFont(QFont("Segoe UI", 10))
        self._btn_back.setCursor(Qt.PointingHandCursor)
        self._btn_back.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #0098C4;
                border: 1.5px solid #0098C4; border-radius: 18px;
            }
            QPushButton:hover { background-color: #E8F7FC; }
        """)
        if back_cb:
            self._btn_back.clicked.connect(back_cb)
        outer.addWidget(self._btn_back, 0, Qt.AlignLeft)
        outer.addSpacing(30)

        # ── Título ────────────────────────────────────────────────────
        lbl_title = QLabel("Dividir archivo Excel en partes")
        lbl_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        lbl_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(lbl_title)
        outer.addSpacing(10)

        # ── Descripción ───────────────────────────────────────────────
        lbl_desc = QLabel(
            "Esta automatización te ayudara a separar tu archivo Excel en partes con cierta cantidad de filas. Es conveniente para cargas masivas que tienen un limite de registros y tu archivo a subir supera ese limite.")
        lbl_desc.setFont(QFont("Segoe UI", 13))
        lbl_desc.setStyleSheet("color: #333;")
        lbl_desc.setWordWrap(True)
        outer.addWidget(lbl_desc)
        outer.addSpacing(28)

        # ── Requerimientos ────────────────────────────────────────────
        lbl_req_titulo = QLabel("Requerimientos")
        lbl_req_titulo.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_req_titulo.setStyleSheet("color: #0098C4;")
        outer.addWidget(lbl_req_titulo)
        outer.addSpacing(6)

        lbl_req_body = QLabel(
            "  · Nombre exacto de la hoja a dividir\n"
            "  · Límite de filas por parte (default: 25,000)"
        )
        lbl_req_body.setFont(QFont("Segoe UI", 12))
        lbl_req_body.setStyleSheet("color: #333;")
        outer.addWidget(lbl_req_body)
        outer.addSpacing(28)

        # ── Configuración ─────────────────────────────────────────────
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #DBF5FF;
                border-radius: 12px;
            }
        """)
        config_lay = QVBoxLayout(config_frame)
        config_lay.setContentsMargins(20, 16, 20, 16)
        config_lay.setSpacing(14)

        config_header = QHBoxLayout()
        config_header.setContentsMargins(0, 0, 0, 0)
        lbl_config = QLabel("Configuración")
        lbl_config.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_config.setStyleSheet(
            "color: #0098C4; background: transparent; border: none;")
        config_header.addWidget(lbl_config)
        config_header.addStretch()
        self._btn_modificar = QPushButton("Modificar")
        self._btn_modificar.setFixedSize(90, 30)
        self._btn_modificar.setFont(QFont("Segoe UI", 10))
        self._btn_modificar.setCursor(Qt.PointingHandCursor)
        self._btn_modificar.clicked.connect(self._toggle_config)
        config_header.addWidget(self._btn_modificar)
        config_lay.addLayout(config_header)

        row = QHBoxLayout()
        row.setSpacing(30)

        lbl_hoja, self._inp_hoja = _campo("Nombre de hoja", "Lugares")
        self._inp_hoja.setText("Lugares")
        self._inp_hoja.setMaximumWidth(280)

        lbl_filas, self._inp_filas = _campo(
            "Límite de filas por parte", "25000",
            validator=QIntValidator(1, 10_000_000))
        self._inp_filas.setText("25000")
        self._inp_filas.setMaximumWidth(180)

        for lbl, inp in ((lbl_hoja, self._inp_hoja),
                          (lbl_filas, self._inp_filas)):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(lbl)
            col.addWidget(inp)
            row.addLayout(col)

        row.addStretch()
        config_lay.addLayout(row)
        outer.addWidget(config_frame)

        # Bloquear configuración hasta que el usuario pulse Modificar
        self._editando_config = False
        self._set_config_editable(False)
        outer.addSpacing(28)

        # ── DropZone ──────────────────────────────────────────────────
        self._dz = DropZone(
            "Arrastra aquí tu archivo Excel\no haz clic para buscarlo")
        outer.addWidget(self._dz)
        outer.addSpacing(24)

        # ── Estado: 0=idle 1=procesando 2=error 3=éxito ──────────────
        self._estado = QStackedWidget()
        outer.addWidget(self._estado)

        # Estado 0 – botón iniciar
        w0 = QWidget()
        l0 = QVBoxLayout(w0)
        l0.setContentsMargins(0, 0, 0, 0)
        l0.setAlignment(Qt.AlignCenter)
        self._btn_iniciar = QPushButton("Comenzar división")
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
        self._pbar.setRange(0, 1)
        self._pbar.setValue(0)
        self._pbar.setFixedSize(340, 10)
        self._pbar.setTextVisible(False)
        self._pbar.setStyleSheet("""
            QProgressBar { border: none; border-radius: 5px;
                           background-color: #E0E0E0; }
            QProgressBar::chunk { background-color: #0098C4;
                                  border-radius: 5px; }
        """)
        l1.addWidget(self._pbar, 0, Qt.AlignHCenter)
        self._lbl_progreso = QLabel("Procesando…")
        self._lbl_progreso.setAlignment(Qt.AlignCenter)
        self._lbl_progreso.setFont(QFont("Segoe UI", 11))
        self._lbl_progreso.setStyleSheet("color: #555;")
        l1.addWidget(self._lbl_progreso)
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
        outer.addStretch()

    # ── Configuración editable ──────────────────────────────────────
    _STYLE_INP_LOCKED = """
        QLineEdit {
            border: 1.5px solid #DADADA;
            border-radius: 8px;
            padding: 0 10px;
            background: #EEF8FC;
            color: #555;
        }
    """
    _STYLE_INP_ACTIVE = """
        QLineEdit {
            border: 1.5px solid #DADADA;
            border-radius: 8px;
            padding: 0 10px;
            background: #FAFAFA;
            color: #222;
        }
        QLineEdit:focus {
            border: 1.5px solid #0098C4;
            background: #F0FBFF;
        }
    """
    _STYLE_BTN_MODIFICAR = """
        QPushButton {
            background-color: transparent; color: #0098C4;
            border: 1.5px solid #0098C4; border-radius: 15px;
        }
        QPushButton:hover { background-color: #C9EFFD; }
    """
    _STYLE_BTN_GUARDAR = """
        QPushButton {
            background-color: #0098C4; color: #FFFFFF;
            border: none; border-radius: 15px;
        }
        QPushButton:hover { background-color: #007BA3; }
    """

    def _set_config_editable(self, editable: bool):
        self._inp_hoja.setReadOnly(not editable)
        self._inp_filas.setReadOnly(not editable)
        style = self._STYLE_INP_ACTIVE if editable else self._STYLE_INP_LOCKED
        self._inp_hoja.setStyleSheet(style)
        self._inp_filas.setStyleSheet(style)
        if editable:
            self._btn_modificar.setText("Guardar")
            self._btn_modificar.setStyleSheet(self._STYLE_BTN_GUARDAR)
        else:
            self._btn_modificar.setText("Modificar")
            self._btn_modificar.setStyleSheet(self._STYLE_BTN_MODIFICAR)

    def _toggle_config(self):
        self._editando_config = not self._editando_config
        self._set_config_editable(self._editando_config)
        if not self._editando_config:
            # Guardar pulsado: restaurar defaults si los campos quedaron vacíos
            if not self._inp_hoja.text().strip():
                self._inp_hoja.setText("Lugares")
            if not self._inp_filas.text().strip():
                self._inp_filas.setText("25000")

    # ── Lógica ────────────────────────────────────────────────────────
    def _validar(self) -> str | None:
        if not self._dz.tiene_archivo():
            return "Debes seleccionar un archivo Excel."
        hoja = self._inp_hoja.text().strip()
        if not hoja:
            return "El nombre de hoja no puede estar vacío."
        filas_txt = self._inp_filas.text().strip()
        if not filas_txt or not filas_txt.isdigit() or int(filas_txt) < 1:
            return "El límite de filas debe ser un número entero mayor a 0."
        try:
            wb = openpyxl.load_workbook(
                self._dz.ruta, read_only=True, data_only=True)
            wb.close()
        except PermissionError:
            return ("El archivo está abierto en Excel.\n"
                    "Ciérralo e intenta de nuevo.")
        except Exception:
            return "No se pudo leer el archivo. Asegúrate de que no esté dañado."
        return None

    def _comenzar(self):
        # Auto-guardar configuración si el usuario la dejó en modo edición
        if self._editando_config:
            self._toggle_config()

        error = self._validar()
        if error:
            self._lbl_error.setText(f"⚠  {error}")
            self._estado.setCurrentIndex(2)
            return

        max_filas   = int(self._inp_filas.text().strip())
        nombre_hoja = self._inp_hoja.text().strip()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        carpeta_salida = os.path.join(
            os.path.expanduser("~/Downloads"),
            f"Division_Excel_{ts}")
        os.makedirs(carpeta_salida, exist_ok=True)

        self._btn_back.setEnabled(False)
        self._btn_modificar.setEnabled(False)
        self._dz.setEnabled(False)
        self._inp_hoja.setEnabled(False)
        self._inp_filas.setEnabled(False)
        self._pbar.setRange(0, 0)
        self._lbl_progreso.setText("Leyendo archivo…")
        self._estado.setCurrentIndex(1)

        self._hilo = _DividirThread(
            ruta_archivo   = self._dz.ruta,
            nombre_hoja    = nombre_hoja,
            max_filas      = max_filas,
            carpeta_salida = carpeta_salida,
        )
        self._hilo.progreso.connect(self._on_progreso)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.error_ocurrido.connect(self._on_error)
        self._hilo.finished.connect(lambda: setattr(self, "_hilo", None))
        self._hilo.start()

    def _on_progreso(self, actual: int, total: int):
        self._pbar.setRange(0, total)
        self._pbar.setValue(actual)
        self._lbl_progreso.setText(
            f"Guardando parte {actual} de {total}…  "
            f"Por favor no cierres la aplicación.")

    def _on_terminado(self, carpeta: str, total_partes: int):
        self._btn_back.setEnabled(True)
        self._btn_modificar.setEnabled(True)
        self._lbl_ok.setText(
            f"✓  División completada en {total_partes} parte(s)\n"
            f"Archivos guardados en Descargas /\n"
            f"{os.path.basename(carpeta)}"
        )
        self._estado.setCurrentIndex(3)

    def _on_error(self, mensaje: str):
        self._btn_back.setEnabled(True)
        self._btn_modificar.setEnabled(True)
        self._inp_hoja.setEnabled(True)
        self._inp_filas.setEnabled(True)
        self._dz.setEnabled(True)
        self._lbl_error.setText(f"⚠  {mensaje}")
        self._estado.setCurrentIndex(2)

    def _reiniciar(self):
        self._dz.reset()
        self._inp_hoja.setEnabled(True)
        self._inp_filas.setEnabled(True)
        self._estado.setCurrentIndex(0)
