"""
Vista – Catalogación por formato y lugar
Interfaz funcional: drag & drop, validación, proceso en hilo, salida a Descargas.
"""

import os
import sys
import shutil
import tempfile
from datetime import datetime

import openpyxl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QProgressBar,
    QFileDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QCursor

from ui.components.drop_zone import DropZone


# ── Suprimir prints de los scripts de procesamiento ──────────────────
class _NullIO:
    def write(self, *a): pass
    def flush(self): pass


def _ruta_base_app() -> str:
    """Devuelve la carpeta core/catalogacion/data/ donde viven los xlsx de plantilla."""
    if getattr(sys, "frozen", False):
        raiz = os.path.dirname(sys.executable)
    else:
        # __file__ está en ui/ → subir un nivel para obtener la raíz del proyecto
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(raiz, "core", "catalogacion", "data")


# ── Columna informativa (sin cambios) ────────────────────────────────
def _info_col(titulo: str, contenido: str | None = None) -> QWidget:
    col = QWidget()
    layout = QVBoxLayout(col)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    lbl_titulo = QLabel(titulo)
    lbl_titulo.setFont(QFont("Segoe UI", 13, QFont.Bold))
    lbl_titulo.setStyleSheet("color: #00BCD4;")
    layout.addWidget(lbl_titulo)

    if contenido:
        lbl_body = QLabel(contenido)
        lbl_body.setFont(QFont("Segoe UI", 11))
        lbl_body.setStyleSheet("color: #333;")
        lbl_body.setWordWrap(True)
        layout.addWidget(lbl_body)

    layout.addStretch()
    return col


