"""
Dashboard view — the main landing page showing key spending stats and charts.
"""

from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QProgressBar, QComboBox,
)

from gui.models.database import BudgetDatabase, CategoryTotal
from gui.widgets.stat_card import StatCard
from gui.widgets.chart_canvas import ChartCanvas
from gui.categories import CATEGORIES, colour_for
from gui.widgets.help_window import make_help_button
from gui.theme import (
    font_heading, font_body, BG_MAIN, BG_CARD, BORDER, NAVY,
    TEXT_PRIMARY, TEXT_SECONDARY, CARD_STYLE, POSITIVE, NEGATIVE,
    COMBO_STYLE,
)

import matplotlib.ticker as mticker


class DashboardView(QWidget):
    """Overview dashboard with stat cards, pie chart, and monthly bar chart."""

    def __init__(self, db: BudgetDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Scrollable container
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_MAIN}; border: none; }}")

        container = QWidget()
        container.setStyleSheet(f"background: {BG_MAIN};")
        self.main_layout = QVBoxLayout(container)
        self.main_layout.setContentsMargins(24, 20, 24, 20)
        self.main_layout.setSpacing(20)

        # ── Title row with month picker ────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(16)

        title = QLabel("Dashboard")
        title.setFont(font_heading(20))
        title.setStyleSheet(f"color: {NAVY}; background: transparent;")
        title_row.addWidget(title)

        title_row.addWidget(make_help_button("Dashboard", self))
        title_row.addStretch()

        month_lbl = QLabel("Viewing:")
        month_lbl.setFont(font_body(10))
        month_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        title_row.addWidget(month_lbl)

        self.month_combo = QComboBox()
        self.month_combo.setMinimumWidth(180)
        self.month_combo.setStyleSheet(COMBO_STYLE)
        self.month_combo.currentIndexChanged.connect(self._on_month_changed)
        title_row.addWidget(self.month_combo)

        self.main_layout.addLayout(title_row)

        # ── Stat cards row ──────────────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        self.card_total_month = StatCard("This Month")  # label updated dynamically
        self.card_avg_month   = StatCard("Monthly Average")
        self.card_total_year  = StatCard("Last 12 Months")
        self.card_budget      = StatCard("Budget")
        self.card_txn_count   = StatCard("Transactions")

        for card in (self.card_total_month, self.card_avg_month,
                     self.card_total_year, self.card_budget, self.card_txn_count):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            stats_row.addWidget(card)

        self.main_layout.addLayout(stats_row)

        # ── Charts row ─────────────────────────────────────────────────
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        # Pie chart card
        pie_card = QFrame()
        pie_card.setObjectName("card")
        pie_card.setStyleSheet(CARD_STYLE)
        pie_layout = QVBoxLayout(pie_card)
        pie_layout.setContentsMargins(16, 12, 16, 12)
        pie_title = QLabel("Spending by Category")
        pie_title.setFont(font_heading(13))
        pie_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        pie_layout.addWidget(pie_title)
        self.pie_canvas = ChartCanvas(width=5, height=4)
        self.pie_canvas.setStyleSheet("background: transparent; border: none;")
        pie_layout.addWidget(self.pie_canvas)

        # Bar chart card
        bar_card = QFrame()
        bar_card.setObjectName("card")
        bar_card.setStyleSheet(CARD_STYLE)
        bar_layout = QVBoxLayout(bar_card)
        bar_layout.setContentsMargins(16, 12, 16, 12)
        bar_title = QLabel("Monthly Spending (Last 12 Months)")
        bar_title.setFont(font_heading(13))
        bar_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        bar_layout.addWidget(bar_title)
        self.bar_canvas = ChartCanvas(width=6, height=4)
        self.bar_canvas.setStyleSheet("background: transparent; border: none;")
        bar_layout.addWidget(self.bar_canvas)

        charts_row.addWidget(pie_card, stretch=2)
        charts_row.addWidget(bar_card, stretch=3)
        self.main_layout.addLayout(charts_row)

        # ── Top categories table ────────────────────────────────────────
        top_card = QFrame()
        top_card.setObjectName("card")
        top_card.setStyleSheet(CARD_STYLE)
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(16, 12, 16, 12)
        self.top_title = QLabel("Top Categories This Month")
        self.top_title.setFont(font_heading(13))
        self.top_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        top_layout.addWidget(self.top_title)
        self.top_categories_layout = QVBoxLayout()
        self.top_categories_layout.setSpacing(6)
        top_layout.addLayout(self.top_categories_layout)
        self.main_layout.addWidget(top_card)

        self.main_layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Data refresh ────────────────────────────────────────────────────

    def refresh(self):
        """Repopulate the month combo and refresh all data."""
        # Get all months (including gaps with 0 count)
        all_months = self.db.get_monthly_transaction_counts()

        if not all_months:
            return

        # Block signals while repopulating combo
        self.month_combo.blockSignals(True)
        prev_selection = self.month_combo.currentData()
        self.month_combo.clear()

        # Show newest first — continuous timeline so the user sees gaps
        default_idx = 0
        for i, (month_str, count) in enumerate(reversed(all_months)):
            d = datetime.strptime(month_str + "-01", "%Y-%m-%d").date()
            label = d.strftime("%B %Y")
            if count == 0:
                self.month_combo.addItem(f"{label}  — no data", month_str)
            else:
                self.month_combo.addItem(f"{label}  ({count} txns)", month_str)

        # Find the best default: latest month with >= 50 txns (a full month)
        if prev_selection:
            idx = self.month_combo.findData(prev_selection)
            if idx >= 0:
                default_idx = idx
        else:
            # First load — find the first (newest) month with meaningful data
            for i, (month_str, count) in enumerate(reversed(all_months)):
                if count >= 50:
                    default_idx = i
                    break

        self.month_combo.setCurrentIndex(default_idx)
        self.month_combo.blockSignals(False)
        self._refresh_data()

    def _on_month_changed(self):
        self._refresh_data()

    def _refresh_data(self):
        """Refresh all dashboard data for the currently selected month."""
        month_str = self.month_combo.currentData()
        if not month_str:
            return

        focus = datetime.strptime(month_str + "-01", "%Y-%m-%d").date()
        month_start = focus.isoformat()
        if focus.month == 12:
            month_end = focus.replace(year=focus.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = focus.replace(month=focus.month + 1, day=1) - timedelta(days=1)
        month_end = month_end.isoformat()

        year_start = (focus - timedelta(days=365)).isoformat()
        month_label = focus.strftime("%B %Y")

        # Update card labels
        self.card_total_month.set_label(month_label)

        # Stats
        month_total = self.db.get_total_spending(month_start, month_end)
        year_total = self.db.get_total_spending(year_start, month_end)
        txn_count = self.db.get_transaction_count()

        monthly_summaries = self.db.get_monthly_totals(12)
        avg_monthly = year_total / max(len(monthly_summaries), 1)

        self.card_total_month.set_value(f"${month_total:,.0f}")
        self.card_avg_month.set_value(f"${avg_monthly:,.0f}")
        self.card_total_year.set_value(f"${year_total:,.0f}")
        self.card_txn_count.set_value(f"{txn_count:,}")

        # Budget card
        total_budget = self.db.get_total_budget()
        if total_budget > 0:
            pct_used = (month_total / total_budget * 100) if total_budget else 0
            self.card_budget.set_value(f"{pct_used:.0f}%")
            self.card_budget.set_label(f"of ${total_budget:,.0f} budget")
        else:
            self.card_budget.set_value("—")
            self.card_budget.set_label("No budget set")

        # Pie chart — focus month
        cat_totals = self.db.get_category_totals(month_start, month_end)
        budgets = self.db.get_budgets()
        self._draw_pie(cat_totals)

        # Bar chart — monthly (highlight the selected month)
        self._draw_monthly_bars(monthly_summaries, highlight_month=month_str)

        # Top categories with budget bars
        self._draw_top_categories(cat_totals, month_label, budgets)

    def _draw_pie(self, cat_totals: list):
        self.pie_canvas.fig.clear()

        if not cat_totals:
            ax = self.pie_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No data for this period", ha="center", va="center",
                    fontsize=12, color="#999")
            ax.axis("off")
            self.pie_canvas.draw()
            return

        # Combine small slices into "Other"
        threshold = 0.03
        total = sum(c.total for c in cat_totals)
        main, other_total = [], 0.0
        for c in cat_totals:
            if c.total / total >= threshold:
                main.append(c)
            else:
                other_total += c.total
        if other_total > 0:
            main.append(CategoryTotal("other_combined", "Other", other_total, 0, "#BDBDBD"))

        labels = [c.display_name for c in main]
        sizes = [c.total for c in main]
        colours = [c.colour for c in main]

        ax = self.pie_canvas.fig.add_subplot(111)
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct="%1.0f%%",
            colors=colours, startangle=90,
            pctdistance=0.8,
            wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
        )
        for t in autotexts:
            t.set_fontsize(8)
            t.set_color("white")
            t.set_fontweight("bold")

        ax.legend(
            wedges, [f"{l}  (${s:,.0f})" for l, s in zip(labels, sizes)],
            loc="center left", bbox_to_anchor=(1.05, 0.5),
            fontsize=8, frameon=False,
        )
        self.pie_canvas.fig.subplots_adjust(left=0.02, right=0.60, top=0.95, bottom=0.05)
        self.pie_canvas.draw()

    def _draw_monthly_bars(self, summaries: list, highlight_month: str = None):
        self.bar_canvas.fig.clear()

        if not summaries:
            ax = self.bar_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="#999")
            ax.axis("off")
            self.bar_canvas.draw()
            return

        # Reverse so oldest is on the left
        summaries = list(reversed(summaries))
        month_keys = [s.month for s in summaries]
        months = [s.month[5:] + "\n" + s.month[:4] for s in summaries]
        totals = [s.total for s in summaries]

        ax = self.bar_canvas.fig.add_subplot(111)
        bars = ax.bar(months, totals, color="#4E79A7", width=0.6, edgecolor="white", linewidth=0.5)

        # Highlight the selected month
        if highlight_month and highlight_month in month_keys:
            idx = month_keys.index(highlight_month)
            bars[idx].set_color("#1F3864")

        ax.set_ylabel("Spending ($)", fontsize=9, color="#6B7280")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.tick_params(axis="both", labelsize=8, colors="#6B7280")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, linestyle="--", alpha=0.3)

        # Average line
        avg = sum(totals) / len(totals)
        ax.axhline(y=avg, color="#EF4444", linewidth=1, linestyle="--", alpha=0.7)
        ax.text(len(months) - 0.5, avg, f"  Avg ${avg:,.0f}", fontsize=7,
                color="#EF4444", va="bottom")

        self.bar_canvas.fig.subplots_adjust(left=0.12, right=0.96, top=0.94, bottom=0.15)
        self.bar_canvas.draw()

    def _draw_top_categories(self, cat_totals: list, month_label: str = "This Month",
                             budgets: dict = None):
        budgets = budgets or {}
        has_budgets = bool(budgets)
        self.top_title.setText(
            f"Top Categories — {month_label}" + (" vs Budget" if has_budgets else "")
        )

        # Clear existing
        while self.top_categories_layout.count():
            child = self.top_categories_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not cat_totals:
            lbl = QLabel(f"No transactions in {month_label}")
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; padding: 8px; background: transparent; border: none;")
            self.top_categories_layout.addWidget(lbl)
            return

        total = sum(c.total for c in cat_totals)
        for ct in cat_totals[:8]:
            pct = (ct.total / total * 100) if total else 0
            budget_amt = budgets.get(ct.category, 0)

            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(2)

            # Top line: dot, name, amount, percentage
            top_row = QHBoxLayout()
            top_row.setSpacing(8)

            dot = QLabel("\u25CF")
            dot.setStyleSheet(f"color: {ct.colour}; font-size: 14px; background: transparent; border: none;")
            dot.setFixedWidth(20)
            top_row.addWidget(dot)

            name = QLabel(ct.display_name)
            name.setFont(font_body(10))
            name.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
            top_row.addWidget(name, stretch=2)

            amt = QLabel(f"${ct.total:,.2f}")
            amt.setFont(font_body(10))
            amt.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
            top_row.addWidget(amt, stretch=1)

            if budget_amt > 0:
                budget_pct = ct.total / budget_amt * 100
                over = ct.total > budget_amt
                pct_colour = NEGATIVE if over else POSITIVE
                pct_text = f"{budget_pct:.0f}%"
                pct_lbl = QLabel(pct_text)
                pct_lbl.setFont(font_body(9))
                pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                pct_lbl.setStyleSheet(f"color: {pct_colour}; font-weight: 600; background: transparent; border: none;")
                pct_lbl.setFixedWidth(50)
                pct_lbl.setToolTip(f"${ct.total:,.0f} of ${budget_amt:,.0f} budget")
                top_row.addWidget(pct_lbl)
            else:
                pct_lbl = QLabel(f"{pct:.1f}%")
                pct_lbl.setFont(font_body(9))
                pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                pct_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
                pct_lbl.setFixedWidth(50)
                top_row.addWidget(pct_lbl)

            rl.addLayout(top_row)

            # Budget progress bar (only if budget exists)
            if budget_amt > 0:
                bar = QProgressBar()
                bar.setFixedHeight(4)
                bar.setTextVisible(False)
                bar.setMaximum(int(budget_amt))
                bar.setValue(min(int(ct.total), int(budget_amt)))

                over = ct.total > budget_amt
                bar_colour = NEGATIVE if over else ct.colour
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: #F3F4F6;
                        border: none;
                        border-radius: 2px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {bar_colour};
                        border-radius: 2px;
                    }}
                """)
                rl.addWidget(bar)

            self.top_categories_layout.addWidget(row)
