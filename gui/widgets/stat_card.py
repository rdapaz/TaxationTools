"""
Reusable stat card widget — shows a big number with a label underneath.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from gui.theme import CARD_STYLE, STAT_VALUE_STYLE, STAT_LABEL_STYLE, BORDER


class StatCard(QFrame):
    """A rounded card showing a headline stat and label."""

    def __init__(self, label: str, value: str = "$0", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(CARD_STYLE)
        self.setMinimumHeight(100)
        self.setMinimumWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        self._value_label = QLabel(value)
        self._value_label.setStyleSheet(STAT_VALUE_STYLE)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._text_label = QLabel(label)
        self._text_label.setStyleSheet(STAT_LABEL_STYLE)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()
        layout.addWidget(self._value_label)
        layout.addWidget(self._text_label)
        layout.addStretch()

    def set_value(self, value: str):
        self._value_label.setText(value)

    def set_label(self, text: str):
        self._text_label.setText(text)
