"""
QThread workers for classifying transactions.

Two engines:
  - ClassifyAPIWorker: Uses Anthropic Claude API
  - ClassifyLocalWorker: Uses local DistilBERT model

Both share the same signal interface so the Settings UI can swap between them.
"""

import sqlite3
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from gui.models.database import BudgetDatabase
from gui.categories import CATEGORIES, get_classification_prompt


class ClassifyAPIWorker(QThread):
    """Background worker that uses Claude API to classify uncategorised transactions."""
    progress = Signal(int, int, str)    # current, total, description
    finished = Signal(int, int)          # classified, errors
    log = Signal(str)

    def __init__(self, db: BudgetDatabase, api_key: str,
                 txn_ids: list = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.api_key = api_key
        self.txn_ids = txn_ids
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)

            # Get transactions to classify
            conn = sqlite3.connect(self.db.db_path)
            conn.row_factory = sqlite3.Row

            if self.txn_ids:
                placeholders = ",".join("?" * len(self.txn_ids))
                rows = conn.execute(
                    f"SELECT id, description, amount FROM transactions "
                    f"WHERE id IN ({placeholders}) AND budget_category IS NULL "
                    f"ORDER BY trans_date DESC",
                    self.txn_ids
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, description, amount FROM transactions "
                    "WHERE budget_category IS NULL ORDER BY trans_date DESC"
                ).fetchall()
            conn.close()

            total = len(rows)
            if total == 0:
                self.log.emit("All transactions are already categorised!")
                self.finished.emit(0, 0)
                return

            scope = "last import" if self.txn_ids else "all uncategorised"
            self.log.emit(f"Classifying {total} transactions ({scope}) using Claude API...")
            cat_prompt = get_classification_prompt()

            classified = 0
            errors = 0
            batch_updates = []

            for i, row in enumerate(rows):
                if self._stop:
                    self.log.emit("Stopped by user.")
                    break

                desc = row["description"]
                amount = row["amount"]
                self.progress.emit(i + 1, total, desc[:50])

                try:
                    prompt = f"""Classify this Australian credit card transaction into exactly one category.

Categories:
{cat_prompt}

Transaction: {desc}
Amount: ${amount:.2f}

Respond with ONLY the category id (e.g. "groceries"), nothing else."""

                    message = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=30,
                        messages=[{"role": "user", "content": prompt}]
                    )

                    category = message.content[0].text.strip().strip('"').lower()

                    if category not in CATEGORIES:
                        self.log.emit(f"  Invalid category '{category}' for: {desc[:40]}... -> other")
                        category = "other"

                    batch_updates.append((category, row["id"]))
                    classified += 1

                    if len(batch_updates) >= 20:
                        self.db.bulk_update_categories(batch_updates)
                        batch_updates = []

                except Exception as e:
                    errors += 1
                    self.log.emit(f"  Error classifying '{desc[:40]}...': {e}")

            if batch_updates:
                self.db.bulk_update_categories(batch_updates)

            self.log.emit(f"\nDone! Classified: {classified}, Errors: {errors}")
            self.finished.emit(classified, errors)

        except ImportError:
            self.log.emit("ERROR: anthropic package not installed. Run: pip install anthropic")
            self.finished.emit(0, 0)
        except Exception as e:
            self.log.emit(f"ERROR: {e}")
            self.finished.emit(0, 0)


