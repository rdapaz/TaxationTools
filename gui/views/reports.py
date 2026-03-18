"""
Reports view — monthly comparisons, category trends, and tax summary.
"""

from datetime import date, timedelta
from collections import defaultdict
import numpy as np

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QComboBox, QDateEdit, QPushButton, QSizePolicy,
)

from gui.models.database import BudgetDatabase
from gui.widgets.chart_canvas import ChartCanvas
from gui.widgets.stat_card import StatCard
from gui.categories import CATEGORIES, colour_for, get_groups
from gui.widgets.help_window import make_help_button
from gui.theme import (
    font_heading, font_body, BG_MAIN, BG_CARD, BORDER, NAVY,
    TEXT_SECONDARY, CARD_STYLE,
)

import matplotlib.ticker as mticker


class ReportsView(QWidget):
    """Reports with monthly comparison, category trends, and tax summary."""

    def __init__(self, db: BudgetDatabase, parent=None):
        super().__init__(parent)
        self.db = db
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
        title = QLabel("Reports")
        title.setFont(font_heading(20))
        title.setStyleSheet(f"color: {NAVY}; background: transparent;")
        title_row.addWidget(title)
        title_row.addWidget(make_help_button("Reports", self))
        title_row.addStretch()
        self.main_layout.addLayout(title_row)

        # ── Controls row ────────────────────────────────────────────────
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        ctrl_card.setStyleSheet(CARD_STYLE)
        ctrl_layout = QHBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(16, 10, 16, 10)
        ctrl_layout.setSpacing(12)

        combo_style = f"border: 1px solid {BORDER}; border-radius: 6px; padding: 6px; background: white; color: #1A1A2E; font-size: 10pt;"

        # Focus month selector — populated from DB
        ctrl_layout.addWidget(self._styled_label("Focus month:"))
        self.focus_month_combo = QComboBox()
        self.focus_month_combo.setStyleSheet(combo_style)
        self.focus_month_combo.setMinimumWidth(130)
        ctrl_layout.addWidget(self.focus_month_combo)

        ctrl_layout.addWidget(self._styled_label("Trend range:"))
        self.months_combo = QComboBox()
        for n in [3, 6, 12]:
            self.months_combo.addItem(f"Last {n} months", n)
        self.months_combo.setCurrentIndex(1)  # default 6
        self.months_combo.setStyleSheet(combo_style)
        self.months_combo.currentIndexChanged.connect(self.refresh)
        ctrl_layout.addWidget(self.months_combo)

        ctrl_layout.addStretch()

        # Tax year summary
        self.tax_year_combo = QComboBox()
        current_year = date.today().year
        # Australian financial year: Jul-Jun
        for y in range(current_year, current_year - 3, -1):
            self.tax_year_combo.addItem(f"FY {y-1}/{y}", y)
        self.tax_year_combo.setStyleSheet(combo_style)
        self.tax_year_combo.currentIndexChanged.connect(self.refresh)
        ctrl_layout.addWidget(self._styled_label("Tax year:"))
        ctrl_layout.addWidget(self.tax_year_combo)

        self.main_layout.addWidget(ctrl_card)

        # ── Tax deductible summary cards ────────────────────────────────
        tax_row = QHBoxLayout()
        tax_row.setSpacing(16)
        self.card_tax_total = StatCard("Tax Deductible (FY)")
        self.card_tax_items = StatCard("Deductible Items")
        self.card_avg_spend = StatCard("Avg Monthly Spend")
        self.card_projected = StatCard("Projected Annual")
        for card in (self.card_tax_total, self.card_tax_items,
                     self.card_avg_spend, self.card_projected):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tax_row.addWidget(card)
        self.main_layout.addLayout(tax_row)

        # ── Monthly comparison (paired histogram) ───────────────────────
        comp_card = QFrame()
        comp_card.setObjectName("card")
        comp_card.setStyleSheet(CARD_STYLE)
        comp_layout = QVBoxLayout(comp_card)
        comp_layout.setContentsMargins(16, 12, 16, 12)
        comp_title = QLabel("Monthly Comparison by Category")
        comp_title.setFont(font_heading(13))
        comp_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        comp_layout.addWidget(comp_title)
        self.comp_canvas = ChartCanvas(width=10, height=5)
        self.comp_canvas.setStyleSheet("background: transparent; border: none;")
        self.comp_canvas.setMinimumHeight(350)
        comp_layout.addWidget(self.comp_canvas)
        self.main_layout.addWidget(comp_card)

        # ── Category trend (rolling average) ────────────────────────────
        trend_card = QFrame()
        trend_card.setObjectName("card")
        trend_card.setStyleSheet(CARD_STYLE)
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(16, 12, 16, 12)
        trend_title = QLabel("Monthly Spending Trend (Top 6 Categories)")
        trend_title.setFont(font_heading(13))
        trend_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        trend_layout.addWidget(trend_title)
        self.trend_canvas = ChartCanvas(width=10, height=4.5)
        self.trend_canvas.setStyleSheet("background: transparent; border: none;")
        self.trend_canvas.setMinimumHeight(320)
        trend_layout.addWidget(self.trend_canvas)
        self.main_layout.addWidget(trend_card)

        # ── Current vs 3-month rolling average ──────────────────────────
        avg_card = QFrame()
        avg_card.setObjectName("card")
        avg_card.setStyleSheet(CARD_STYLE)
        avg_layout = QVBoxLayout(avg_card)
        avg_layout.setContentsMargins(16, 12, 16, 12)
        self.avg_title = QLabel("Current Month vs 3-Month Rolling Average")
        self.avg_title.setFont(font_heading(13))
        self.avg_title.setStyleSheet(f"color: {NAVY}; background: transparent; border: none;")
        avg_layout.addWidget(self.avg_title)
        self.avg_canvas = ChartCanvas(width=10, height=4)
        self.avg_canvas.setStyleSheet("background: transparent; border: none;")
        self.avg_canvas.setMinimumHeight(300)
        avg_layout.addWidget(self.avg_canvas)
        self.main_layout.addWidget(avg_card)

        self.main_layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _styled_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {NAVY}; background: transparent; border: none; font-size: 10pt;")
        return lbl

    # ── Refresh ─────────────────────────────────────────────────────────

    def refresh(self):
        # Get all monthly data
        all_monthly = self.db.get_monthly_totals(24)  # up to 2 years

        # Populate focus month combo (only once, or if data changed)
        available_months = [m.month for m in all_monthly]
        current_selection = self.focus_month_combo.currentData()

        if self.focus_month_combo.count() == 0 or \
           set(available_months) != set(self.focus_month_combo.itemData(i)
                                        for i in range(self.focus_month_combo.count())):
            self.focus_month_combo.blockSignals(True)
            self.focus_month_combo.clear()
            for m in available_months:
                self.focus_month_combo.addItem(m, m)
            # Restore selection or default to most recent
            if current_selection:
                idx = self.focus_month_combo.findData(current_selection)
                if idx >= 0:
                    self.focus_month_combo.setCurrentIndex(idx)
            self.focus_month_combo.blockSignals(False)
            # Connect after first populate to avoid double-refresh
            try:
                self.focus_month_combo.currentIndexChanged.disconnect()
            except RuntimeError:
                pass
            self.focus_month_combo.currentIndexChanged.connect(self.refresh)

        focus_month = self.focus_month_combo.currentData() or (available_months[0] if available_months else None)
        n_months = self.months_combo.currentData() or 6

        # Find focus month index in all_monthly
        focus_idx = 0
        for i, m in enumerate(all_monthly):
            if m.month == focus_month:
                focus_idx = i
                break

        # Slice data for charts
        monthly_for_trend = all_monthly[:n_months + 1]

        # Tax year stats
        fy_year = self.tax_year_combo.currentData() or date.today().year
        fy_start = f"{fy_year - 1}-07-01"
        fy_end = f"{fy_year}-06-30"
        tax_totals = self.db.get_category_totals(fy_start, fy_end)
        tax_deductible = [t for t in tax_totals if CATEGORIES.get(t.category, None)
                          and CATEGORIES[t.category].tax_deductible]
        tax_total = sum(t.total for t in tax_deductible)
        tax_items = sum(t.count for t in tax_deductible)

        # Average monthly & projected
        complete_months = all_monthly[1:13] if len(all_monthly) > 1 else all_monthly
        avg_monthly = sum(m.total for m in complete_months) / max(len(complete_months), 1)
        projected = avg_monthly * 12

        self.card_tax_total.set_value(f"${tax_total:,.0f}")
        self.card_tax_items.set_value(f"{tax_items}")
        self.card_avg_spend.set_value(f"${avg_monthly:,.0f}")
        self.card_projected.set_value(f"${projected:,.0f}")

        # Comparison: focus month vs previous month
        focus_data = all_monthly[focus_idx] if focus_idx < len(all_monthly) else None
        prev_data = all_monthly[focus_idx + 1] if (focus_idx + 1) < len(all_monthly) else None
        self._draw_comparison(focus_data, prev_data)

        self._draw_trend(monthly_for_trend)

        # Rolling average: focus month vs average of 3 months before it
        prev_3 = all_monthly[focus_idx + 1:focus_idx + 4]
        self._draw_rolling_average(focus_data, prev_3)

        # Update title
        if focus_month:
            self.avg_title.setText(f"{focus_month} vs 3-Month Rolling Average")

    def _draw_comparison(self, current, previous):
        """Paired histogram: focus month vs previous month by category."""
        self.comp_canvas.fig.clear()

        if not current or not previous:
            ax = self.comp_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Need at least 2 months of data", ha="center", va="center",
                    fontsize=12, color="#999")
            ax.axis("off")
            self.comp_canvas.draw()
            return

        # Get all categories present in either month
        all_cats = sorted(set(list(current.by_category.keys()) + list(previous.by_category.keys())))
        # Filter to categories with meaningful spending
        all_cats = [c for c in all_cats if (current.by_category.get(c, 0) + previous.by_category.get(c, 0)) > 5]

        if not all_cats:
            ax = self.comp_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No category data", ha="center", va="center",
                    fontsize=12, color="#999")
            ax.axis("off")
            self.comp_canvas.draw()
            return

        labels = []
        for c in all_cats:
            cat_info = CATEGORIES.get(c)
            labels.append(cat_info.display_name if cat_info else c.replace("_", " ").title())

        cur_vals = [current.by_category.get(c, 0) for c in all_cats]
        prev_vals = [previous.by_category.get(c, 0) for c in all_cats]

        x = np.arange(len(labels))
        width = 0.35

        ax = self.comp_canvas.fig.add_subplot(111)
        bars1 = ax.bar(x - width/2, prev_vals, width, label=previous.month,
                        color="#A0CBE8", edgecolor="white", linewidth=0.5)
        bars2 = ax.bar(x + width/2, cur_vals, width, label=current.month,
                        color="#1F3864", edgecolor="white", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("Spending ($)", fontsize=9, color="#6B7280")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.legend(fontsize=9, frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.tick_params(axis="both", labelsize=8, colors="#6B7280")
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, linestyle="--", alpha=0.3)

        self.comp_canvas.fig.subplots_adjust(left=0.10, right=0.96, top=0.94, bottom=0.22)
        self.comp_canvas.draw()

    def _draw_trend(self, monthly):
        """Line chart showing top 6 categories over time."""
        self.trend_canvas.fig.clear()

        if len(monthly) < 3:
            ax = self.trend_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Need at least 3 months of data", ha="center", va="center",
                    fontsize=12, color="#999")
            ax.axis("off")
            self.trend_canvas.draw()
            return

        # Find top 6 categories by total spend across all months
        cat_totals = defaultdict(float)
        for m in monthly:
            for cat, val in m.by_category.items():
                cat_totals[cat] += val
        top_cats = sorted(cat_totals, key=cat_totals.get, reverse=True)[:6]

        months_sorted = list(reversed(monthly))
        x_labels = [m.month[5:] + "\n" + m.month[:4] for m in months_sorted]

        ax = self.trend_canvas.fig.add_subplot(111)
        for cat in top_cats:
            values = [m.by_category.get(cat, 0) for m in months_sorted]
            cat_info = CATEGORIES.get(cat)
            label = cat_info.display_name if cat_info else cat.replace("_", " ").title()
            colour = cat_info.colour if cat_info else "#9E9E9E"
            ax.plot(x_labels, values, marker="o", markersize=4, linewidth=2,
                    label=label, color=colour)

        ax.set_ylabel("Spending ($)", fontsize=9, color="#6B7280")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.tick_params(axis="both", labelsize=8, colors="#6B7280")
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, linestyle="--", alpha=0.3)

        self.trend_canvas.fig.subplots_adjust(left=0.10, right=0.78, top=0.94, bottom=0.14)
        self.trend_canvas.draw()

    def _draw_rolling_average(self, current, prev_months):
        """Horizontal bar chart: focus month vs 3-month rolling average per category."""
        self.avg_canvas.fig.clear()

        if not current or not prev_months:
            ax = self.avg_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Need more data", ha="center", va="center",
                    fontsize=12, color="#999")
            ax.axis("off")
            self.avg_canvas.draw()
            return

        avg_by_cat = defaultdict(float)
        for m in prev_months:
            for cat, val in m.by_category.items():
                avg_by_cat[cat] += val
        for cat in avg_by_cat:
            avg_by_cat[cat] /= len(prev_months)

        # All categories with any spend
        all_cats = sorted(
            set(list(current.by_category.keys()) + list(avg_by_cat.keys())),
            key=lambda c: current.by_category.get(c, 0),
            reverse=True
        )
        # Top 10 only
        all_cats = [c for c in all_cats
                    if (current.by_category.get(c, 0) + avg_by_cat.get(c, 0)) > 5][:10]

        if not all_cats:
            ax = self.avg_canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="#999")
            ax.axis("off")
            self.avg_canvas.draw()
            return

        labels = []
        for c in all_cats:
            cat_info = CATEGORIES.get(c)
            labels.append(cat_info.display_name if cat_info else c.replace("_", " ").title())

        cur_vals = [current.by_category.get(c, 0) for c in all_cats]
        avg_vals = [avg_by_cat.get(c, 0) for c in all_cats]

        y = np.arange(len(labels))
        height = 0.35

        ax = self.avg_canvas.fig.add_subplot(111)
        ax.barh(y + height/2, avg_vals, height, label="3-Month Avg",
                color="#A0CBE8", edgecolor="white", linewidth=0.5)
        ax.barh(y - height/2, cur_vals, height, label=current.month,
                color="#1F3864", edgecolor="white", linewidth=0.5)

        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("Spending ($)", fontsize=9, color="#6B7280")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.legend(fontsize=9, frameon=False, loc="lower right")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.tick_params(axis="both", labelsize=8, colors="#6B7280")
        ax.set_axisbelow(True)
        ax.xaxis.grid(True, linestyle="--", alpha=0.3)
        ax.invert_yaxis()

        self.avg_canvas.fig.subplots_adjust(left=0.18, right=0.96, top=0.94, bottom=0.14)
        self.avg_canvas.draw()
