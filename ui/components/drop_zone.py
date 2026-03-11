"""
Componente reutilizable DropZone – drag & drop + clic para abrir diálogo.
Importar con: from ui.components.drop_zone import DropZone
"""

import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor


class DropZone(QFrame):
    """
    Zona interactiva de arrastre/clic para seleccionar un archivo Excel.

    Parámetros
    ----------
    texto   : texto placeholder cuando no hay archivo cargado.
    patron  : subcadena que debe contener el nombre del archivo (opcional).
              Si se omite (None) se acepta cualquier archivo Excel válido.
    """

    archivo_cambiado = Signal(bool)   # True = archivo cargado, False = limpiado

    _IDLE = """
        DropZone { border: 2px dashed #00BCD4; border-radius: 16px;
                   background-color: #FFFFFF; }
    """
    _HOVER = """
        DropZone { border: 2.5px dashed #0098C4; border-radius: 16px;
                   background-color: #F0FBFF; }
    """
    _FILLED = """
        DropZone { border: 2px solid #2E7D32; border-radius: 16px;
                   background-color: #F1F8E9; }
    """
    _ERR = """
        DropZone { border: 2px solid #C62828; border-radius: 16px;
                   background-color: #FFEBEE; }
    """

    def __init__(self, texto: str, patron: str | None = None, parent=None):
        super().__init__(parent)
        self._texto_base = texto
        self._patron = patron
        self._ruta = None

        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._IDLE)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        self._icon = QLabel("📂")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(
            "background: transparent; border: none; font-size: 22px;")
        layout.addWidget(self._icon)

        self._lbl = QLabel(texto)
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setWordWrap(True)
        self._lbl.setFont(QFont("Segoe UI", 10))
        self._lbl.setStyleSheet(
            "color: #999; background: transparent; border: none;")
        layout.addWidget(self._lbl)

        # ── Overlay de acción (hover con archivo cargado) ─────────────
        self._overlay = QFrame(self)
        self._overlay.setStyleSheet("""
            QFrame {
                background-color: #DAEFFE;
                border: 2.5px solid #0098C4;
                border-radius: 14px;
            }
        """)
        self._overlay.hide()

        ovl_lay = QVBoxLayout(self._overlay)
        ovl_lay.setAlignment(Qt.AlignCenter)
        ovl_lay.setSpacing(10)
        ovl_lay.setContentsMargins(20, 20, 20, 20)

        btn_reemplazar = QPushButton("↩  Reemplazar")
        btn_quitar_ovl = QPushButton("×  Quitar archivo")
        for btn in (btn_reemplazar, btn_quitar_ovl):
            btn.setFixedHeight(34)
            btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
        btn_reemplazar.setStyleSheet("""
            QPushButton { background:#E3F2FD; color:#1565C0;
                border:1.5px solid #1565C0; border-radius:7px; padding:0 16px; }
            QPushButton:hover { background:#BBDEFB; }
        """)
        btn_quitar_ovl.setStyleSheet("""
            QPushButton { background:#FFEBEE; color:#C62828;
                border:1.5px solid #C62828; border-radius:7px; padding:0 16px; }
            QPushButton:hover { background:#FFCDD2; }
        """)
        btn_reemplazar.clicked.connect(self._reemplazar)
        btn_quitar_ovl.clicked.connect(self.reset)
        ovl_lay.addWidget(btn_reemplazar)
        ovl_lay.addWidget(btn_quitar_ovl)

    # ── API pública ──────────────────────────────────────────────────
    @property
    def ruta(self):
        return self._ruta

    def tiene_archivo(self) -> bool:
        return self._ruta is not None and os.path.exists(self._ruta)

    def reset(self):
        self._ruta = None
        self._lbl.setText(self._texto_base)
        self._lbl.setStyleSheet(
            "color: #999; background: transparent; border: none;")
        self._icon.setText("📂")
        self.setStyleSheet(self._IDLE)
        self.setEnabled(True)
        self._overlay.hide()
        self.archivo_cambiado.emit(False)

    # ── Lógica interna ────────────────────────────────────────────────
    def _aceptar(self, ruta: str):
        ext = os.path.splitext(ruta)[1].lower()
        if ext not in (".xlsx", ".xlsm", ".xls"):
            self._lbl.setText(f"Formato no válido ({ext or 'sin extensión'})")
            self._lbl.setStyleSheet(
                "color: #C62828; background: transparent; border: none;")
            self.setStyleSheet(self._ERR)
            return
        if self._patron and self._patron.lower() not in os.path.basename(ruta).lower():
            self._lbl.setText(
                f"Nombre incorrecto. Se esperaba un archivo que contenga '{self._patron}'")
            self._lbl.setStyleSheet(
                "color: #C62828; background: transparent; border: none;")
            self.setStyleSheet(self._ERR)
            return
        self._ruta = ruta
        self._lbl.setText(os.path.basename(ruta))
        self._lbl.setStyleSheet(
            "color: #2E7D32; font-weight: bold; "
            "background: transparent; border: none;")
        self._icon.setText("✓")
        self.setStyleSheet(self._FILLED)
        self.archivo_cambiado.emit(True)

    # ── Eventos ───────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        self._overlay.hide()
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()
            if not self.tiene_archivo():
                self.setStyleSheet(self._HOVER)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        if not self.tiene_archivo():
            self.setStyleSheet(self._IDLE)
        super().dragLeaveEvent(event)

    def enterEvent(self, event):
        if self.tiene_archivo():
            self._overlay.setGeometry(0, 0, self.width(), self.height())
            self._overlay.show()
            self._overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self._overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(0, 0, self.width(), self.height())

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._aceptar(urls[0].toLocalFile())
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.tiene_archivo():
            ruta, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar archivo", "",
                "Archivos Excel (*.xlsx *.xlsm *.xls)")
            if ruta:
                self._aceptar(ruta)

    def _reemplazar(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo", "",
            "Archivos Excel (*.xlsx *.xlsm *.xls)")
        if ruta:
            self._overlay.hide()
            self._aceptar(ruta)
