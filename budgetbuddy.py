"""
BudgetBuddy — Personal & household budgeting tool.

Entry point for the PySide6 GUI application.
"""

import sys
import os
from pathlib import Path

# Ensure the project root is on the path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette, QColor

from gui.models.database import BudgetDatabase
from gui.main_window import MainWindow


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("BudgetBuddy")
    app.setOrganizationName("daPaz")

    # Force light colour scheme (prevents Windows dark mode from messing with text)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F5F6FA"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1A1A2E"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F9FAFB"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1A1A2E"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1A1A2E"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1F3864"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9CA3AF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1F3864"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    app.setPalette(palette)

    # Set default font
    app.setFont(QFont("Segoe UI", 10))

    # Global stylesheet for widgets that need special handling
    app.setStyleSheet("""
        QToolTip {
            background-color: #1F3864;
            color: white;
            border: none;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 9pt;
        }
        QScrollBar:vertical {
            background: #F5F6FA;
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #CBD5E1;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #94A3B8;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        /* Calendar popup fix — explicit dark text */
        QCalendarWidget {
            background-color: white;
        }
        QCalendarWidget QAbstractItemView {
            background-color: white;
            color: #1A1A2E;
            selection-background-color: #1F3864;
            selection-color: white;
            font-size: 10pt;
        }
        QCalendarWidget QWidget#qt_calendar_navigationbar {
            background-color: #1F3864;
        }
        QCalendarWidget QToolButton {
            color: white;
            background-color: transparent;
            font-size: 10pt;
            padding: 4px 8px;
        }
        QCalendarWidget QToolButton:hover {
            background-color: rgba(255, 255, 255, 0.15);
            border-radius: 4px;
        }
        QCalendarWidget QSpinBox {
            color: white;
            background-color: transparent;
            font-size: 10pt;
            selection-background-color: #2B4A8C;
            selection-color: white;
        }
        QCalendarWidget QMenu {
            background-color: white;
            color: #1A1A2E;
        }
        QCalendarWidget QMenu::item:selected {
            background-color: #E8EDF5;
            color: #1F3864;
        }
    """)

    # Database path — use existing expenses.db
    db_path = PROJECT_ROOT / "expenses.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Run statement_manager.py first to create the database.")
        sys.exit(1)

    db = BudgetDatabase(db_path)

    # Auto-migrate legacy categories on first run
    migrated = db.migrate_legacy_categories()
    if migrated > 0:
        print(f"Migrated {migrated} transactions to new budget categories")

    unmigrated = db.get_unmigrated_count()
    if unmigrated > 0:
        print(f"Note: {unmigrated} transactions still need manual re-categorisation")

    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
