from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QProgressBar, QPushButton


def create_back_button(
    on_click: Callable | None = None,
    text: str = "← Volver",
) -> QPushButton:
    """Builds a standard back button used across views."""
    button = QPushButton(text)
    button.setFixedSize(120, 36)
    button.setFont(QFont("Segoe UI", 10))
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: transparent;
            color: #0098C4;
            border: 1.5px solid #0098C4;
            border-radius: 18px;
        }
        QPushButton:hover { background-color: #E8F7FC; }
        """
    )
    if on_click:
        button.clicked.connect(on_click)
    return button


def create_primary_action_button(
    text: str,
    on_click: Callable | None = None,
    size: tuple[int, int] = (240, 50),
    font_size: int = 12,
    disabled_bg: str | None = None,
    border_radius: int = 25,
) -> QPushButton:
    """Builds the main rounded CTA button (start/save actions)."""
    button = QPushButton(text)
    button.setFixedSize(*size)
    button.setFont(QFont("Segoe UI", font_size, QFont.Bold))
    button.setCursor(Qt.PointingHandCursor)

    style = (
        f"""
        QPushButton {{
            background-color: #0098C4;
            color: #FFFFFF;
            border: none;
            border-radius: {border_radius}px;
        }}
        QPushButton:hover   {{ background-color: #007BA3; }}
        QPushButton:pressed {{ background-color: #006080; }}
        """
    )
    if disabled_bg:
        style += f"\nQPushButton:disabled {{ background-color: {disabled_bg}; }}\n"

    button.setStyleSheet(style)
    if on_click:
        button.clicked.connect(on_click)
    return button


def create_status_action_button(
    text: str,
    on_click: Callable | None = None,
    tone: str = "error",
    size: tuple[int, int] = (200, 42),
    font_size: int = 10,
    border_radius: int = 21,
) -> QPushButton:
    """Builds status actions like retry/new run in error and success states."""
    colors = {
        "error": {
            "bg": "#FFEBEE",
            "fg": "#C62828",
            "hover": "#FFCDD2",
        },
        "success": {
            "bg": "#E8F5E9",
            "fg": "#2E7D32",
            "hover": "#C8E6C9",
        },
    }
    palette = colors["success"] if tone == "success" else colors["error"]

    button = QPushButton(text)
    button.setFixedSize(*size)
    button.setFont(QFont("Segoe UI", font_size, QFont.Bold))
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {palette['bg']};
            color: {palette['fg']};
            border: 1.5px solid {palette['fg']};
            border-radius: {border_radius}px;
        }}
        QPushButton:hover {{ background-color: {palette['hover']}; }}
        """
    )
    if on_click:
        button.clicked.connect(on_click)
    return button


def create_process_progress_bar(
    size: tuple[int, int] = (340, 10),
    indeterminate: bool = False,
    maximum: int = 1,
    value: int = 0,
) -> QProgressBar:
    """Builds the standard process progress bar used in automation states."""
    bar = QProgressBar()
    if indeterminate:
        bar.setRange(0, 0)
    else:
        bar.setRange(0, maximum)
        bar.setValue(value)

    bar.setFixedSize(*size)
    bar.setTextVisible(False)
    bar.setStyleSheet(
        """
        QProgressBar {
            border: none;
            border-radius: 5px;
            background-color: #E0E0E0;
        }
        QProgressBar::chunk {
            background-color: #0098C4;
            border-radius: 5px;
        }
        """
    )
    return bar