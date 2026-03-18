"""
Main application window with sidebar navigation.
"""

from PySide6.QtCore import Qt, QSize, QSettings, QByteArray
from PySide6.QtGui import QIcon, QFont, QAction, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QSizePolicy, QSpacerItem,
)

from gui.models.database import BudgetDatabase
from gui.views.dashboard import DashboardView
from gui.views.transactions import TransactionsView
from gui.views.reports import ReportsView
from gui.views.settings import SettingsView
from gui.views.budgets import BudgetsView
from gui.theme import NAVY, BG_MAIN, BORDER, font_heading, font_body


class NavButton(QPushButton):
    """Sidebar navigation button."""

    def __init__(self, icon_char: str, text: str, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_char}   {text}")
        self.setCheckable(True)
        self.setFlat(True)
        self.setFont(QFont("Segoe UI", 10))
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 0 16px;
                border: none;
                border-radius: 8px;
                color: #9CA3AF;
                background: transparent;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: white;
            }}
            QPushButton:checked {{
                background: rgba(255, 255, 255, 0.12);
                color: white;
                font-weight: 600;
            }}
        """)


class MainWindow(QMainWindow):
    """Main app window with sidebar + stacked views."""

    def __init__(self, db: BudgetDatabase):
        super().__init__()
        self.db = db

        self.setWindowTitle("BudgetBuddy")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 850)

        self._settings = QSettings("BudgetBuddy", "BudgetBuddy")

        self._build_ui()
        self._setup_shortcuts()
        self._restore_geometry()
        self._select_nav(0)  # Start on dashboard

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {NAVY};
                border-right: 1px solid rgba(255,255,255,0.1);
            }}
        """)

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 20, 12, 20)
        sb_layout.setSpacing(4)

        # App title
        app_title = QLabel("BudgetBuddy")
        app_title.setFont(font_heading(16))
        app_title.setStyleSheet("color: white; background: transparent; border: none; padding-bottom: 20px;")
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(app_title)

        # Nav buttons
        self.nav_buttons: list[NavButton] = []
        nav_items = [
            ("\U0001F4CA", "Dashboard"),      # 📊
            ("\U0001F4CB", "Transactions"),    # 📋
            ("\U0001F4C8", "Reports"),         # 📈
            ("\U0001F3AF", "Budgets"),         # 🎯
            ("\U00002699", "Settings"),        # ⚙
        ]

        for icon, text in nav_items:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked, b=btn: self._on_nav_clicked(b))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        # Migration info
        self.migration_label = QLabel()
        self.migration_label.setFont(font_body(8))
        self.migration_label.setStyleSheet("color: #FFD93D; background: transparent; border: none; padding: 8px;")
        self.migration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.migration_label.setWordWrap(True)
        sb_layout.addWidget(self.migration_label)
        self._update_migration_label()

        root_layout.addWidget(sidebar)

        # ── Content area ────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG_MAIN};")

        # Create views
        self.dashboard_view = DashboardView(self.db)
        self.transactions_view = TransactionsView(self.db)
        self.reports_view = ReportsView(self.db)
        self.settings_view = SettingsView(self.db)
        self.budgets_view = BudgetsView(self.db)

        self.stack.addWidget(self.dashboard_view)     # 0
        self.stack.addWidget(self.transactions_view)   # 1
        self.stack.addWidget(self.reports_view)        # 2
        self.stack.addWidget(self.budgets_view)        # 3
        self.stack.addWidget(self.settings_view)       # 4

        root_layout.addWidget(self.stack, stretch=1)

    def _placeholder(self, title: str, description: str) -> QWidget:
        """Create a placeholder view for unbuilt sections."""
        w = QWidget()
        w.setStyleSheet(f"background: {BG_MAIN};")
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("\U0001F6A7")  # 🚧
        icon.setFont(QFont("Segoe UI", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon)

        lbl = QLabel(title)
        lbl.setFont(font_heading(18))
        lbl.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        desc = QLabel(description)
        desc.setFont(font_body(11))
        desc.setStyleSheet("color: #6B7280; background: transparent; border: none;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        coming = QLabel("Coming soon")
        coming.setFont(font_body(10))
        coming.setStyleSheet("color: #9CA3AF; background: transparent; border: none; padding-top: 12px;")
        coming.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(coming)

        return w

    def _setup_shortcuts(self):
        """Wire up Ctrl+1..5 keyboard shortcuts for navigation."""
        for i in range(5):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            shortcut.activated.connect(lambda idx=i: self._navigate_to(idx))

    def _navigate_to(self, index: int):
        """Navigate to a view by index and refresh it."""
        self._select_nav(index)
        widget = self.stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()
        self._update_migration_label()

    def _update_migration_label(self):
        unmigrated = self.db.get_unmigrated_count()
        if unmigrated > 0:
            self.migration_label.setText(f"{unmigrated:,} transactions\nneed categorising")
            self.migration_label.setVisible(True)
        else:
            self.migration_label.setVisible(False)

    def _select_nav(self, index: int):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def _on_nav_clicked(self, clicked_btn: NavButton):
        idx = self.nav_buttons.index(clicked_btn)
        self._select_nav(idx)

        # Refresh the active view
        widget = self.stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

        # Update sidebar counters
        self._update_migration_label()

    # ── Window geometry persistence ────────────────────────────────────
    def _restore_geometry(self):
        """Restore window size/position from previous session."""
        geometry = self._settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self._settings.value("window/state")
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        """Save window size/position on close."""
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())
        super().closeEvent(event)
