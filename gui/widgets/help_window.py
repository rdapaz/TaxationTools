"""
Help window that renders markdown as HTML in a scrollable QDialog.
Supports jumping to specific sections via anchor.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout,
)

from gui.theme import NAVY, BG_MAIN, BORDER, TEXT_PRIMARY, font_heading, font_body


def _markdown_to_html(md_text: str) -> str:
    """Convert markdown to HTML. Uses the `markdown` library if available,
    otherwise does a basic conversion."""
    try:
        import markdown
        return markdown.markdown(
            md_text,
            extensions=['tables', 'fenced_code', 'toc'],
        )
    except ImportError:
        # Basic fallback — handle headers, bold, code blocks, lists, tables
        import re
        html = md_text

        # Code blocks (fenced)
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:#F3F4F6;padding:10px;border-radius:6px;overflow-x:auto;">\2</pre>',
            html, flags=re.DOTALL
        )

        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2 id="\1">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)

        # Inline code
        html = re.sub(r'`(.+?)`', r'<code style="background:#F3F4F6;padding:2px 4px;border-radius:3px;">\1</code>', html)

        # Horizontal rules
        html = re.sub(r'^---$', '<hr>', html, flags=re.MULTILINE)

        # Unordered list items
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)

        # Simple table support
        lines = html.split('\n')
        in_table = False
        result = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                cells = [c.strip() for c in stripped.strip('|').split('|')]
                if all(set(c) <= {'-', ' ', ':'} for c in cells):
                    continue  # separator row
                if not in_table:
                    result.append('<table style="border-collapse:collapse;width:100%;">')
                    in_table = True
                    result.append('<tr>' + ''.join(
                        f'<th style="border:1px solid #ddd;padding:6px;text-align:left;background:#F3F4F6;">{c}</th>'
                        for c in cells) + '</tr>')
                else:
                    result.append('<tr>' + ''.join(
                        f'<td style="border:1px solid #ddd;padding:6px;">{c}</td>'
                        for c in cells) + '</tr>')
            else:
                if in_table:
                    result.append('</table>')
                    in_table = False
                result.append(line)
        if in_table:
            result.append('</table>')
        html = '\n'.join(result)

        # Paragraphs (double newlines)
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'

        return html


_HELP_CSS = f"""
    body {{
        font-family: 'Segoe UI', sans-serif;
        font-size: 10pt;
        color: {TEXT_PRIMARY};
        line-height: 1.6;
        padding: 10px;
    }}
    h1 {{
        color: {NAVY};
        font-size: 18pt;
        border-bottom: 2px solid {BORDER};
        padding-bottom: 8px;
        margin-top: 0;
    }}
    h2 {{
        color: {NAVY};
        font-size: 14pt;
        border-bottom: 1px solid {BORDER};
        padding-bottom: 4px;
        margin-top: 24px;
    }}
    h3 {{
        color: {NAVY};
        font-size: 11pt;
        margin-top: 16px;
    }}
    a {{
        color: #2563EB;
    }}
    code {{
        background: #F3F4F6;
        padding: 2px 4px;
        border-radius: 3px;
        font-family: 'Cascadia Code', 'Consolas', monospace;
        font-size: 9pt;
    }}
    pre {{
        background: #F3F4F6;
        padding: 12px;
        border-radius: 6px;
        overflow-x: auto;
        font-family: 'Cascadia Code', 'Consolas', monospace;
        font-size: 9pt;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
    }}
    th, td {{
        border: 1px solid {BORDER};
        padding: 6px 10px;
        text-align: left;
    }}
    th {{
        background: #F3F4F6;
        font-weight: 600;
    }}
    hr {{
        border: none;
        border-top: 1px solid {BORDER};
        margin: 20px 0;
    }}
    li {{
        margin: 4px 0;
    }}
"""


class HelpWindow(QDialog):
    """Standalone help dialog that renders the markdown help file."""

    _instance = None  # Singleton — only one help window at a time

    def __init__(self, parent=None, section: str = None):
        super().__init__(parent)
        self.setWindowTitle("BudgetBuddy Help")
        self.setMinimumSize(700, 550)
        self.resize(780, 650)
        self.setStyleSheet(f"background: white;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                border: none;
                background: white;
                padding: 16px;
            }}
        """)
        layout.addWidget(self.browser)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 12)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY}; color: white; border: none;
                border-radius: 6px; padding: 6px 24px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: #2B4A8C; }}
        """)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Load content
        self._load_help(section)

    def _load_help(self, section: str = None):
        """Load and render the markdown help file."""
        help_path = Path(__file__).parent.parent / "help.md"

        if not help_path.exists():
            self.browser.setHtml("<h2>Help file not found</h2><p>help.md is missing.</p>")
            return

        md_text = help_path.read_text(encoding="utf-8")
        html_body = _markdown_to_html(md_text)
        full_html = f"<html><head><style>{_HELP_CSS}</style></head><body>{html_body}</body></html>"
        self.browser.setHtml(full_html)

        # Scroll to section if specified
        if section:
            self.browser.scrollToAnchor(section)

    @classmethod
    def show_help(cls, parent=None, section: str = None):
        """Show the help window (singleton pattern)."""
        if cls._instance is not None:
            try:
                cls._instance.close()
            except RuntimeError:
                pass  # Already deleted

        cls._instance = HelpWindow(parent, section)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()

        # Scroll to section after display
        if section:
            cls._instance.browser.scrollToAnchor(section)


def make_help_button(section: str, parent=None) -> QPushButton:
    """Create a small (?) help button that opens the help window at a section.
    Importable by any view."""
    btn = QPushButton("?")
    btn.setFixedSize(24, 24)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip("Help")
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: #E5E7EB; color: {NAVY}; border: none;
            border-radius: 12px; font-size: 10pt; font-weight: 700;
        }}
        QPushButton:hover {{ background-color: #D1D5DB; }}
    """)
    btn.clicked.connect(lambda: HelpWindow.show_help(parent, section))
    return btn
