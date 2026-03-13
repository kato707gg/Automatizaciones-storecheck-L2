"""
Ventana principal – Automatizaciones más usadas
Contiene MainWindow y CardWidget.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QGraphicsDropShadowEffect, QSizePolicy, QFrame, QStackedWidget,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor, QFont

from ui.vista_catalogacion import VistaCatalogacion
from ui.vista_productos import VistaProductos
from ui.vista_catalogo_lugares import VistaActualizarCatalogoLugares
from ui.vista_dividir_archivo import VistaDividirArchivo


HOVER_BG = "#F8FEFF"
HOVER_BORDER = "#0098C4"
HOVER_SUB_BG = "#0098C4"


# ── Datos de las cards ──────────────────────────────────────────────
CARDS = [
    {
        "titulo": "Catalogación por formato y\nlugar",
        "subtitulo": "Electrolit MX",
        "vista": VistaCatalogacion,
    },
    {
        "titulo": "Actualizar catálogo de lugares",
        "subtitulo": "Electrolit MX",
        "vista": VistaActualizarCatalogoLugares,
    },
    {
        "titulo": "Dividir archivo Excel\nen partes",
        "subtitulo": "Global",
        "vista": VistaDividirArchivo,
    },
    {
        "titulo": "Automatización 4",
        "subtitulo": "Próximamente",
    },
    {
        "titulo": "Automatización 5",
        "subtitulo": "Próximamente",
    },
    {
        "titulo": "Automatización 6",
        "subtitulo": "Próximamente",
    },
]


# ── Widget Card ─────────────────────────────────────────────────────
class CardWidget(QFrame):
    """Tarjeta con efecto hover: pasa de blanca con borde gris a color."""

    def __init__(self, data: dict, navigate_cb=None, parent=None):
        super().__init__(parent)
        self.data = data
        self._navigate_cb = navigate_cb
        self._hovered = False
        self._card_width = 320
        self._card_height = 205

        self.setFrameShape(QFrame.NoFrame)
        self.setFixedSize(self._card_width, self._card_height)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.lbl_titulo = QLabel(data["titulo"])
        self.lbl_titulo.setWordWrap(True)
        self.lbl_titulo.setAlignment(Qt.AlignCenter)
        self.lbl_titulo.setFont(QFont("Segoe UI", 12))
        self.lbl_titulo.setStyleSheet("background: transparent; border: none; color: #333;")
        self.lbl_titulo.setContentsMargins(18, 18, 18, 0)
        self.lbl_titulo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.lbl_titulo)

        self.lbl_sub = QLabel(data["subtitulo"])
        self.lbl_sub.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_sub.setFont(QFont("Segoe UI", 10))
        self.lbl_sub.setFixedHeight(36)
        self.lbl_sub.setContentsMargins(10, 0, 0, 0)
        layout.addWidget(self.lbl_sub)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(self._shadow)

        self._update_internal_sizes()
        self._apply_normal_style()

    def set_card_size(self, width: int, height: int):
        self._card_width = width
        self._card_height = height
        self.setFixedSize(width, height)
        self._update_internal_sizes()
        if self._hovered:
            self._apply_hover_style()
        else:
            self._apply_normal_style()

    def _update_internal_sizes(self):
        titulo_size = max(12, min(18, self._card_width // 22))
        subtitulo_size = max(10, min(13, self._card_width // 30))
        sub_h = max(36, min(50, self._card_height // 4))
        self.lbl_titulo.setFont(QFont("Segoe UI", titulo_size))
        self.lbl_sub.setFont(QFont("Segoe UI", subtitulo_size))
        self.lbl_sub.setFixedHeight(sub_h)

    def _apply_normal_style(self):
        self.setStyleSheet("""
            CardWidget {
                background-color: #FFFFFF;
                border: 1.5px solid #DADADA;
                border-radius: 16px;
            }
            CardWidget QLabel {
                background-color: transparent;
                border: none;
            }
        """)
        self.lbl_sub.setStyleSheet("""
            background-color: transparent;
            border: none;
            color: #999;
            padding-left: 10px;
        """)
        self._shadow.setColor(QColor(0, 0, 0, 35))
        self._shadow.setBlurRadius(20)
        self._shadow.setOffset(0, 4)

    def _apply_hover_style(self):
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {HOVER_BG};
                border: 2.5px solid {HOVER_BORDER};
                border-radius: 16px;
            }}
            CardWidget QLabel {{
                background-color: transparent;
                border: none;
            }}
        """)
        self.lbl_sub.setStyleSheet(f"""
            background-color: {HOVER_SUB_BG};
            border: none;
            border-bottom-left-radius: 13px;
            border-bottom-right-radius: 13px;
            color: #FFFFFF;
            padding-left: 10px;
        """)
        self._shadow.setColor(QColor(0, 0, 0, 60))
        self._shadow.setBlurRadius(28)
        self._shadow.setOffset(0, 6)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.data.get("vista") and self._navigate_cb:
            self._navigate_cb(self.data["vista"])

    def eventFilter(self, obj, event):
        if obj is self:
            if event.type() == QEvent.HoverEnter:
                self._hovered = True
                self._apply_hover_style()
            elif event.type() == QEvent.HoverLeave:
                self._hovered = False
                self._apply_normal_style()
        return super().eventFilter(obj, event)