class ClassifyLocalWorker(QThread):
    """Background worker that uses the local DistilBERT model to classify transactions."""
    progress = Signal(int, int, str)    # current, total, description
    finished = Signal(int, int)          # classified, errors
    log = Signal(str)

    def __init__(self, db: BudgetDatabase, model_dir: str,
                 txn_ids: list = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.model_dir = model_dir
        self.txn_ids = txn_ids
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import torch
            import torch.nn as nn
            from transformers import DistilBertTokenizer, DistilBertModel
            import pickle

            model_path = Path(self.model_dir)

            # Verify model files exist
            if not (model_path / 'best_model.pt').exists():
                self.log.emit("ERROR: No trained model found. Train a model first in Settings.")
                self.finished.emit(0, 0)
                return

            self.log.emit("Loading local DistilBERT model...")

            # Load tokenizer
            tokenizer = DistilBertTokenizer.from_pretrained(model_path / 'tokenizer')

            # Load label encoder
            with open(model_path / 'label_encoder.pkl', 'rb') as f:
                label_encoder = pickle.load(f)

            # Load model
            checkpoint = torch.load(
                model_path / 'best_model.pt',
                map_location=torch.device('cpu'),
                weights_only=False
            )
            n_classes = checkpoint['n_classes']

            # Rebuild model architecture
            class ExpenseClassifier(nn.Module):
                def __init__(self, n_cls, dropout=0.3):
                    super().__init__()
                    self.bert = DistilBertModel.from_pretrained('distilbert-base-uncased')
                    self.dropout = nn.Dropout(dropout)
                    self.classifier = nn.Linear(self.bert.config.hidden_size, n_cls)

                def forward(self, input_ids, attention_mask):
                    outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                    pooled = outputs.last_hidden_state[:, 0]
                    return self.classifier(self.dropout(pooled))

            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            model = ExpenseClassifier(n_cls=n_classes).to(device)
            model.load_state_dict(checkpoint['model_state_dict'])
            model.eval()

            model_cats = list(label_encoder.classes_)
            self.log.emit(f"Model loaded: {n_classes} categories on {device}")
            self.log.emit(f"Categories: {', '.join(model_cats)}")

            # Check for category mismatch
            app_cats = set(CATEGORIES.keys()) - {"uncategorised"}
            model_cat_set = set(model_cats)
            if model_cat_set != app_cats:
                missing = app_cats - model_cat_set
                extra = model_cat_set - app_cats
                if missing:
                    self.log.emit(f"Warning: Model missing categories: {', '.join(sorted(missing))}")
                if extra:
                    self.log.emit(f"Warning: Model has extra categories: {', '.join(sorted(extra))}")

            # Get transactions to classify
            conn = sqlite3.connect(self.db.db_path)
            conn.row_factory = sqlite3.Row

            if self.txn_ids:
                placeholders = ",".join("?" * len(self.txn_ids))
                rows = conn.execute(
                    f"SELECT id, description, amount FROM transactions "
                    f"WHERE id IN ({placeholders}) AND budget_category IS NULL "
                    f"ORDER BY trans_date DESC",
                    self.txn_ids
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, description, amount FROM transactions "
                    "WHERE budget_category IS NULL ORDER BY trans_date DESC"
                ).fetchall()
            conn.close()

            total = len(rows)
            if total == 0:
                self.log.emit("All transactions are already categorised!")
                self.finished.emit(0, 0)
                return

            scope = "last import" if self.txn_ids else "all uncategorised"
            self.log.emit(f"\nClassifying {total} transactions ({scope}) using local model...")

            classified = 0
            errors = 0
            batch_updates = []

            for i, row in enumerate(rows):
                if self._stop:
                    self.log.emit("Stopped by user.")
                    break

                desc = row["description"]
                self.progress.emit(i + 1, total, desc[:50])

                try:
                    # Tokenize
                    encoding = tokenizer(
                        desc, add_special_tokens=True, max_length=128,
                        padding='max_length', truncation=True,
                        return_attention_mask=True, return_tensors='pt'
                    )

                    input_ids = encoding['input_ids'].to(device)
                    attention_mask = encoding['attention_mask'].to(device)

                    with torch.no_grad():
                        outputs = model(input_ids, attention_mask)
                        _, predicted = torch.max(outputs, 1)

                    category = label_encoder.inverse_transform([predicted.item()])[0]

                    # Validate against app categories
                    if category not in CATEGORIES:
                        self.log.emit(f"  Unknown category '{category}' for: {desc[:40]}... -> other")
                        category = "other"

                    batch_updates.append((category, row["id"]))
                    classified += 1

                    if len(batch_updates) >= 50:  # Bigger batches since local is fast
                        self.db.bulk_update_categories(batch_updates)
                        batch_updates = []

                except Exception as e:
                    errors += 1
                    self.log.emit(f"  Error: {desc[:40]}... -> {e}")

            if batch_updates:
                self.db.bulk_update_categories(batch_updates)

            self.log.emit(f"\nDone! Classified: {classified}, Errors: {errors}")
            self.finished.emit(classified, errors)

        except ImportError as e:
            self.log.emit(f"ERROR: Missing dependency: {e}")
            self.log.emit("Install with: pip install torch transformers scikit-learn")
            self.finished.emit(0, 0)
        except Exception as e:
            self.log.emit(f"ERROR: {e}")
            self.finished.emit(0, 0)
