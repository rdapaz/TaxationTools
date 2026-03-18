"""
Data-access layer for the budgeting app.

Wraps the existing expenses.db schema and provides query helpers
that return typed results for the GUI views.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from gui.categories import CATEGORIES, LEGACY_MAP


@dataclass
class Transaction:
    id: int
    trans_date: date
    description: str
    reference_number: str
    amount: float
    category: Optional[str]
    ai_classified: int
    created_at: Optional[str] = None


@dataclass
class MonthlySummary:
    month: str            # "2025-03"
    total: float
    count: int
    by_category: Dict[str, float]


@dataclass
class CategoryTotal:
    category: str
    display_name: str
    total: float
    count: int
    colour: str


class BudgetDatabase:
    """Thread-safe (read) database wrapper.  Write ops use a dedicated connection."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _conn(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _ensure_schema(self):
        """Create tables if they don't exist (safe on existing DB)."""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    trans_date       TEXT    NOT NULL,
                    description      TEXT    NOT NULL,
                    reference_number TEXT    NOT NULL,
                    amount           REAL    NOT NULL,
                    category         TEXT,
                    ai_classified    INTEGER DEFAULT 0,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (trans_date, reference_number, amount)
                )
            """)

            # Add budget_category column if not present (migration for existing DBs)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
            if "budget_category" not in cols:
                conn.execute("ALTER TABLE transactions ADD COLUMN budget_category TEXT")

            # Budgets table — one row per category
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    category      TEXT PRIMARY KEY,
                    monthly_amount REAL NOT NULL DEFAULT 0,
                    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # App settings table — key/value store for preferences
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    # ── App Settings ─────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Return a single setting value, or default if not set."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        """Set or update a single setting."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, value)
            )

    # ── Training Data Queries ────────────────────────────────────────────────

    def get_categorised_transactions(self) -> List[dict]:
        """Return all transactions that have a budget_category set.
        Used as training data for the local model."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, description, amount, budget_category "
                "FROM transactions WHERE budget_category IS NOT NULL "
                "AND budget_category != 'uncategorised'"
            ).fetchall()
        return [{"id": r["id"], "description": r["description"],
                 "amount": r["amount"], "category": r["budget_category"]} for r in rows]

    def get_training_stats(self) -> Dict[str, int]:
        """Return {category: count} for all categorised transactions."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT budget_category as cat, COUNT(*) as cnt "
                "FROM transactions WHERE budget_category IS NOT NULL "
                "AND budget_category != 'uncategorised' "
                "GROUP BY cat ORDER BY cnt DESC"
            ).fetchall()
        return {r["cat"]: r["cnt"] for r in rows}

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_transactions(self, start: Optional[str] = None,
                         end: Optional[str] = None,
                         category: Optional[str] = None,
                         limit: int = 500, offset: int = 0) -> List[Transaction]:
        """Return transactions with optional date/category filtering."""
        clauses, params = [], []
        if start:
            clauses.append("trans_date >= ?"); params.append(start)
        if end:
            clauses.append("trans_date <= ?"); params.append(end)
        if category:
            clauses.append("(budget_category = ? OR category = ?)"); params.extend([category, category])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""SELECT id, trans_date, description, reference_number, amount,
                         COALESCE(budget_category, category) as category,
                         ai_classified, created_at
                  FROM transactions {where}
                  ORDER BY trans_date DESC
                  LIMIT ? OFFSET ?"""
        params.extend([limit, offset])

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_txn(r) for r in rows]

    def get_transaction_count(self, start: Optional[str] = None,
                              end: Optional[str] = None) -> int:
        clauses, params = [], []
        if start:
            clauses.append("trans_date >= ?"); params.append(start)
        if end:
            clauses.append("trans_date <= ?"); params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]

    def get_category_totals(self, start: Optional[str] = None,
                            end: Optional[str] = None) -> List[CategoryTotal]:
        """Return spending totals per category for the given date range."""
        clauses, params = [], []
        if start:
            clauses.append("trans_date >= ?"); params.append(start)
        if end:
            clauses.append("trans_date <= ?"); params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        sql = f"""SELECT COALESCE(budget_category, category) as cat,
                         SUM(amount) as total, COUNT(*) as cnt
                  FROM transactions {where}
                  GROUP BY cat
                  ORDER BY total DESC"""
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            cat_id = r["cat"] or "uncategorised"
            cat_info = CATEGORIES.get(cat_id)
            results.append(CategoryTotal(
                category=cat_id,
                display_name=cat_info.display_name if cat_info else cat_id.replace("_", " ").title(),
                total=r["total"],
                count=r["cnt"],
                colour=cat_info.colour if cat_info else "#9E9E9E",
            ))
        return results

    def get_monthly_totals(self, months: int = 12) -> List[MonthlySummary]:
        """Return per-month spending summaries for the last N months."""
        sql = """
            SELECT substr(trans_date, 1, 7) as month,
                   SUM(amount) as total, COUNT(*) as cnt,
                   COALESCE(budget_category, category) as cat
            FROM transactions
            GROUP BY month, cat
            ORDER BY month DESC
        """
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()

        # Aggregate into MonthlySummary objects
        monthly: Dict[str, MonthlySummary] = {}
        for r in rows:
            m = r["month"]
            if m not in monthly:
                monthly[m] = MonthlySummary(month=m, total=0, count=0, by_category={})
            ms = monthly[m]
            ms.total += r["total"]
            ms.count += r["cnt"]
            cat = r["cat"] or "uncategorised"
            ms.by_category[cat] = ms.by_category.get(cat, 0) + r["total"]

        # Sort descending, limit
        sorted_months = sorted(monthly.values(), key=lambda s: s.month, reverse=True)
        return sorted_months[:months]

    def get_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """Return (min_date, max_date) from the database."""
        with self._conn() as conn:
            row = conn.execute("SELECT MIN(trans_date), MAX(trans_date) FROM transactions").fetchone()
        return (row[0], row[1]) if row else (None, None)

    def get_total_spending(self, start: Optional[str] = None,
                           end: Optional[str] = None) -> float:
        clauses, params = [], []
        if start:
            clauses.append("trans_date >= ?"); params.append(start)
        if end:
            clauses.append("trans_date <= ?"); params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            row = conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM transactions {where}", params).fetchone()
        return row[0]

    # ── Mutations ───────────────────────────────────────────────────────────

    def update_category(self, txn_id: int, new_category: str):
        """Update the budget_category for a single transaction."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE transactions SET budget_category = ? WHERE id = ?",
                (new_category, txn_id)
            )

    def bulk_update_categories(self, updates: List[Tuple[str, int]]):
        """Batch update: list of (new_category, txn_id)."""
        with self._conn() as conn:
            conn.executemany(
                "UPDATE transactions SET budget_category = ? WHERE id = ?",
                updates
            )

    def migrate_legacy_categories(self) -> int:
        """
        Migrate old tax-tool categories to new budget categories
        using the LEGACY_MAP. Only touches rows where budget_category is NULL.
        Returns number of rows updated.
        """
        count = 0
        with self._conn() as conn:
            for old_cat, new_cat in LEGACY_MAP.items():
                if new_cat is None:
                    continue  # "not work related" needs manual re-categorisation
                result = conn.execute(
                    "UPDATE transactions SET budget_category = ? WHERE category = ? AND budget_category IS NULL",
                    (new_cat, old_cat)
                )
                count += result.rowcount
        return count

    def get_unmigrated_count(self) -> int:
        """Count transactions that still need budget_category assignment."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE budget_category IS NULL"
            ).fetchone()
        return row[0]

    # ── Budget operations ──────────────────────────────────────────────────

    def get_budgets(self) -> Dict[str, float]:
        """Return {category_id: monthly_amount} for all budgeted categories."""
        with self._conn() as conn:
            rows = conn.execute("SELECT category, monthly_amount FROM budgets").fetchall()
        return {r["category"]: r["monthly_amount"] for r in rows}

    def set_budget(self, category: str, amount: float):
        """Set or update the monthly budget for a single category."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO budgets (category, monthly_amount, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (category, amount)
            )

    def set_budgets(self, budgets: Dict[str, float]):
        """Bulk set budgets from a dict of {category_id: amount}."""
        with self._conn() as conn:
            for cat, amount in budgets.items():
                conn.execute(
                    "INSERT OR REPLACE INTO budgets (category, monthly_amount, updated_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (cat, amount)
                )

    def get_category_averages(self, months: int = 3) -> Dict[str, float]:
        """Return average monthly spending per category over the last N months.
        Uses the most recent N months that have data."""
        # Get the most recent months
        with self._conn() as conn:
            month_rows = conn.execute(
                "SELECT DISTINCT substr(trans_date, 1, 7) as month "
                "FROM transactions ORDER BY month DESC LIMIT ?",
                (months,)
            ).fetchall()

            if not month_rows:
                return {}

            recent_months = [r["month"] for r in month_rows]
            n_months = len(recent_months)
            min_month = min(recent_months)
            max_month = max(recent_months)

            # Get totals per category across those months
            rows = conn.execute(
                "SELECT COALESCE(budget_category, category) as cat, SUM(amount) as total "
                "FROM transactions "
                "WHERE substr(trans_date, 1, 7) >= ? AND substr(trans_date, 1, 7) <= ? "
                "GROUP BY cat",
                (min_month, max_month)
            ).fetchall()

        return {r["cat"]: round(r["total"] / n_months, 2) for r in rows if r["cat"]}

    def get_budget_vs_actual(self, start: str, end: str) -> List[dict]:
        """Return budget vs actual spending for the given date range.
        Returns list of {category, display_name, budget, actual, colour}."""
        budgets = self.get_budgets()
        actuals_list = self.get_category_totals(start, end)

        # Build combined view
        all_cats = set(budgets.keys()) | {ct.category for ct in actuals_list}
        actuals = {ct.category: ct for ct in actuals_list}

        results = []
        for cat_id in sorted(all_cats):
            budget_amt = budgets.get(cat_id, 0)
            actual_ct = actuals.get(cat_id)
            actual_amt = actual_ct.total if actual_ct else 0
            cat_info = CATEGORIES.get(cat_id)

            if budget_amt == 0 and actual_amt == 0:
                continue

            results.append({
                "category": cat_id,
                "display_name": cat_info.display_name if cat_info else cat_id.replace("_", " ").title(),
                "budget": budget_amt,
                "actual": actual_amt,
                "colour": cat_info.colour if cat_info else "#9E9E9E",
            })

        # Sort by budget descending (biggest budget first)
        results.sort(key=lambda x: x["budget"], reverse=True)
        return results

    def get_total_budget(self) -> float:
        """Return sum of all monthly budgets."""
        with self._conn() as conn:
            row = conn.execute("SELECT COALESCE(SUM(monthly_amount), 0) FROM budgets").fetchone()
        return row[0]

    def get_recent_uncategorised_ids(self, limit: int = 500) -> List[int]:
        """Return IDs of the most recently added uncategorised transactions."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id FROM transactions WHERE budget_category IS NULL "
                "ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [r["id"] for r in rows]

    def get_uncategorised_by_ids(self, ids: List[int]) -> List[dict]:
        """Return id, description, amount for specific transaction IDs that are uncategorised."""
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT id, description, amount FROM transactions "
                f"WHERE id IN ({placeholders}) AND budget_category IS NULL",
                ids
            ).fetchall()
        return [{"id": r["id"], "description": r["description"], "amount": r["amount"]} for r in rows]

    def get_monthly_transaction_counts(self) -> List[Tuple[str, int]]:
        """Return (month, count) for every month between min and max date.
        Missing months appear with count=0."""
        min_d, max_d = self.get_date_range()
        if not min_d or not max_d:
            return []

        # Get actual counts
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT substr(trans_date, 1, 7) as month, COUNT(*) as cnt "
                "FROM transactions GROUP BY month ORDER BY month"
            ).fetchall()
        actual = {r["month"]: r["cnt"] for r in rows}

        # Generate all months in range
        from datetime import datetime
        start = datetime.strptime(min_d[:7] + "-01", "%Y-%m-%d").date()
        end = datetime.strptime(max_d[:7] + "-01", "%Y-%m-%d").date()

        result = []
        current = start
        while current <= end:
            m = current.strftime("%Y-%m")
            result.append((m, actual.get(m, 0)))
            # Advance to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_txn(row) -> Transaction:
        return Transaction(
            id=row["id"],
            trans_date=datetime.strptime(row["trans_date"], "%Y-%m-%d").date(),
            description=row["description"],
            reference_number=row["reference_number"],
            amount=row["amount"],
            category=row["category"],
            ai_classified=row["ai_classified"],
            created_at=row["created_at"] if "created_at" in row.keys() else None,
        )
