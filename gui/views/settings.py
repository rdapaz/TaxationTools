"""
Settings view — classification engine, API key, model training, data import, categories.
"""

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QProgressBar, QTextEdit, QMessageBox, QSizePolicy,
    QGridLayout, QGroupBox, QRadioButton, QLineEdit, QButtonGroup,
    QComboBox, QSpinBox,
)

from gui.models.database import BudgetDatabase
from gui.models.api_key import (
    load_api_key, save_api_key, delete_api_key, mask_api_key, has_api_key,
)
from gui.workers.classify_worker import ClassifyAPIWorker, ClassifyLocalWorker
from gui.workers.train_worker import TrainWorker
from gui.categories import CATEGORIES, get_groups, get_classification_prompt
from gui.theme import (
    font_heading, font_body, BG_MAIN, BG_CARD, BORDER, NAVY, ACCENT,
    TEXT_SECONDARY, TEXT_PRIMARY, CARD_STYLE, POSITIVE, NEGATIVE, INPUT_STYLE,
)

from gui.widgets.help_window import make_help_button as _help_button

# Settings keys stored in SQLite
ENGINE_KEY = "classify_engine"   # "api" or "local"
ENGINE_API = "api"
ENGINE_LOCAL = "local"


class SettingsView(QWidget):
    """Settings panel with classification engine, import, training, and categories."""

    def __init__(self, db: BudgetDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.worker = None
        self.train_worker = None
        self._last_import_ids: list[int] = []
        self._build_ui()
        self.refresh()

    # ═══════════════════════════════════════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_MAIN}; border: none; }}")

        container = QWidget()
        container.setStyleSheet(f"background: {BG_MAIN};")
        self.main_layout = QVBoxLayout(container)
        self.main_layout.setContentsMargins(24, 20, 24, 20)
        self.main_layout.setSpacing(20)

        # Title
        title = QLabel("Settings")
        title.setFont(font_heading(20))
        title.setStyleSheet(f"color: {NAVY}; background: transparent;")
        self.main_layout.addWidget(title)

        # Build all cards
        self._build_engine_card()
        self._build_import_card()
        self._build_classify_card()
        self._build_training_card()
        self._build_coverage_card()
        self._build_categories_card()

        self.main_layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Classification Engine Card ─────────────────────────────────────────

    def _build_engine_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        card_title = QLabel("Classification Engine")
        card_title.setFont(font_heading(14))
        card_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        title_row.addWidget(card_title)
        title_row.addStretch()
        title_row.addWidget(_help_button("Classification Engine", self))
        layout.addLayout(title_row)

        desc = QLabel(
            "Choose how transactions are classified. The Anthropic API (Claude) is more accurate "
            "but costs money per request. The local model is free and runs offline but needs to be "
            "trained on your data first."
        )
        desc.setFont(font_body(10))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Radio buttons
        self.engine_group = QButtonGroup(self)
        radio_style = f"""
            QRadioButton {{
                color: {TEXT_PRIMARY}; background: transparent; border: none;
                spacing: 8px; padding: 6px 0;
            }}
            QRadioButton::indicator {{ width: 16px; height: 16px; }}
        """

        # API option
        api_row = QHBoxLayout()
        self.radio_api = QRadioButton("Anthropic API (Claude)")
        self.radio_api.setFont(font_body(10))
        self.radio_api.setStyleSheet(radio_style)
        self.engine_group.addButton(self.radio_api)
        api_row.addWidget(self.radio_api)

        self.api_status_label = QLabel()
        self.api_status_label.setFont(font_body(9))
        self.api_status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        api_row.addWidget(self.api_status_label)
        api_row.addStretch()
        layout.addLayout(api_row)

        # API key row
        key_row = QHBoxLayout()
        key_row.setContentsMargins(28, 0, 0, 0)  # Indent under radio

        key_label = QLabel("API Key:")
        key_label.setFont(font_body(10))
        key_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        key_row.addWidget(key_label)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-ant-api03-...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setFixedWidth(350)
        self.api_key_input.setStyleSheet(INPUT_STYLE)
        key_row.addWidget(self.api_key_input)

        self.save_key_btn = QPushButton("Save Key")
        self.save_key_btn.setFixedHeight(32)
        self.save_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_key_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {POSITIVE}; color: white; border: none;
                border-radius: 6px; padding: 4px 14px; font-size: 9pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #16A34A; }}
        """)
        self.save_key_btn.clicked.connect(self._save_api_key)
        key_row.addWidget(self.save_key_btn)

        self.remove_key_btn = QPushButton("Remove")
        self.remove_key_btn.setFixedHeight(32)
        self.remove_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_key_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NEGATIVE}; color: white; border: none;
                border-radius: 6px; padding: 4px 14px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: #DC2626; }}
        """)
        self.remove_key_btn.clicked.connect(self._remove_api_key)
        key_row.addWidget(self.remove_key_btn)

        key_row.addStretch()
        layout.addLayout(key_row)

        self.api_key_status = QLabel()
        self.api_key_status.setFont(font_body(9))
        self.api_key_status.setContentsMargins(28, 0, 0, 0)
        self.api_key_status.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        layout.addWidget(self.api_key_status)

        # Local model option
        local_row = QHBoxLayout()
        self.radio_local = QRadioButton("Local Model (DistilBERT)")
        self.radio_local.setFont(font_body(10))
        self.radio_local.setStyleSheet(radio_style)
        self.engine_group.addButton(self.radio_local)
        local_row.addWidget(self.radio_local)

        self.local_status_label = QLabel()
        self.local_status_label.setFont(font_body(9))
        self.local_status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        local_row.addWidget(self.local_status_label)
        local_row.addStretch()
        layout.addLayout(local_row)

        # Connect radio change to save preference
        self.radio_api.toggled.connect(self._on_engine_changed)

        self.main_layout.addWidget(card)

    # ── Import Card ────────────────────────────────────────────────────────

    def _build_import_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        import_layout = QVBoxLayout(card)
        import_layout.setContentsMargins(20, 16, 20, 16)
        import_layout.setSpacing(12)

        import_title_row = QHBoxLayout()
        import_title = QLabel("Import Transactions")
        import_title.setFont(font_heading(14))
        import_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        import_title_row.addWidget(import_title)
        import_title_row.addStretch()
        import_title_row.addWidget(_help_button("Import Transactions", self))
        import_layout.addLayout(import_title_row)

        import_desc = QLabel(
            "Copy your credit card statement to the clipboard, then click Import. "
            "Transactions are parsed from the standard 6-digit date format "
            "(DDMMYY) used by Australian bank statements."
        )
        import_desc.setFont(font_body(10))
        import_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        import_desc.setWordWrap(True)
        import_layout.addWidget(import_desc)

        btn_row = QHBoxLayout()

        self.import_btn = QPushButton("Import from Clipboard")
        self.import_btn.setFixedHeight(38)
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {POSITIVE}; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-size: 10pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #16A34A; }}
        """)
        self.import_btn.clicked.connect(self._import_clipboard)
        btn_row.addWidget(self.import_btn)

        self.import_classify_btn = QPushButton("Import + Auto-Classify")
        self.import_classify_btn.setFixedHeight(38)
        self.import_classify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_classify_btn.setToolTip("Import and immediately classify using the selected engine")
        self.import_classify_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY}; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-size: 10pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #2B4A8C; }}
        """)
        self.import_classify_btn.clicked.connect(lambda: self._import_clipboard(auto_classify=True))
        btn_row.addWidget(self.import_classify_btn)

        btn_row.addStretch()
        import_layout.addLayout(btn_row)

        self.import_result = QLabel()
        self.import_result.setFont(font_body(10))
        self.import_result.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        self.import_result.setWordWrap(True)
        self.import_result.setVisible(False)
        import_layout.addWidget(self.import_result)

        # Classify Last Import button
        classify_last_row = QHBoxLayout()
        self.classify_last_btn = QPushButton("Classify Last Import")
        self.classify_last_btn.setFixedHeight(34)
        self.classify_last_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.classify_last_btn.setToolTip("Run classification on only the transactions from the last import")
        self.classify_last_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #4E79A7; color: white; border: none;
                border-radius: 8px; padding: 6px 18px; font-size: 10pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #3D6290; }}
            QPushButton:disabled {{ background-color: #9CA3AF; }}
        """)
        self.classify_last_btn.setVisible(False)
        self.classify_last_btn.clicked.connect(self._classify_last_import)
        classify_last_row.addWidget(self.classify_last_btn)
        classify_last_row.addStretch()
        import_layout.addLayout(classify_last_row)

        self.main_layout.addWidget(card)

    # ── Classify Card ──────────────────────────────────────────────────────

    def _build_classify_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        ai_layout = QVBoxLayout(card)
        ai_layout.setContentsMargins(20, 16, 20, 16)
        ai_layout.setSpacing(12)

        ai_title_row = QHBoxLayout()
        ai_title = QLabel("AI Classification")
        ai_title.setFont(font_heading(14))
        ai_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        ai_title_row.addWidget(ai_title)
        ai_title_row.addStretch()
        ai_title_row.addWidget(_help_button("AI Classification", self))
        ai_layout.addLayout(ai_title_row)

        self.ai_status = QLabel()
        self.ai_status.setFont(font_body(10))
        self.ai_status.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        self.ai_status.setWordWrap(True)
        ai_layout.addWidget(self.ai_status)

        self.engine_info_label = QLabel()
        self.engine_info_label.setFont(font_body(9))
        self.engine_info_label.setStyleSheet(f"color: {ACCENT}; background: transparent; border: none; font-weight: 600;")
        ai_layout.addWidget(self.engine_info_label)

        btn_row = QHBoxLayout()

        self.classify_btn = QPushButton("Classify Uncategorised Transactions")
        self.classify_btn.setFixedHeight(38)
        self.classify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.classify_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY}; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-size: 10pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #2B4A8C; }}
            QPushButton:disabled {{ background-color: #9CA3AF; }}
        """)
        self.classify_btn.clicked.connect(self._start_classification)
        btn_row.addWidget(self.classify_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NEGATIVE}; color: white; border: none;
                border-radius: 8px; padding: 8px 16px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: #DC2626; }}
            QPushButton:disabled {{ background-color: #9CA3AF; }}
        """)
        self.stop_btn.clicked.connect(self._stop_classification)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()
        ai_layout.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #E5E7EB; border: none; border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {NAVY}; border-radius: 3px;
            }}
        """)
        self.progress_bar.setVisible(False)
        ai_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel()
        self.progress_label.setFont(font_body(9))
        self.progress_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        self.progress_label.setVisible(False)
        ai_layout.addWidget(self.progress_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(150)
        self.log_box.setFont(font_body(9))
        self.log_box.setStyleSheet(f"""
            QTextEdit {{
                background: #F9FAFB; border: 1px solid {BORDER};
                border-radius: 6px; padding: 8px; color: {TEXT_SECONDARY};
            }}
        """)
        self.log_box.setVisible(False)
        ai_layout.addWidget(self.log_box)

        self.main_layout.addWidget(card)

    # ── Model Training Card ────────────────────────────────────────────────

    def _build_training_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        train_title_row = QHBoxLayout()
        card_title = QLabel("Local Model Training")
        card_title.setFont(font_heading(14))
        card_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        train_title_row.addWidget(card_title)
        train_title_row.addStretch()
        train_title_row.addWidget(_help_button("Local Model Training", self))
        layout.addLayout(train_title_row)

        desc = QLabel(
            "Train a DistilBERT model on your categorised transactions. Once trained, "
            "the local model can classify new transactions instantly without internet or API costs. "
            "Training typically takes 5-15 minutes on CPU."
        )
        desc.setFont(font_body(10))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Training data stats
        self.training_stats_label = QLabel()
        self.training_stats_label.setFont(font_body(10))
        self.training_stats_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        self.training_stats_label.setWordWrap(True)
        layout.addWidget(self.training_stats_label)

        # Model status
        self.model_status_label = QLabel()
        self.model_status_label.setFont(font_body(10))
        self.model_status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        self.model_status_label.setWordWrap(True)
        layout.addWidget(self.model_status_label)

        # Low-sample warnings
        self.low_sample_label = QLabel()
        self.low_sample_label.setFont(font_body(9))
        self.low_sample_label.setStyleSheet(f"color: #D97706; background: transparent; border: none;")
        self.low_sample_label.setWordWrap(True)
        self.low_sample_label.setVisible(False)
        layout.addWidget(self.low_sample_label)

        # Training params row
        params_row = QHBoxLayout()

        epochs_label = QLabel("Epochs:")
        epochs_label.setFont(font_body(10))
        epochs_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        params_row.addWidget(epochs_label)

        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(3, 30)
        self.epochs_spin.setValue(10)
        self.epochs_spin.setFixedWidth(70)
        self.epochs_spin.setStyleSheet(f"""
            QSpinBox {{
                border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
                background: white; color: {TEXT_PRIMARY}; font-size: 10pt;
            }}
        """)
        params_row.addWidget(self.epochs_spin)

        params_row.addSpacing(20)
        params_row.addStretch()
        layout.addLayout(params_row)

        # Buttons
        btn_row = QHBoxLayout()

        self.train_btn = QPushButton("Retrain Model")
        self.train_btn.setFixedHeight(38)
        self.train_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.train_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #7C3AED; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-size: 10pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #6D28D9; }}
            QPushButton:disabled {{ background-color: #9CA3AF; }}
        """)
        self.train_btn.clicked.connect(self._start_training)
        btn_row.addWidget(self.train_btn)

        self.train_stop_btn = QPushButton("Stop Training")
        self.train_stop_btn.setFixedHeight(38)
        self.train_stop_btn.setEnabled(False)
        self.train_stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NEGATIVE}; color: white; border: none;
                border-radius: 8px; padding: 8px 16px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: #DC2626; }}
            QPushButton:disabled {{ background-color: #9CA3AF; }}
        """)
        self.train_stop_btn.clicked.connect(self._stop_training)
        btn_row.addWidget(self.train_stop_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Training progress
        self.train_progress = QProgressBar()
        self.train_progress.setFixedHeight(6)
        self.train_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #E5E7EB; border: none; border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: #7C3AED; border-radius: 3px;
            }}
        """)
        self.train_progress.setVisible(False)
        layout.addWidget(self.train_progress)

        self.train_progress_label = QLabel()
        self.train_progress_label.setFont(font_body(9))
        self.train_progress_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        self.train_progress_label.setVisible(False)
        layout.addWidget(self.train_progress_label)

        self.train_log = QTextEdit()
        self.train_log.setReadOnly(True)
        self.train_log.setMaximumHeight(200)
        self.train_log.setFont(font_body(9))
        self.train_log.setStyleSheet(f"""
            QTextEdit {{
                background: #F9FAFB; border: 1px solid {BORDER};
                border-radius: 6px; padding: 8px; color: {TEXT_SECONDARY};
            }}
        """)
        self.train_log.setVisible(False)
        layout.addWidget(self.train_log)

        self.main_layout.addWidget(card)

    # ── Data Coverage Card ─────────────────────────────────────────────────

    def _build_coverage_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        coverage_layout = QVBoxLayout(card)
        coverage_layout.setContentsMargins(20, 16, 20, 16)
        coverage_layout.setSpacing(12)

        cov_title_row = QHBoxLayout()
        coverage_title = QLabel("Data Coverage")
        coverage_title.setFont(font_heading(14))
        coverage_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        cov_title_row.addWidget(coverage_title)
        cov_title_row.addStretch()
        cov_title_row.addWidget(_help_button("Data Coverage", self))
        coverage_layout.addLayout(cov_title_row)

        coverage_desc = QLabel(
            "Shows transaction counts per month across your data range. "
            "Months with zero transactions may indicate missing statement imports."
        )
        coverage_desc.setFont(font_body(10))
        coverage_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        coverage_desc.setWordWrap(True)
        coverage_layout.addWidget(coverage_desc)

        self.coverage_grid = QVBoxLayout()
        self.coverage_grid.setSpacing(4)
        coverage_layout.addLayout(self.coverage_grid)

        self.main_layout.addWidget(card)

    # ── Categories Card ────────────────────────────────────────────────────

    def _build_categories_card(self):
        cat_card = QFrame()
        cat_card.setObjectName("card")
        cat_card.setStyleSheet(CARD_STYLE)
        cat_layout = QVBoxLayout(cat_card)
        cat_layout.setContentsMargins(20, 16, 20, 16)
        cat_layout.setSpacing(12)

        cat_title = QLabel("Categories")
        cat_title.setFont(font_heading(14))
        cat_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        cat_layout.addWidget(cat_title)

        cat_subtitle = QLabel(f"{len(CATEGORIES)} categories across {len(get_groups())} groups")
        cat_subtitle.setFont(font_body(10))
        cat_subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        cat_layout.addWidget(cat_subtitle)

        grid = QGridLayout()
        grid.setSpacing(6)
        col = 0
        row = 0
        for group_name, cats in get_groups():
            group_lbl = QLabel(group_name)
            group_lbl.setFont(font_body(9))
            group_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 600; background: transparent; border: none; padding-top: 6px;")
            grid.addWidget(group_lbl, row, col * 2, 1, 2)
            row += 1

            for cat in cats:
                dot = QLabel("\u25CF")
                dot.setStyleSheet(f"color: {cat.colour}; font-size: 12px; background: transparent; border: none;")
                dot.setFixedWidth(18)
                grid.addWidget(dot, row, col * 2)

                info = QLabel(f"{cat.display_name}")
                info.setFont(font_body(9))
                tax_badge = " (tax)" if cat.tax_deductible else ""
                info.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
                info.setToolTip(f"{cat.description}{tax_badge}")
                grid.addWidget(info, row, col * 2 + 1)
                row += 1

            if row > 10 and col < 2:
                col += 1
                row = 0

        cat_layout.addLayout(grid)
        self.main_layout.addWidget(cat_card)

    # ═══════════════════════════════════════════════════════════════════════
    #  REFRESH
    # ═══════════════════════════════════════════════════════════════════════

    def refresh(self):
        self._refresh_engine_status()
        self._refresh_classify_status()
        self._refresh_training_status()
        self._refresh_coverage()

    def _refresh_engine_status(self):
        """Update the Classification Engine card with current state."""
        # Which engine is selected?
        engine = self.db.get_setting(ENGINE_KEY, ENGINE_API)

        # Block signals during programmatic update
        self.radio_api.blockSignals(True)
        self.radio_local.blockSignals(True)
        if engine == ENGINE_LOCAL:
            self.radio_local.setChecked(True)
        else:
            self.radio_api.setChecked(True)
        self.radio_api.blockSignals(False)
        self.radio_local.blockSignals(False)

        # API key status
        api_key = load_api_key()
        if api_key:
            self.api_key_input.setText("")
            self.api_key_input.setPlaceholderText(mask_api_key(api_key))
            self.api_key_status.setText(f"Key stored securely in OS credential manager")
            self.api_key_status.setStyleSheet(f"color: {POSITIVE}; background: transparent; border: none;")
            self.api_status_label.setText("API key configured")
            self.api_status_label.setStyleSheet(f"color: {POSITIVE}; background: transparent; border: none;")
            self.remove_key_btn.setVisible(True)
        else:
            self.api_key_input.setText("")
            self.api_key_input.setPlaceholderText("sk-ant-api03-...")
            self.api_key_status.setText("No API key configured — enter your key above to enable API classification")
            self.api_key_status.setStyleSheet(f"color: #D97706; background: transparent; border: none;")
            self.api_status_label.setText("No API key")
            self.api_status_label.setStyleSheet(f"color: #D97706; background: transparent; border: none;")
            self.remove_key_btn.setVisible(False)

        # Local model status
        model_path = Path(self.db.db_path).parent / "models" / "best_model.pt"
        if model_path.exists():
            import os
            from datetime import datetime
            mtime = datetime.fromtimestamp(os.path.getmtime(model_path))
            self.local_status_label.setText(f"Model available (trained {mtime.strftime('%d %b %Y')})")
            self.local_status_label.setStyleSheet(f"color: {POSITIVE}; background: transparent; border: none;")
        else:
            self.local_status_label.setText("No model trained yet")
            self.local_status_label.setStyleSheet(f"color: #D97706; background: transparent; border: none;")

    def _refresh_classify_status(self):
        """Update the AI Classification card."""
        unmigrated = self.db.get_unmigrated_count()
        if unmigrated > 0:
            self.ai_status.setText(
                f"{unmigrated:,} transactions need categorising."
            )
            self.classify_btn.setEnabled(True)
        else:
            self.ai_status.setText("All transactions are categorised. Nice!")
            self.classify_btn.setEnabled(False)

        # Engine info
        engine = self.db.get_setting(ENGINE_KEY, ENGINE_API)
        if engine == ENGINE_LOCAL:
            model_path = Path(self.db.db_path).parent / "models" / "best_model.pt"
            if model_path.exists():
                self.engine_info_label.setText("Using: Local DistilBERT model (free, offline)")
            else:
                self.engine_info_label.setText("Using: Local model selected but no model trained — will fall back to API")
                self.engine_info_label.setStyleSheet(f"color: #D97706; background: transparent; border: none; font-weight: 600;")
        else:
            if has_api_key():
                self.engine_info_label.setText("Using: Anthropic API (Claude)")
            else:
                self.engine_info_label.setText("Using: API selected but no key configured — set up in Classification Engine above")
                self.engine_info_label.setStyleSheet(f"color: #D97706; background: transparent; border: none; font-weight: 600;")

        # Last import button
        if self._last_import_ids:
            still_uncat = len(self.db.get_uncategorised_by_ids(self._last_import_ids))
            if still_uncat > 0:
                self.classify_last_btn.setText(f"Classify Last Import ({still_uncat} uncategorised)")
                self.classify_last_btn.setVisible(True)
                self.classify_last_btn.setEnabled(True)
            else:
                self.classify_last_btn.setVisible(False)
        else:
            self.classify_last_btn.setVisible(False)

    def _refresh_training_status(self):
        """Update the Model Training card with data stats."""
        stats = self.db.get_training_stats()
        total = sum(stats.values())
        n_cats = len(stats)

        if total == 0:
            self.training_stats_label.setText(
                "No categorised transactions yet. Import and classify some data first."
            )
            self.train_btn.setEnabled(False)
        else:
            self.training_stats_label.setText(
                f"Training data: {total:,} categorised transactions across {n_cats} categories"
            )
            self.train_btn.setEnabled(total >= 30)

        # Low sample warnings
        if stats:
            low = [(cat, cnt) for cat, cnt in stats.items() if cnt < 10]
            if low:
                warnings = []
                for cat, cnt in sorted(low, key=lambda x: x[1]):
                    cat_info = CATEGORIES.get(cat)
                    name = cat_info.display_name if cat_info else cat
                    warnings.append(f"{name} ({cnt})")
                self.low_sample_label.setText(
                    f"Low samples (<10): {', '.join(warnings)} — predictions may be unreliable"
                )
                self.low_sample_label.setVisible(True)
            else:
                self.low_sample_label.setVisible(False)
        else:
            self.low_sample_label.setVisible(False)

        # Model file status
        model_path = Path(self.db.db_path).parent / "models" / "best_model.pt"
        if model_path.exists():
            import os
            from datetime import datetime
            mtime = datetime.fromtimestamp(os.path.getmtime(model_path))
            size_mb = os.path.getsize(model_path) / (1024 * 1024)

            # Try to read category count from the saved model
            try:
                import pickle
                label_path = Path(self.db.db_path).parent / "models" / "label_encoder.pkl"
                if label_path.exists():
                    with open(label_path, 'rb') as f:
                        le = pickle.load(f)
                    model_cats = len(le.classes_)
                    cat_match = model_cats == n_cats
                    status = (f"Current model: {model_cats} categories, "
                              f"{size_mb:.0f}MB, trained {mtime.strftime('%d %b %Y %H:%M')}")
                    if not cat_match and n_cats > 0:
                        status += f"\nCategory mismatch: model has {model_cats}, app has {n_cats}. Retraining recommended."
                        self.model_status_label.setStyleSheet(f"color: #D97706; background: transparent; border: none;")
                    else:
                        self.model_status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
                else:
                    status = f"Model file found ({size_mb:.0f}MB), trained {mtime.strftime('%d %b %Y')}"
                    self.model_status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
            except Exception:
                status = f"Model file found ({size_mb:.0f}MB), trained {mtime.strftime('%d %b %Y')}"
                self.model_status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

            self.model_status_label.setText(status)
        else:
            self.model_status_label.setText("No trained model found. Train one below using your categorised data.")
            self.model_status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")

    # ═══════════════════════════════════════════════════════════════════════
    #  ENGINE SELECTION
    # ═══════════════════════════════════════════════════════════════════════

    def _on_engine_changed(self, checked):
        """Save engine preference when radio button changes."""
        if self.radio_api.isChecked():
            self.db.set_setting(ENGINE_KEY, ENGINE_API)
        else:
            self.db.set_setting(ENGINE_KEY, ENGINE_LOCAL)
        self._refresh_classify_status()

    # ═══════════════════════════════════════════════════════════════════════
    #  API KEY MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def _save_api_key(self):
        key = self.api_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Empty Key", "Please enter an API key.")
            return

        if not key.startswith("sk-"):
            reply = QMessageBox.question(
                self, "Unusual Key Format",
                "This doesn't look like an Anthropic API key (should start with 'sk-'). Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if save_api_key(key):
            self.api_key_input.clear()
            self._refresh_engine_status()
            QMessageBox.information(self, "Saved",
                "API key saved securely to your OS credential store.\n\n"
                "This key is stored per-user and is NOT included in the app files, "
                "so it's safe to share this app with others.")
        else:
            QMessageBox.warning(self, "Error",
                "Could not save API key. Check that keyring is working.")

    def _remove_api_key(self):
        reply = QMessageBox.question(
            self, "Remove API Key",
            "Remove the stored API key? You'll need to re-enter it to use API classification.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_api_key()
            self._refresh_engine_status()
            self._refresh_classify_status()

    # ═══════════════════════════════════════════════════════════════════════
    #  CLASSIFICATION
    # ═══════════════════════════════════════════════════════════════════════

    def _get_engine(self) -> str:
        """Return current engine preference, with fallback logic."""
        engine = self.db.get_setting(ENGINE_KEY, ENGINE_API)

        if engine == ENGINE_LOCAL:
            model_path = Path(self.db.db_path).parent / "models" / "best_model.pt"
            if not model_path.exists():
                self.log_box.setVisible(True)
                self.log_box.append("No local model found — falling back to API")
                return ENGINE_API

        if engine == ENGINE_API:
            if not has_api_key():
                # Try local as fallback
                model_path = Path(self.db.db_path).parent / "models" / "best_model.pt"
                if model_path.exists():
                    self.log_box.setVisible(True)
                    self.log_box.append("No API key configured — falling back to local model")
                    return ENGINE_LOCAL
                else:
                    return None  # Neither available

        return engine

    def _start_classification(self, txn_ids: list = None):
        engine = self._get_engine()

        if engine is None:
            QMessageBox.warning(self, "No Engine Available",
                "Neither classification engine is ready:\n\n"
                "- API: No API key configured\n"
                "- Local: No trained model found\n\n"
                "Set up an API key or train a local model first.")
            return

        self.classify_btn.setEnabled(False)
        self.classify_last_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.log_box.setVisible(True)
        self.log_box.clear()

        if engine == ENGINE_LOCAL:
            model_dir = str(Path(self.db.db_path).parent / "models")
            self.worker = ClassifyLocalWorker(
                self.db, model_dir, txn_ids=txn_ids
            )
        else:
            api_key = load_api_key()
            if not api_key:
                QMessageBox.warning(self, "No API Key",
                    "No API key found. Enter your Anthropic API key in the "
                    "Classification Engine section above.")
                self.classify_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                self.progress_bar.setVisible(False)
                self.progress_label.setVisible(False)
                return

            self.worker = ClassifyAPIWorker(
                self.db, api_key, txn_ids=txn_ids
            )

        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_classification(self):
        if self.worker:
            self.worker.stop()

    def _on_progress(self, current, total, desc):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"{current}/{total}: {desc}")

    def _on_log(self, text):
        self.log_box.append(text)

    def _on_finished(self, classified, errors):
        self.classify_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.classify_last_btn.setEnabled(False)
        self.classify_last_btn.setVisible(False)
        self.progress_label.setText(f"Complete: {classified} classified, {errors} errors")
        self.refresh()

    def _classify_last_import(self):
        if not self._last_import_ids:
            return
        self._start_classification(txn_ids=self._last_import_ids)

    # ═══════════════════════════════════════════════════════════════════════
    #  MODEL TRAINING
    # ═══════════════════════════════════════════════════════════════════════

    def _start_training(self):
        stats = self.db.get_training_stats()
        total = sum(stats.values())
        if total < 30:
            QMessageBox.warning(self, "Insufficient Data",
                f"Only {total} categorised transactions found.\n"
                f"Need at least 30 for meaningful training.\n\n"
                f"Classify more transactions first using the API, then retrain.")
            return

        reply = QMessageBox.question(
            self, "Start Training",
            f"Train a new model on {total:,} categorised transactions "
            f"across {len(stats)} categories?\n\n"
            f"This will take 5-15 minutes on CPU and will replace any existing model.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.train_btn.setEnabled(False)
        self.train_stop_btn.setEnabled(True)
        self.train_progress.setVisible(True)
        self.train_progress_label.setVisible(True)
        self.train_log.setVisible(True)
        self.train_log.clear()

        model_dir = str(Path(self.db.db_path).parent / "models")
        self.train_worker = TrainWorker(
            self.db, model_dir,
            epochs=self.epochs_spin.value(),
            batch_size=16,
            learning_rate=2e-5,
        )
        self.train_worker.progress.connect(self._on_train_progress)
        self.train_worker.log.connect(self._on_train_log)
        self.train_worker.finished.connect(self._on_train_finished)
        self.train_worker.start()

    def _stop_training(self):
        if self.train_worker:
            self.train_worker.stop()

    def _on_train_progress(self, epoch, total, status):
        self.train_progress.setMaximum(total)
        self.train_progress.setValue(epoch)
        self.train_progress_label.setText(status)

    def _on_train_log(self, text):
        self.train_log.append(text)

    def _on_train_finished(self, success, summary):
        self.train_btn.setEnabled(True)
        self.train_stop_btn.setEnabled(False)
        self.train_progress_label.setText(summary)

        if success:
            QMessageBox.information(self, "Training Complete", summary)
        else:
            if "Stopped" not in summary:
                QMessageBox.warning(self, "Training Failed", summary)

        self._refresh_engine_status()
        self._refresh_training_status()

    # ═══════════════════════════════════════════════════════════════════════
    #  DATA COVERAGE
    # ═══════════════════════════════════════════════════════════════════════

    def _refresh_coverage(self):
        """Populate the data coverage grid showing transaction counts per month."""
        while self.coverage_grid.count():
            child = self.coverage_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    inner = child.layout().takeAt(0)
                    if inner.widget():
                        inner.widget().deleteLater()

        monthly = self.db.get_monthly_transaction_counts()
        if not monthly:
            lbl = QLabel("No transaction data found")
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
            self.coverage_grid.addWidget(lbl)
            return

        from collections import OrderedDict
        years: dict[str, list] = OrderedDict()
        gaps = []
        for month_str, count in monthly:
            year = month_str[:4]
            years.setdefault(year, []).append((month_str, count))
            if count == 0:
                gaps.append(month_str)

        total_months = len(monthly)
        gap_count = len(gaps)
        if gap_count == 0:
            summary = QLabel(f"Complete coverage: {total_months} months, no gaps detected")
            summary.setStyleSheet(f"color: {POSITIVE}; font-weight: 600; background: transparent; border: none;")
        else:
            summary = QLabel(f"{gap_count} month{'s' if gap_count != 1 else ''} with no transactions — possible missing imports")
            summary.setStyleSheet(f"color: {NEGATIVE}; font-weight: 600; background: transparent; border: none;")
        summary.setFont(font_body(10))
        self.coverage_grid.addWidget(summary)

        for year, months in years.items():
            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 4, 0, 0)
            rl.setSpacing(4)

            year_lbl = QLabel(year)
            year_lbl.setFont(font_body(9))
            year_lbl.setFixedWidth(40)
            year_lbl.setStyleSheet(f"color: {NAVY}; font-weight: 600; background: transparent; border: none;")
            rl.addWidget(year_lbl)

            for month_str, count in months:
                month_num = int(month_str[5:7])
                short_name = ["J","F","M","A","M","J","J","A","S","O","N","D"][month_num - 1]

                cell = QLabel(f"{short_name}\n{count}")
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFixedSize(38, 38)
                cell.setFont(font_body(8))

                if count == 0:
                    cell.setStyleSheet(
                        f"background-color: #FEE2E2; color: {NEGATIVE}; "
                        f"border: 1px solid #FECACA; border-radius: 4px; font-weight: 600;"
                    )
                    cell.setToolTip(f"{month_str}: No transactions — missing import?")
                elif count < 10:
                    cell.setStyleSheet(
                        f"background-color: #FEF3C7; color: #D97706; "
                        f"border: 1px solid #FDE68A; border-radius: 4px;"
                    )
                    cell.setToolTip(f"{month_str}: Only {count} transactions — partial month?")
                else:
                    cell.setStyleSheet(
                        f"background-color: #F0FDF4; color: #16A34A; "
                        f"border: 1px solid #BBF7D0; border-radius: 4px;"
                    )
                    cell.setToolTip(f"{month_str}: {count} transactions")

                rl.addWidget(cell)

            rl.addStretch()
            self.coverage_grid.addWidget(row)

    # ═══════════════════════════════════════════════════════════════════════
    #  CLIPBOARD IMPORT
    # ═══════════════════════════════════════════════════════════════════════

    def _parse_clipboard_text(self, text: str) -> list:
        """Parse credit card statement text into transactions."""
        transactions = []
        lines = text.splitlines()

        date_pattern = re.compile(r'^(\d{6})\s+(.+)')
        ref_pattern = re.compile(r'\d{15,}')

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            match = date_pattern.match(line)
            if match:
                date_str = match.group(1)
                rest = match.group(2).strip()

                amount_match = re.search(r'([\d.]+)$', rest)
                if amount_match:
                    amount = float(Decimal(amount_match.group(1)))
                    desc_and_ref = rest[:amount_match.start()].strip()

                    ref_num = ""
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        ref_match = ref_pattern.search(next_line)
                        if ref_match:
                            ref_num = ref_match.group(0)
                            i += 1

                    formatted_date = f"20{date_str[4:6]}-{date_str[2:4]}-{date_str[0:2]}"

                    transactions.append({
                        'date': formatted_date,
                        'description': desc_and_ref,
                        'reference': ref_num,
                        'amount': amount,
                    })
            i += 1

        return transactions

    def _import_clipboard(self, auto_classify: bool = False):
        """Import transactions from clipboard into the database."""
        try:
            import pyperclip
            text = pyperclip.paste()
        except Exception as e:
            QMessageBox.warning(self, "Clipboard Error",
                                f"Could not read clipboard:\n{e}")
            return

        if not text or not text.strip():
            QMessageBox.information(self, "Empty Clipboard",
                                    "The clipboard is empty. Copy your credit card statement first.")
            return

        transactions = self._parse_clipboard_text(text)
        if not transactions:
            QMessageBox.information(self, "No Transactions Found",
                                    "Could not find any transactions in the clipboard data.\n\n"
                                    "Expected format: DDMMYY followed by description and amount.")
            return

        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        added = 0
        duplicates = 0
        imported_ids = []

        for trans in transactions:
            try:
                cursor.execute(
                    "INSERT INTO transactions (trans_date, description, reference_number, amount) "
                    "VALUES (?, ?, ?, ?)",
                    (trans['date'], trans['description'], trans['reference'], trans['amount'])
                )
                imported_ids.append(cursor.lastrowid)
                added += 1
            except sqlite3.IntegrityError:
                duplicates += 1

        conn.commit()
        conn.close()

        self._last_import_ids = imported_ids

        self.import_result.setVisible(True)
        msg = f"Imported {added} new transaction{'s' if added != 1 else ''}"
        if duplicates:
            msg += f" ({duplicates} duplicate{'s' if duplicates != 1 else ''} skipped)"
        self.import_result.setText(msg)
        self.import_result.setStyleSheet(
            f"color: {POSITIVE if added > 0 else TEXT_SECONDARY}; "
            f"background: transparent; border: none; font-weight: 600;"
        )

        if added > 0 and not auto_classify:
            self.classify_last_btn.setText(f"Classify Last Import ({added} transactions)")
            self.classify_last_btn.setVisible(True)
            self.classify_last_btn.setEnabled(True)
        else:
            self.classify_last_btn.setVisible(False)

        if auto_classify and added > 0:
            self._start_classification(txn_ids=imported_ids)

        self.refresh()
