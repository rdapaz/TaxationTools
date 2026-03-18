"""
Theme and styling constants for the budget app.
"""

from PySide6.QtGui import QColor, QFont

# ── Colour tokens ───────────────────────────────────────────────────────────
NAVY         = "#1F3864"
ACCENT       = "#4E79A7"
ACCENT_LIGHT = "#A0CBE8"
BG_CARD      = "#FFFFFF"
BG_MAIN      = "#F5F6FA"
TEXT_PRIMARY  = "#1A1A2E"
TEXT_SECONDARY= "#6B7280"
POSITIVE     = "#22C55E"  # income / under budget
NEGATIVE     = "#EF4444"  # over budget
BORDER       = "#E5E7EB"

# ── Fonts ───────────────────────────────────────────────────────────────────
def font_heading(size: int = 16) -> QFont:
    f = QFont("Segoe UI", size)
    f.setWeight(QFont.Weight.DemiBold)
    return f

def font_body(size: int = 10) -> QFont:
    return QFont("Segoe UI", size)

def font_mono(size: int = 9) -> QFont:
    return QFont("Cascadia Code", size)

# ── Card stylesheet ─────────────────────────────────────────────────────────
# CRITICAL: must set color explicitly so children don't inherit sidebar white
CARD_STYLE = f"""
    QFrame#card {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
"""

STAT_VALUE_STYLE = f"""
    QLabel {{
        color: {NAVY};
        font-size: 28px;
        font-weight: 600;
        font-family: 'Segoe UI';
    }}
"""

STAT_LABEL_STYLE = f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        font-family: 'Segoe UI';
    }}
"""

# ── Reusable widget styles ──────────────────────────────────────────────────
INPUT_STYLE = f"""
    QLineEdit {{
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 10pt;
        background-color: white;
        color: {TEXT_PRIMARY};
    }}
    QLineEdit:focus {{
        border-color: {NAVY};
    }}
"""

COMBO_STYLE = f"""
    QComboBox {{
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 10pt;
        background-color: white;
        color: {TEXT_PRIMARY};
    }}
    QComboBox:focus {{
        border-color: {NAVY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: white;
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        selection-background-color: #E8EDF5;
        selection-color: {NAVY};
        font-size: 10pt;
        padding: 4px;
    }}
"""

DATE_STYLE = f"""
    QDateEdit {{
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 8px;
        background-color: white;
        color: {TEXT_PRIMARY};
        font-size: 10pt;
        min-width: 100px;
    }}
    QDateEdit:focus {{
        border-color: {NAVY};
    }}
    QDateEdit::drop-down {{
        border: none;
        width: 24px;
    }}
"""

TABLE_STYLE = f"""
    QTableView {{
        border: none;
        background-color: white;
        color: {TEXT_PRIMARY};
        alternate-background-color: #F9FAFB;
        selection-background-color: #E8EDF5;
        selection-color: {NAVY};
        font-size: 10pt;
        gridline-color: transparent;
    }}
    QTableView::item {{
        padding: 6px 8px;
        border-bottom: 1px solid #F3F4F6;
        color: {TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: #F9FAFB;
        color: {NAVY};
        font-weight: 600;
        font-size: 10pt;
        padding: 8px;
        border: none;
        border-bottom: 2px solid {BORDER};
    }}
"""