# ── Hilo de procesamiento ─────────────────────────────────────────────
class _ProcesoThread(QThread):
    terminado      = Signal(str)   # carpeta de salida en Descargas
    error_ocurrido = Signal(str)   # mensaje de error

    def __init__(self, ruta_matriz, ruta_places, ruta_products, ruta_base):
        super().__init__()
        self._ruta_matriz   = ruta_matriz
        self._ruta_places   = ruta_places
        self._ruta_products = ruta_products
        self._ruta_base     = ruta_base

    def run(self):
        _out, _err = sys.stdout, sys.stderr
        sys.stdout = _NullIO()
        sys.stderr = _NullIO()
        tmp_dir = None
        try:
            from core.catalogacion.completa import procesar_matriz
            from core.catalogacion.formato  import catalogacion_solo_por_formato
            from core.catalogacion.tienda   import catalogacion_por_tienda

            tmp_dir = tempfile.mkdtemp(prefix="catalogacion_")
            ext = os.path.splitext(self._ruta_matriz)[1]
            ruta_copia = os.path.join(tmp_dir, f"MATRIZ{ext}")
            shutil.copy2(self._ruta_matriz, ruta_copia)

            if not procesar_matriz(
                    ruta_copia, self._ruta_products,
                    self._ruta_places, self._ruta_base):
                raise RuntimeError(
                    "Fallo al procesar la Matriz de Catalogación.\n"
                    "Revisa que los archivos sean correctos.")

            if not catalogacion_solo_por_formato(
                    ruta_copia, self._ruta_base, tmp_dir):
                raise RuntimeError(
                    "Fallo en la catalogación por formato.\n"
                    "Verifica que layout_format_scope esté en la carpeta de la app.")

            if not catalogacion_por_tienda(
                    ruta_copia, self._ruta_base, tmp_dir):
                raise RuntimeError(
                    "Fallo en la catalogación por tienda.\n"
                    "Verifica que layout_place_scope esté en la carpeta de la app.")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            carpeta_salida = os.path.join(
                os.path.expanduser("~/Downloads"), f"Catalogacion_{ts}")
            os.makedirs(carpeta_salida, exist_ok=True)

            shutil.copy2(ruta_copia, os.path.join(
                carpeta_salida,
                f"Matriz_catalogacion_procesada_{ts}{ext}"))

            for archivo in os.listdir(tmp_dir):
                if archivo == os.path.basename(ruta_copia):
                    continue
                shutil.copy2(os.path.join(tmp_dir, archivo),
                             os.path.join(carpeta_salida, archivo))

            self.terminado.emit(carpeta_salida)

        except BaseException as exc:
            self.error_ocurrido.emit(str(exc))
        finally:
            sys.stdout = _out
            sys.stderr = _err
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Vista principal ───────────────────────────────────────────────────
class VistaCatalogacion(QWidget):
    def __init__(self, back_cb=None, navigate_productos_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._hilo    = None
        self.setStyleSheet("VistaCatalogacion { background-color: #FFFFFF; }")

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
        self._navigate_productos_cb = navigate_productos_cb
        outer.addWidget(self._btn_back, 0, Qt.AlignLeft)
        outer.addSpacing(30)

        content = outer

        # ── Título ──────────────────────────────────────────────────
        lbl_title = QLabel("Catalogación por formato y lugar")
        lbl_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        lbl_title.setStyleSheet("color: #0098C4;")
        content.addWidget(lbl_title)
        content.addSpacing(10)

        # ── Descripción ─────────────────────────────────────────────
        lbl_desc = QLabel(
            "La catalogación es el proceso mensual donde convertimos la información que nos "
            "entrega Electrolit Mx (la Matriz de catalogación) en dos listas limpias que nuestro "
            "sistema entiende:\n"
            "  · Catalogación por Formato: productos que aplican a todo un formato "
            "(todas las tiendas que pertenecen a ese formato).\n"
            "  · Catalogación por Lugar (tienda): productos que aplican únicamente a tiendas "
            "individuales o no cumplen la condición de cobertura por formato."
        )
        lbl_desc.setFont(QFont("Segoe UI", 13))
        lbl_desc.setStyleSheet("color: #333;")
        lbl_desc.setWordWrap(True)
        content.addWidget(lbl_desc)
        content.addSpacing(28)

        # ── Tres columnas informativas ───────────────────────────────
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(30)

        col_ajustes = QWidget()
        lay_aj = QVBoxLayout(col_ajustes)
        lay_aj.setContentsMargins(0, 0, 0, 0)
        lay_aj.setSpacing(6)
        lbl_aj_titulo = QLabel("Ajustes avanzados")
        lbl_aj_titulo.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_aj_titulo.setStyleSheet("color: #00BCD4;")
        lay_aj.addWidget(lbl_aj_titulo)
        lbl_aj_body = QLabel(
            "Cambia parámetros como los productos generales o la competencia. "
            "Por lo general estos campos no cambian, pero si se requiere un ajuste "
            "haz <a href='editar' style='color:#005F8A; text-decoration:underline;'>"
            "clic aquí</a>."
        )
        lbl_aj_body.setFont(QFont("Segoe UI", 11))
        lbl_aj_body.setStyleSheet("color: #333;")
        lbl_aj_body.setWordWrap(True)
        lbl_aj_body.setOpenExternalLinks(False)
        lbl_aj_body.setCursor(Qt.PointingHandCursor)
        if navigate_productos_cb:
            lbl_aj_body.linkActivated.connect(
                lambda _: navigate_productos_cb())
        lay_aj.addWidget(lbl_aj_body)
        lay_aj.addStretch()
        cols_layout.addWidget(col_ajustes)

        cols_layout.addWidget(_info_col(
            "Propósito del proceso",
            "Ayudar a generar el archivo final de layout_format_scope y "
            "layout_place_scope, listo para subirse",
        ))
        cols_layout.addWidget(_info_col(
            "Requerimientos",
            "  · Matriz de catalogación\n  · layout_places\n  · layout_products",
        ))
        content.addLayout(cols_layout)
        content.addSpacing(28)

        # ── Zonas de drop ────────────────────────────────────────────
        drops_layout = QHBoxLayout()
        drops_layout.setSpacing(20)
        self._dz_matriz   = DropZone("Arrastra aquí el archivo\nMatriz de catalogación")
        self._dz_places   = DropZone("Arrastra aquí el archivo\nlayout_places",   patron="layout_places")
        self._dz_products = DropZone("Arrastra aquí el archivo\nlayout_products", patron="layout_products")
        drops_layout.addWidget(self._dz_matriz)
        drops_layout.addWidget(self._dz_places)
        drops_layout.addWidget(self._dz_products)
        content.addLayout(drops_layout)
        content.addSpacing(28)

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
        lbl_prog = QLabel(
            "Procesando… Este proceso puede tomar entre 5 y 10 minutos.\n"
            "Por favor no cierres la aplicación.")
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

    # ── Lógica ───────────────────────────────────────────────────────
    def _validar(self) -> str | None:
        if not self._dz_matriz.tiene_archivo():
            return "Falta el archivo Matriz de catalogación."
        if not self._dz_places.tiene_archivo():
            return "Falta el archivo layout_places."
        if not self._dz_products.tiene_archivo():
            return "Falta el archivo layout_products."
        try:
            wb = openpyxl.load_workbook(
                self._dz_matriz.ruta, read_only=True, data_only=True)
            hojas = wb.sheetnames
            wb.close()
            if "CONFIGURACIÓN DE ANAQUEL" not in hojas:
                return (
                    "El archivo de Matriz no contiene la hoja "
                    "'CONFIGURACIÓN DE ANAQUEL'.\n"
                    "Verifica que sea el archivo correcto.")
        except PermissionError:
            return ("El archivo Matriz está abierto en Excel.\n"
                    "Ciérralo e intenta de nuevo.")
        except Exception:
            return ("No se pudo leer la Matriz.\n"
                    "Asegúrate de que no esté dañado.")
        return None

    def _comenzar(self):
        error = self._validar()
        if error:
            self._mostrar_error(error)
            return

        self._btn_back.setEnabled(False)
        self._dz_matriz.setEnabled(False)
        self._dz_places.setEnabled(False)
        self._dz_products.setEnabled(False)
        self._estado.setCurrentIndex(1)

        self._hilo = _ProcesoThread(
            ruta_matriz   = self._dz_matriz.ruta,
            ruta_places   = self._dz_places.ruta,
            ruta_products = self._dz_products.ruta,
            ruta_base     = _ruta_base_app(),
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
        self._dz_matriz.reset()
        self._dz_places.reset()
        self._dz_products.reset()
        self._btn_back.setEnabled(True)
        self._estado.setCurrentIndex(0)