# ── Ventana Principal ───────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatizaciones")
        self.setMinimumSize(1050, 680)
        self.setStyleSheet("""
            QMainWindow { background-color: #FFFFFF; }
            QWidget#central { background-color: #FFFFFF; }
        """)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background-color: #FFFFFF; }")
        self.setCentralWidget(self._stack)

        # ── Página 0: menú de cards ────────────────────────────────────
        central = QWidget()
        central.setObjectName("central")
        self._stack.addWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 25)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignCenter)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(25, 25, 25, 25)
        self.content_layout.setSpacing(5)
        main_layout.addWidget(self.content, 0, Qt.AlignHCenter | Qt.AlignVCenter)

        self.lbl_title = QLabel("Automatizaciones mas usadas")
        self.lbl_title.setStyleSheet("color: #0098C4;")
        self.content_layout.addWidget(self.lbl_title)
        self.content_layout.addSpacing(2)

        self.lbl_desc = QLabel(
            "Biblioteca de scripts que te ayudarán a realizar las tareas más "
            "complejas y repetitivas de horas a segundos"
        )
        self.lbl_desc.setStyleSheet("color: #444;")
        self.lbl_desc.setWordWrap(True)
        self.content_layout.addWidget(self.lbl_desc)
        self.content_layout.addSpacing(30)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(30)
        self.grid.setVerticalSpacing(42)
        self.grid.setAlignment(Qt.AlignCenter)

        self.cards = []
        for idx, card_data in enumerate(CARDS):
            row, col = idx // 3, idx % 3
            card = CardWidget(card_data, navigate_cb=self._navigate_to)
            self.cards.append(card)
            self.grid.addWidget(card, row, col, Qt.AlignCenter)

        self.content_layout.addLayout(self.grid)
        self._update_responsive_layout()

        # ── Páginas de vistas ─────────────────────────────────────────
        # Página 1
        self._vista_catalogacion = VistaCatalogacion(
            back_cb=self._go_home,
            navigate_productos_cb=self._navigate_to_productos,
        )
        self._stack.addWidget(self._vista_catalogacion)

        # Página 2
        self._vista_productos = VistaProductos(back_cb=self._go_catalogacion)
        self._stack.addWidget(self._vista_productos)

        # Página 3
        self._vista_catalogo_lugares = VistaActualizarCatalogoLugares(
            back_cb=self._go_home,
        )
        self._stack.addWidget(self._vista_catalogo_lugares)

        # Página 4
        self._vista_dividir = VistaDividirArchivo(back_cb=self._go_home)
        self._stack.addWidget(self._vista_dividir)

    # ── Navegación ────────────────────────────────────────────────────
    def _navigate_to(self, vista_class):
        mapping = {
            VistaCatalogacion:              1,
            VistaActualizarCatalogoLugares: 3,
            VistaDividirArchivo:            4,
        }
        idx = mapping.get(vista_class)
        if idx is not None:
            self._stack.setCurrentIndex(idx)

    def _navigate_to_productos(self):
        self._stack.setCurrentIndex(2)

    def _go_home(self):
        self._stack.setCurrentIndex(0)

    def _go_catalogacion(self):
        self._stack.setCurrentIndex(1)

    # ── Responsivo ────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self):
        window_w = self.width()
        side_margin = max(52, min(120, int(window_w * 0.07)))
        usable_w = max(980, window_w - (side_margin * 2))
        self.content.setFixedWidth(usable_w)

        layout_margins = self.content_layout.contentsMargins()
        inner_w = max(860, usable_w - layout_margins.left() - layout_margins.right())

        h_gap = max(24, min(42, int(inner_w * 0.025)))
        v_gap = h_gap + 12
        self.grid.setHorizontalSpacing(h_gap)
        self.grid.setVerticalSpacing(v_gap)

        card_w = int((inner_w - (2 * h_gap)) / 3)
        card_w = max(280, min(410, card_w))
        card_h = int(card_w * 0.64)

        for card in self.cards:
            card.set_card_size(card_w, card_h)

        title_size = max(28, min(42, window_w // 43))
        desc_size = max(16, min(18, window_w // 85))
        self.lbl_title.setFont(QFont("Segoe UI", title_size, QFont.Bold))
        self.lbl_desc.setFont(QFont("Segoe UI", desc_size))


# ── Entry point ─────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
