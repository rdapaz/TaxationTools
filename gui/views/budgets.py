"""
Budgets view — set monthly spending targets per category, see live pie chart.
"""

from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QDoubleSpinBox, QComboBox, QPushButton, QSizePolicy, QGridLayout,
)

from gui.models.database import BudgetDatabase
from gui.categories import CATEGORIES, get_groups, colour_for
from gui.widgets.chart_canvas import ChartCanvas
from gui.widgets.help_window import make_help_button
from gui.theme import (
    font_heading, font_body, BG_MAIN, BG_CARD, BORDER, NAVY,
    TEXT_PRIMARY, TEXT_SECONDARY, CARD_STYLE, POSITIVE, NEGATIVE,
    COMBO_STYLE,
)

import matplotlib.ticker as mticker


class BudgetsView(QWidget):
    """Set and manage monthly budgets per category."""

    def __init__(self, db: BudgetDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self._spinners: dict[str, QDoubleSpinBox] = {}
        self._building = False  # Prevent signal loops during seed
        self._build_ui()
        self.refresh()

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

        # Title row with help button
        title_row = QHBoxLayout()
        title = QLabel("Monthly Budgets")
        title.setFont(font_heading(20))
        title.setStyleSheet(f"color: {NAVY}; background: transparent;")
        title_row.addWidget(title)
        title_row.addWidget(make_help_button("Budgets", self))
        title_row.addStretch()
        self.main_layout.addLayout(title_row)

        # ── Seed bar ──────────────────────────────────────────────────────
        seed_card = QFrame()
        seed_card.setObjectName("card")
        seed_card.setStyleSheet(CARD_STYLE)
        seed_layout = QHBoxLayout(seed_card)
        seed_layout.setContentsMargins(16, 12, 16, 12)
        seed_layout.setSpacing(12)

        seed_desc = QLabel("Pre-fill from historical spending:")
        seed_desc.setFont(font_body(10))
        seed_desc.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        seed_layout.addWidget(seed_desc)

        self.seed_combo = QComboBox()
        self.seed_combo.addItem("Last 3 months average", 3)
        self.seed_combo.addItem("Last 6 months average", 6)
        self.seed_combo.addItem("Last 12 months average", 12)
        self.seed_combo.setMinimumWidth(200)
        self.seed_combo.setStyleSheet(COMBO_STYLE)
        seed_layout.addWidget(self.seed_combo)

        self.seed_btn = QPushButton("Auto-Fill")
        self.seed_btn.setFixedHeight(34)
        self.seed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seed_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #4E79A7;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 10pt;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #3D6290; }}
        """)
        self.seed_btn.clicked.connect(self._seed_from_history)
        seed_layout.addWidget(self.seed_btn)

        self.save_btn = QPushButton("Save All")
        self.save_btn.setFixedHeight(34)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 10pt;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #2B4A8C; }}
        """)
        self.save_btn.clicked.connect(self._save_all)
        seed_layout.addWidget(self.save_btn)

        seed_layout.addStretch()

        # Total budget label
        self.total_label = QLabel("Total: $0")
        self.total_label.setFont(font_heading(13))
        self.total_label.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        seed_layout.addWidget(self.total_label)

        self.main_layout.addWidget(seed_card)

        # ── Main content: budget grid + pie chart ─────────────────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # Left: category budget grid
        grid_card = QFrame()
        grid_card.setObjectName("card")
        grid_card.setStyleSheet(CARD_STYLE)
        grid_outer = QVBoxLayout(grid_card)
        grid_outer.setContentsMargins(16, 12, 16, 12)
        grid_outer.setSpacing(8)

        grid_title = QLabel("Budget per Category")
        grid_title.setFont(font_heading(13))
        grid_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        grid_outer.addWidget(grid_title)

        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.grid.setColumnMinimumWidth(0, 18)   # colour dot
        self.grid.setColumnMinimumWidth(1, 150)  # name
        self.grid.setColumnMinimumWidth(2, 130)  # spinner
        self.grid.setColumnMinimumWidth(3, 80)   # avg label

        # Header row
        for col, text in [(1, "Category"), (2, "Monthly Budget"), (3, "Avg Spend")]:
            h = QLabel(text)
            h.setFont(font_body(9))
            h.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 600; background: transparent; border: none;")
            self.grid.addWidget(h, 0, col)

        row = 1
        for group_name, cats in get_groups():
            if group_name == "Other":
                continue  # Skip uncategorised/other in budget

            # Group header
            group_lbl = QLabel(group_name)
            group_lbl.setFont(font_body(9))
            group_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-weight: 700; background: transparent; "
                f"border: none; padding-top: 8px;"
            )
            self.grid.addWidget(group_lbl, row, 0, 1, 4)
            row += 1

            for cat in cats:
                # Colour dot
                dot = QLabel("\u25CF")
                dot.setStyleSheet(f"color: {cat.colour}; font-size: 14px; background: transparent; border: none;")
                dot.setFixedWidth(18)
                self.grid.addWidget(dot, row, 0)

                # Name
                name = QLabel(cat.display_name)
                name.setFont(font_body(10))
                name.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
                name.setToolTip(cat.description)
                self.grid.addWidget(name, row, 1)

                # Spinner
                spin = QDoubleSpinBox()
                spin.setPrefix("$ ")
                spin.setDecimals(0)
                spin.setRange(0, 99999)
                spin.setSingleStep(50)
                spin.setFixedHeight(30)
                spin.setMinimumWidth(120)
                spin.setStyleSheet(f"""
                    QDoubleSpinBox {{
                        border: 1px solid {BORDER};
                        border-radius: 6px;
                        padding: 4px 8px;
                        font-size: 10pt;
                        background-color: white;
                        color: {TEXT_PRIMARY};
                    }}
                    QDoubleSpinBox:focus {{
                        border-color: {NAVY};
                    }}
                    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                        width: 16px;
                    }}
                """)
                spin.valueChanged.connect(self._on_budget_changed)
                self._spinners[cat.id] = spin
                self.grid.addWidget(spin, row, 2)

                # Average label (filled during refresh)
                avg_lbl = QLabel("—")
                avg_lbl.setFont(font_body(9))
                avg_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
                avg_lbl.setObjectName(f"avg_{cat.id}")
                self.grid.addWidget(avg_lbl, row, 3)

                row += 1

        grid_outer.addLayout(self.grid)
        grid_outer.addStretch()

        # Right: pie chart
        pie_card = QFrame()
        pie_card.setObjectName("card")
        pie_card.setStyleSheet(CARD_STYLE)
        pie_layout = QVBoxLayout(pie_card)
        pie_layout.setContentsMargins(16, 12, 16, 12)

        pie_title = QLabel("Budget Allocation")
        pie_title.setFont(font_heading(13))
        pie_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        pie_layout.addWidget(pie_title)

        self.pie_canvas = ChartCanvas(width=5, height=5)
        self.pie_canvas.setStyleSheet("background: transparent; border: none;")
        pie_layout.addWidget(self.pie_canvas)

        # Budget vs Actual bar chart
        vs_title = QLabel("This Month: Budget vs Actual")
        vs_title.setFont(font_heading(13))
        vs_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none; padding-top: 12px;")
        pie_layout.addWidget(vs_title)
        self.vs_label = vs_title

        self.vs_canvas = ChartCanvas(width=5, height=4)
        self.vs_canvas.setStyleSheet("background: transparent; border: none;")
        pie_layout.addWidget(self.vs_canvas)

        pie_layout.addStretch()

        content_row.addWidget(grid_card, stretch=3)
        content_row.addWidget(pie_card, stretch=2)
        self.main_layout.addLayout(content_row)

        self.main_layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Data ──────────────────────────────────────────────────────────────

    def refresh(self):
        self._building = True

        # Load saved budgets
        budgets = self.db.get_budgets()

        # Load 3-month averages for reference
        avgs = self.db.get_category_averages(3)

        for cat_id, spin in self._spinners.items():
            # Set budget value
            if cat_id in budgets:
                spin.setValue(budgets[cat_id])
            # Set average label
            avg_lbl = self.grid.parentWidget().findChild(QLabel, f"avg_{cat_id}")
            if avg_lbl:
                avg_val = avgs.get(cat_id, 0)
                avg_lbl.setText(f"${avg_val:,.0f}/mo" if avg_val else "—")

        self._building = False
        self._update_totals_and_charts()

    def _seed_from_history(self):
        """Pre-fill budget spinners from historical averages."""
        months = self.seed_combo.currentData()
        avgs = self.db.get_category_averages(months)

        self._building = True
        for cat_id, spin in self._spinners.items():
            if cat_id in avgs:
                # Round to nearest $50 for cleaner numbers
                rounded = round(avgs[cat_id] / 50) * 50
                spin.setValue(max(rounded, 0))
            else:
                spin.setValue(0)
        self._building = False

        self._update_totals_and_charts()

    def _save_all(self):
        """Save all budget values to the database."""
        budgets = {}
        for cat_id, spin in self._spinners.items():
            val = spin.value()
            if val > 0:
                budgets[cat_id] = val
        self.db.set_budgets(budgets)

        # Flash confirmation
        self.save_btn.setText("Saved!")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {POSITIVE};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 10pt;
                font-weight: 600;
            }}
        """)
        # Reset after 1.5s
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._reset_save_btn)

    def _reset_save_btn(self):
        self.save_btn.setText("Save All")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 10pt;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #2B4A8C; }}
        """)

    def _on_budget_changed(self):
        if not self._building:
            self._update_totals_and_charts()

    def _update_totals_and_charts(self):
        """Recalculate total and redraw charts when any spinner changes."""
        # Gather current values
        budgets = {}
        for cat_id, spin in self._spinners.items():
            val = spin.value()
            if val > 0:
                budgets[cat_id] = val

        total = sum(budgets.values())
        self.total_label.setText(f"Total: ${total:,.0f} / month")

        self._draw_pie(budgets)
        self._draw_vs_chart()

    def _draw_pie(self, budgets: dict):
        self.pie_canvas.fig.clear()

        if not budgets:
            ax = self.pie_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Set budgets to see\nallocation breakdown",
                    ha="center", va="center", fontsize=10, color="#999")
            ax.axis("off")
            self.pie_canvas.draw()
            return

        # Sort by value descending
        sorted_items = sorted(budgets.items(), key=lambda x: x[1], reverse=True)
        labels = []
        sizes = []
        colours = []
        for cat_id, amount in sorted_items:
            cat = CATEGORIES.get(cat_id)
            labels.append(cat.display_name if cat else cat_id)
            sizes.append(amount)
            colours.append(colour_for(cat_id))

        ax = self.pie_canvas.fig.add_subplot(111)
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct="%1.0f%%",
            colors=colours, startangle=90,
            pctdistance=0.78,
            wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
        )
        for t in autotexts:
            t.set_fontsize(7)
            t.set_color("white")
            t.set_fontweight("bold")

        ax.legend(
            wedges, [f"{l}  (${s:,.0f})" for l, s in zip(labels, sizes)],
            loc="center left", bbox_to_anchor=(1.05, 0.5),
            fontsize=7, frameon=False,
        )
        self.pie_canvas.fig.subplots_adjust(left=0.02, right=0.55, top=0.95, bottom=0.05)
        self.pie_canvas.draw()

    def _draw_vs_chart(self):
        """Draw budget vs actual horizontal bar chart for the current focus month."""
        self.vs_canvas.fig.clear()

        # Get latest month with data
        _, max_date_str = self.db.get_date_range()
        if not max_date_str:
            ax = self.vs_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=10, color="#999")
            ax.axis("off")
            self.vs_canvas.draw()
            return

        latest = datetime.strptime(max_date_str, "%Y-%m-%d").date()
        month_start = latest.replace(day=1).isoformat()
        if latest.month == 12:
            month_end = latest.replace(year=latest.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = latest.replace(month=latest.month + 1, day=1) - timedelta(days=1)
        month_end = month_end.isoformat()
        month_label = latest.strftime("%B %Y")
        self.vs_label.setText(f"{month_label}: Budget vs Actual")

        data = self.db.get_budget_vs_actual(month_start, month_end)
        if not data:
            ax = self.vs_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Set budgets and save to see\nspending comparison",
                    ha="center", va="center", fontsize=10, color="#999")
            ax.axis("off")
            self.vs_canvas.draw()
            return

        # Only show categories that have a budget
        data = [d for d in data if d["budget"] > 0]
        if not data:
            ax = self.vs_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Save your budgets first",
                    ha="center", va="center", fontsize=10, color="#999")
            ax.axis("off")
            self.vs_canvas.draw()
            return

        # Limit to top 10 by budget
        data = data[:10]

        categories = [d["display_name"] for d in reversed(data)]
        budget_vals = [d["budget"] for d in reversed(data)]
        actual_vals = [d["actual"] for d in reversed(data)]
        colours = [d["colour"] for d in reversed(data)]

        ax = self.vs_canvas.fig.add_subplot(111)
        y = range(len(categories))
        bar_h = 0.35

        # Budget bars (lighter)
        bars_budget = ax.barh([i + bar_h / 2 for i in y], budget_vals, bar_h,
                              color="#E5E7EB", edgecolor="white", label="Budget")
        # Actual bars (coloured, with over-budget highlight)
        bar_colours = []
        for d in reversed(data):
            if d["actual"] > d["budget"]:
                bar_colours.append(NEGATIVE)  # Over budget = red
            else:
                bar_colours.append(d["colour"])

        bars_actual = ax.barh([i - bar_h / 2 for i in y], actual_vals, bar_h,
                              color=bar_colours, edgecolor="white", label="Actual")

        ax.set_yticks(list(y))
        ax.set_yticklabels(categories, fontsize=8)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.tick_params(axis="x", labelsize=7, colors="#6B7280")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.set_axisbelow(True)
        ax.xaxis.grid(True, linestyle="--", alpha=0.3)
        ax.legend(fontsize=7, loc="lower right", frameon=False)

        self.vs_canvas.fig.subplots_adjust(left=0.30, right=0.96, top=0.95, bottom=0.10)
        self.vs_canvas.draw()
