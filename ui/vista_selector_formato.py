"""
Vista - Automatizacion 5
Activa o desactiva formatos desde una lista cargada por Excel o captura manual.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.selector_de_formatos.selector_formato import (
    FormatTarget,
    SelectionSummary,
    WebSelectionSession,
    load_items_from_excel,
    parse_items_from_text,
)
from ui.components.action_buttons import (
    create_back_button,
    create_primary_action_button,
    create_process_progress_bar,
    create_status_action_button,
)
from ui.components.drop_zone import DropZone


TARGET_URL = "https://webapp.storecheck.com/placeClassification/index"


class FormatTableWidget(QTableWidget):
    """Tabla personalizada con atajos de teclado."""
    add_row_requested = Signal()
    remove_row_requested = Signal()
    paste_requested = Signal()
    
    def keyPressEvent(self, event):
        # Enter: agregar fila
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.add_row_requested.emit()
            return
        
        # Backspace: eliminar fila
        if event.key() == Qt.Key_Backspace or event.key() == Qt.Key_Delete:
            self.remove_row_requested.emit()
            return
        
        # Ctrl+V: pegar
        if event.matches(QKeySequence.Paste):
            self.paste_requested.emit()
            return
        
        super().keyPressEvent(event)


class VistaSelectorFormato(QWidget):
    def __init__(self, back_cb=None, parent=None):
        super().__init__(parent)
        self._back_cb = back_cb
        self._items: list[FormatTarget] = []
        self._session: WebSelectionSession | None = None
        self._awaiting_continue = False
        self._running = False
        self._table_sync_locked = False

        self.setStyleSheet("VistaAutomatizacion5 { background-color: #FFFFFF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.setSpacing(0)

        self._btn_back = create_back_button(on_click=self._on_back)
        outer.addWidget(self._btn_back, 0, Qt.AlignLeft)
        outer.addSpacing(20)

        title = QLabel("Agregar/Deseleccionar formatos")
        title.setFont(QFont("Segoe UI", 26, QFont.Bold))
        title.setStyleSheet("color: #0098C4;")
        outer.addWidget(title)
        outer.addSpacing(8)

        desc = QLabel(
            "La automatización nos servirá para seleccionar los formatos deseados y activarlos o desactivarlos, para que las tiendas asociadas bajen o no bajen en el catálogo Recomendado cuando son muchos formatos a seleccionar. "
        )
        desc.setWordWrap(True)
        desc.setFont(QFont("Segoe UI", 11))
        desc.setStyleSheet("color: #333;")
        outer.addWidget(desc)
        outer.addSpacing(8)

        steps_title = QLabel("Pasos a seguir")
        steps_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        steps_title.setStyleSheet("color: #0098C4;")
        outer.addWidget(steps_title)
        outer.addSpacing(4)

        steps = QLabel(
            "1. Carga la lista desde Excel o escribe/pega Canal, Cadena y Formato.\n"
            "2. Comienza proceso para iniciar sesión.\n"
            "3. Dirígete a la pantalla de clasificación de lugares.\n"
            "4. Da clic en Continuar proceso para ejecutar la seleccion."
        )
        steps.setFont(QFont("Segoe UI", 10))
        steps.setStyleSheet("color: #222;")
        outer.addWidget(steps)
        outer.addSpacing(14)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)
        self._toggle_activate = QCheckBox()
        self._toggle_activate.setChecked(True)
        self._toggle_activate.setCursor(Qt.PointingHandCursor)
        self._toggle_activate.setStyleSheet(
            """
            QCheckBox::indicator {
                width: 46px;
                height: 24px;
                border-radius: 12px;
                background: #CFD8DC;
            }
            QCheckBox::indicator:checked {
                background: #15A7DB;
            }
            """
        )
        self._toggle_activate.toggled.connect(self._update_toggle_label)

        self._lbl_toggle_mode = QLabel("Agregar")
        self._lbl_toggle_mode.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._lbl_toggle_mode.setStyleSheet("color: #0098C4;")

        toggle_row.addWidget(self._toggle_activate)
        toggle_row.addWidget(self._lbl_toggle_mode)
        toggle_row.addStretch()
        outer.addLayout(toggle_row)
        outer.addSpacing(14)

        src_row = QHBoxLayout()
        src_row.setSpacing(16)

        self._dz_excel = DropZone("Arrastra aqui el archivo con la lista")
        self._dz_excel.setMinimumHeight(200)
        self._dz_excel.archivo_cambiado.connect(self._sync_source_lock)
        src_row.addWidget(self._dz_excel, 1)

        mid = QLabel("ó")
        mid.setFont(QFont("Segoe UI", 18, QFont.Bold))
        mid.setStyleSheet("color: #2F3A40;")
        src_row.addWidget(mid, 0, Qt.AlignCenter)

        manual_frame = QFrame()
        manual_frame.setStyleSheet(
            "QFrame { background-color: #F8FAFB; border: 1.3px solid #D7DEE3; border-radius: 10px; }"
        )
        manual_layout = QVBoxLayout(manual_frame)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(0)

        self._tbl_formats = FormatTableWidget()
        self._tbl_formats.setColumnCount(3)
        self._tbl_formats.setHorizontalHeaderLabels(["Canal", "Cadena", "Formato"])
        self._tbl_formats.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_formats.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tbl_formats.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_formats.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_formats.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tbl_formats.verticalHeader().setVisible(False)
        self._tbl_formats.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._tbl_formats.setFixedHeight(150)
        self._tbl_formats.setStyleSheet(
            """
            QHeaderView::section {
                background-color: #15A7DB;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 4px;
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 1px solid #15A7DB;
                background-clip: padding;
                margin: 0px;
            }
            QTableWidget {
                border: 1px solid #E0E0E0;
                gridline-color: #EEEEEE;
                font-size: 11px;
                background-color: #FFFFFF;
                border-radius: 8px;
                background-clip: padding;
            }
            QTableWidget::item {
                padding: 4px;
                color: #222222;
                background-color: #FFFFFF;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #BBDEFB;
                color: #000000;
            }
            QTableCornerButton::section {
                background-color: #15A7DB;
            }
            """
        )
        self._tbl_formats.itemChanged.connect(self._on_table_item_changed)
        self._tbl_formats.add_row_requested.connect(self._add_row)
        self._tbl_formats.remove_row_requested.connect(self._remove_row)
        self._tbl_formats.paste_requested.connect(self._paste_list)
        manual_layout.addWidget(self._tbl_formats)
        manual_layout.addSpacing(0)

        table_buttons = QHBoxLayout()
        table_buttons.setContentsMargins(8, 10, 8, 8)
        table_buttons.setSpacing(8)

        self._btn_add_row = QPushButton("+ Agregar fila")
        self._btn_del_row = QPushButton("− Eliminar fila")
        self._btn_paste = QPushButton("Pegar lista")
        for btn in (self._btn_add_row, self._btn_del_row, self._btn_paste):
            btn.setFixedHeight(28)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setCursor(Qt.PointingHandCursor)
        self._btn_add_row.setStyleSheet(
            """
            QPushButton { background:#E3F2FD; color:#1565C0;
                border:1px solid #1565C0; border-radius:5px; padding:0 10px; }
            QPushButton:hover { background:#BBDEFB; }
            """
        )
        self._btn_del_row.setStyleSheet(
            """
            QPushButton { background:#FFEBEE; color:#B71C1C;
                border:1px solid #B71C1C; border-radius:5px; padding:0 10px; }
            QPushButton:hover { background:#FFCDD2; }
            """
        )
        self._btn_paste.setStyleSheet(
            """
            QPushButton { background:#E8F5E9; color:#2E7D32;
                border:1px solid #2E7D32; border-radius:5px; padding:0 10px; }
            QPushButton:hover { background:#C8E6C9; }
            """
        )
        self._btn_add_row.clicked.connect(self._add_row)
        self._btn_del_row.clicked.connect(self._remove_row)
        self._btn_paste.clicked.connect(self._paste_list)
        table_buttons.addWidget(self._btn_add_row)
        table_buttons.addWidget(self._btn_del_row)
        table_buttons.addWidget(self._btn_paste)
        table_buttons.addStretch()
        manual_layout.addLayout(table_buttons)

        src_row.addWidget(manual_frame, 1)
        outer.addLayout(src_row)
        outer.addSpacing(14)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont("Segoe UI", 10))
        self._status.setStyleSheet("color: #2F3A40;")
        outer.addWidget(self._status)
        outer.addSpacing(10)

        self._state = QStackedWidget()

        w_idle = QWidget()
        idle_layout = QVBoxLayout(w_idle)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setAlignment(Qt.AlignCenter)

        self._btn_start = create_primary_action_button(
            "Iniciar sesion",
            on_click=self._start_or_continue,
            size=(300, 52),
            font_size=13,
            border_radius=26,
        )
        idle_layout.addWidget(self._btn_start)
        self._state.addWidget(w_idle)

        w_running = QWidget()
        run_layout = QVBoxLayout(w_running)
        run_layout.setContentsMargins(0, 0, 0, 0)
        run_layout.setAlignment(Qt.AlignCenter)
        run_layout.setSpacing(10)

        self._pbar = create_process_progress_bar(
            size=(360, 11),
            indeterminate=False,
            maximum=100,
            value=0,
        )

        self._lbl_running = QLabel("Ejecutando proceso...")
        self._lbl_running.setFont(QFont("Segoe UI", 11))
        self._lbl_running.setStyleSheet("color: #555;")

        run_layout.addWidget(self._pbar, 0, Qt.AlignHCenter)
        run_layout.addWidget(self._lbl_running, 0, Qt.AlignHCenter)
        self._state.addWidget(w_running)

        w_error = QWidget()
        err_layout = QVBoxLayout(w_error)
        err_layout.setContentsMargins(0, 0, 0, 0)
        err_layout.setAlignment(Qt.AlignCenter)
        err_layout.setSpacing(10)

        self._lbl_error = QLabel("")
        self._lbl_error.setAlignment(Qt.AlignCenter)
        self._lbl_error.setWordWrap(True)
        self._lbl_error.setStyleSheet("color: #C62828;")

        btn_retry = create_status_action_button(
            "↺ Volver a intentar",
            on_click=self._reset_state,
            tone="error",
            size=(210, 40),
            font_size=10,
            border_radius=20,
        )

        err_layout.addWidget(self._lbl_error)
        err_layout.addWidget(btn_retry, 0, Qt.AlignHCenter)
        self._state.addWidget(w_error)

        w_done = QWidget()
        done_layout = QVBoxLayout(w_done)
        done_layout.setContentsMargins(0, 0, 0, 0)
        done_layout.setAlignment(Qt.AlignCenter)
        done_layout.setSpacing(10)

        self._lbl_ok = QLabel("")
        self._lbl_ok.setAlignment(Qt.AlignCenter)
        self._lbl_ok.setWordWrap(True)
        self._lbl_ok.setStyleSheet("color: #2E7D32;")

        btn_new = create_status_action_button(
            "↺ Nueva corrida",
            on_click=self._reset_state,
            tone="success",
            size=(200, 40),
            font_size=10,
            border_radius=20,
        )

        done_layout.addWidget(self._lbl_ok)
        done_layout.addWidget(btn_new, 0, Qt.AlignHCenter)
        self._state.addWidget(w_done)

        self._state.setCurrentIndex(0)
        outer.addWidget(self._state)

    def _update_toggle_label(self, checked: bool):
        mode = "Agregar" if checked else "Deseleccionar"
        self._lbl_toggle_mode.setText(mode)

    def _table_has_data(self) -> bool:
        for row in range(self._tbl_formats.rowCount()):
            item = self._tbl_formats.item(row, 2)
            text = item.text().strip() if item else ""
            if text:
                return True
        return False

    def _collect_table_items(self) -> list[FormatTarget]:
        values: list[FormatTarget] = []
        seen: set[tuple[str, str, str]] = set()
        for row in range(self._tbl_formats.rowCount()):
            channel_item = self._tbl_formats.item(row, 0)
            chain_item = self._tbl_formats.item(row, 1)
            format_item = self._tbl_formats.item(row, 2)

            channel = channel_item.text().strip() if channel_item else ""
            chain = chain_item.text().strip() if chain_item else ""
            format_name = format_item.text().strip() if format_item else ""

            if not format_name:
                continue

            target = FormatTarget(channel_id=channel, chain_id=chain, format_name=format_name)
            key = target.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            values.append(target)
        return values

    def _validate_items(self, items: list[FormatTarget]) -> bool:
        for idx, item in enumerate(items, start=1):
            if not item.channel_id or not item.chain_id or not item.format_name:
                self._show_error(
                    f"Fila {idx} incompleta. Debe incluir Canal, Cadena y Formato."
                )
                return False
        return True

    def _on_table_item_changed(self, _item):
        if self._table_sync_locked:
            return
        self._sync_source_lock()

    def _sync_source_lock(self):
        if self._awaiting_continue or self._running:
            return

        excel_loaded = self._dz_excel.tiene_archivo()
        manual_has_data = self._table_has_data()

        if excel_loaded:
            self._tbl_formats.setEnabled(False)
            self._btn_add_row.setEnabled(False)
            self._btn_del_row.setEnabled(False)
            self._btn_paste.setEnabled(False)
        else:
            self._tbl_formats.setEnabled(True)
            self._btn_add_row.setEnabled(True)
            self._btn_del_row.setEnabled(True)
            self._btn_paste.setEnabled(True)

        if manual_has_data:
            self._dz_excel.setEnabled(False)
        else:
            self._dz_excel.setEnabled(True)

    def _build_items(self) -> list[FormatTarget]:
        excel_items: list[FormatTarget] = []
        if self._dz_excel.tiene_archivo():
            try:
                excel_items = load_items_from_excel(self._dz_excel.ruta)
            except Exception as exc:
                self._show_error(f"No se pudo leer el Excel: {exc}")
                return []

        manual_items = self._collect_table_items()

        if self._dz_excel.tiene_archivo() and manual_items:
            self._show_error("Elige solo un origen de lista: Excel o captura manual.")
            return []

        source_items = excel_items if self._dz_excel.tiene_archivo() else manual_items
        self._items = source_items

        if source_items and not self._validate_items(source_items):
            return []

        if source_items:
            self._state.setCurrentIndex(0)
            self._status.setText("Lista lista para ejecutar.")
        else:
            self._status.setText("Carga un Excel o escribe Canal, Cadena y Formato para continuar.")

        return source_items

    def _start_or_continue(self):
        if self._running:
            return

        if not self._awaiting_continue:
            items = self._build_items()
            if not items:
                self._show_error("No hay formatos para procesar.")
                return

            try:
                self._session = WebSelectionSession(use_profile=False)
                self._session.start(url=TARGET_URL, status_cb=self._status.setText)
            except Exception as exc:
                self._show_error(str(exc))
                self._session = None
                return

            self._awaiting_continue = True
            self._btn_start.setText("Continuar proceso")
            self._toggle_activate.setEnabled(False)
            self._tbl_formats.setEnabled(False)
            self._btn_add_row.setEnabled(False)
            self._btn_del_row.setEnabled(False)
            self._btn_paste.setEnabled(False)
            self._dz_excel.setEnabled(False)
            self._status.setText(
                "Chrome abierto. Inicia sesion, navega a la seccion objetivo y luego presiona Continuar proceso."
            )
            return

        if self._session is None:
            self._show_error("No hay sesion activa de Chrome.")
            return

        self._running = True
        self._btn_start.setEnabled(False)
        self._state.setCurrentIndex(1)
        self._pbar.setRange(0, max(len(self._items), 1))
        self._pbar.setValue(0)

        target_button = "Agregar" if self._toggle_activate.isChecked() else "Deseleccionar"

        try:
            summary = self._session.run_selection(
                items=self._items,
                target_button=target_button,
                progress_cb=self._on_progress,
                status_cb=self._status.setText,
                output_dir="docs/runs",
            )
            self._show_success(summary)
        except Exception as exc:
            self._show_error(str(exc))
        finally:
            self._running = False
            self._awaiting_continue = False
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Iniciar sesion")
            self._toggle_activate.setEnabled(True)
            self._sync_source_lock()
            if self._session is not None:
                self._session.close()
                self._session = None

    def _on_progress(self, current: int, total: int, item: str):
        self._pbar.setRange(0, max(total, 1))
        self._pbar.setValue(current)
        self._lbl_running.setText(f"Procesando: {item}")
        QApplication.processEvents()

    def _show_success(self, summary: SelectionSummary):
        self._lbl_ok.setText(
            "Proceso terminado.\n"
            f"Exitosos: {len(summary.success)} | Ignorados: {len(summary.ignored)} | Fallidos: {len(summary.failed)}"
        )
        self._status.setText("")
        self._state.setCurrentIndex(3)

    def _show_error(self, message: str):
        self._lbl_error.setText(f"⚠ {message}")
        self._status.setText(message)
        self._state.setCurrentIndex(2)

    def _reset_state(self):
        if self._session is not None:
            self._session.close()
            self._session = None

        self._awaiting_continue = False
        self._running = False
        self._btn_start.setText("Iniciar sesion")
        self._btn_start.setEnabled(True)
        self._toggle_activate.setEnabled(True)
        self._status.setText("")
        self._state.setCurrentIndex(0)
        self._sync_source_lock()

    def _add_row(self):
        from PySide6.QtGui import QColor
        row = self._tbl_formats.rowCount()
        self._table_sync_locked = True
        self._tbl_formats.insertRow(row)
        for col in range(3):
            item = QTableWidgetItem("")
            item.setForeground(QColor("#222222"))
            self._tbl_formats.setItem(row, col, item)
        self._table_sync_locked = False
        self._tbl_formats.setCurrentCell(row, 0)
        self._tbl_formats.editItem(self._tbl_formats.item(row, 0))
        self._sync_source_lock()

    def _remove_row(self):
        rows = sorted({idx.row() for idx in self._tbl_formats.selectedIndexes()}, reverse=True)
        if not rows and self._tbl_formats.rowCount() > 0:
            rows = [self._tbl_formats.rowCount() - 1]

        self._table_sync_locked = True
        for row in rows:
            self._tbl_formats.removeRow(row)
        self._table_sync_locked = False
        self._sync_source_lock()

    def _paste_list(self):
        from PySide6.QtGui import QColor
        text = QApplication.clipboard().text()
        values = parse_items_from_text(text)
        if not values:
            self._status.setText("No hay filas validas en portapapeles. Usa: Canal;Cadena;Formato")
            return

        self._table_sync_locked = True
        self._tbl_formats.setRowCount(0)
        for value in values:
            row = self._tbl_formats.rowCount()
            self._tbl_formats.insertRow(row)
            row_values = [value.channel_id, value.chain_id, value.format_name]
            for col, col_value in enumerate(row_values):
                item = QTableWidgetItem(col_value)
                item.setForeground(QColor("#222222"))
                self._tbl_formats.setItem(row, col, item)
        self._table_sync_locked = False
        self._status.setText(f"Se cargaron {len(values)} filas desde el portapapeles.")
        self._sync_source_lock()

    def _on_back(self):
        if self._session is not None:
            self._session.close()
            self._session = None
        if self._back_cb:
            self._back_cb()
