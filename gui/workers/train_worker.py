"""
QThread worker for training a DistilBERT expense classifier from SQLite data.

Adapted from expense_classifier_trainer.py to:
  - Pull training data from SQLite (budget_category column)
  - Use the 19 budget categories
  - Emit progress signals for the GUI
  - Save to models/ directory
"""

from PySide6.QtCore import QThread, Signal

from gui.models.database import BudgetDatabase
from gui.categories import CATEGORIES


class TrainWorker(QThread):
    """Background worker for training the local DistilBERT classifier."""

    # Signals for GUI updates
    progress = Signal(int, int, str)     # epoch, total_epochs, status_message
    log = Signal(str)                    # log line
    finished = Signal(bool, str)         # success, summary_message

    def __init__(self, db: BudgetDatabase, model_dir: str,
                 epochs: int = 10, batch_size: int = 16,
                 learning_rate: float = 2e-5, parent=None):
        super().__init__(parent)
        self.db = db
        self.model_dir = model_dir
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._train()
        except ImportError as e:
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            self.log.emit(f"ERROR: Missing dependency: {missing}")
            self.log.emit("Install with: pip install torch transformers scikit-learn")
            self.finished.emit(False, f"Missing dependency: {missing}")
        except Exception as e:
            self.log.emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))

    def _train(self):
        import torch
        import torch.nn as nn
        from torch.utils.data import Dataset, DataLoader
        from transformers import DistilBertTokenizer, DistilBertModel
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder
        import numpy as np
        import pickle
        from pathlib import Path
        from collections import Counter

        # ── Load training data from SQLite ──────────────────────────────────
        self.log.emit("Loading categorised transactions from database...")
        txns = self.db.get_categorised_transactions()
        if len(txns) < 30:
            self.finished.emit(False,
                f"Only {len(txns)} categorised transactions found. "
                f"Need at least 30 for meaningful training.")
            return

        descriptions = [t["description"] for t in txns]
        categories = [t["category"] for t in txns]

        self.log.emit(f"Loaded {len(descriptions)} categorised transactions")

        # ── Encode labels ───────────────────────────────────────────────────
        label_encoder = LabelEncoder()
        encoded_labels = label_encoder.fit_transform(categories)
        n_classes = len(label_encoder.classes_)

        self.log.emit(f"Categories: {n_classes}")

        # Class distribution + warnings
        class_counts = Counter(categories)
        low_sample_cats = []
        for cat_id, count in sorted(class_counts.items(), key=lambda x: x[1]):
            cat_info = CATEGORIES.get(cat_id)
            name = cat_info.display_name if cat_info else cat_id
            marker = ""
            if count < 10:
                marker = "  (low samples)"
                low_sample_cats.append(f"{name}: {count}")
            self.log.emit(f"  {name}: {count} samples{marker}")

        if low_sample_cats:
            self.log.emit(f"\nWarning: {len(low_sample_cats)} categories have <10 samples — "
                          f"predictions may be unreliable for these.")

        # Filter out categories with < 2 samples (can't split)
        min_samples = 2
        classes_to_keep = [c for c, cnt in class_counts.items() if cnt >= min_samples]
        if len(classes_to_keep) < n_classes:
            removed = n_classes - len(classes_to_keep)
            self.log.emit(f"\nRemoving {removed} categories with <{min_samples} samples")
            mask = [c in classes_to_keep for c in categories]
            descriptions = [d for d, keep in zip(descriptions, mask) if keep]
            categories = [c for c, keep in zip(categories, mask) if keep]

            # Re-encode
            label_encoder = LabelEncoder()
            encoded_labels = label_encoder.fit_transform(categories)
            n_classes = len(label_encoder.classes_)

        # ── Train/val split ─────────────────────────────────────────────────
        use_validation = len(descriptions) >= 40 and min(Counter(encoded_labels).values()) >= 2
        if use_validation:
            try:
                X_train, X_val, y_train, y_val = train_test_split(
                    descriptions, encoded_labels, test_size=0.2,
                    random_state=42, stratify=encoded_labels
                )
            except ValueError:
                X_train, X_val, y_train, y_val = train_test_split(
                    descriptions, encoded_labels, test_size=0.2, random_state=42
                )
        else:
            X_train, y_train = descriptions, encoded_labels
            X_val, y_val = [], []
            self.log.emit("Too few samples for validation split — using all data for training")

        self.log.emit(f"\nTraining: {len(X_train)} samples"
                      + (f", Validation: {len(X_val)} samples" if use_validation else ""))

        # ── Tokenizer ───────────────────────────────────────────────────────
        self.log.emit("Loading DistilBERT tokenizer...")
        tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')

        # ── Dataset class (inline) ──────────────────────────────────────────
        class ExpenseDataset(Dataset):
            def __init__(self, descs, labels, tok, max_length=128):
                self.descs = descs
                self.labels = labels
                self.tok = tok
                self.max_length = max_length

            def __len__(self):
                return len(self.descs)

            def __getitem__(self, idx):
                enc = self.tok(
                    str(self.descs[idx]),
                    add_special_tokens=True, max_length=self.max_length,
                    padding='max_length', truncation=True,
                    return_attention_mask=True, return_tensors='pt'
                )
                return {
                    'input_ids': enc['input_ids'].flatten(),
                    'attention_mask': enc['attention_mask'].flatten(),
                    'label': torch.tensor(self.labels[idx], dtype=torch.long)
                }

        # ── Model class (inline) ────────────────────────────────────────────
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

        # ── Create data loaders ─────────────────────────────────────────────
        train_dataset = ExpenseDataset(X_train, y_train, tokenizer)
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)

        if use_validation:
            val_dataset = ExpenseDataset(X_val, y_val, tokenizer)
            val_loader = DataLoader(val_dataset, batch_size=self.batch_size)

        # ── Device ──────────────────────────────────────────────────────────
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.log.emit(f"Device: {device}\n")

        # ── Init model ──────────────────────────────────────────────────────
        self.log.emit("Initialising DistilBERT model...")
        model = ExpenseClassifier(n_cls=n_classes).to(device)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate)

        # ── Training loop ───────────────────────────────────────────────────
        model_path = Path(self.model_dir)
        model_path.mkdir(exist_ok=True)
        best_val_acc = 0.0

        self.log.emit(f"Starting training: {self.epochs} epochs, batch size {self.batch_size}\n")

        for epoch in range(self.epochs):
            if self._stop:
                self.log.emit("\nTraining stopped by user.")
                self.finished.emit(False, "Stopped by user")
                return

            # Train phase
            model.train()
            train_loss = 0
            train_correct = 0
            train_total = 0

            for batch in train_loader:
                if self._stop:
                    break
                input_ids = batch['input_ids'].to(device)
                attention_mask = batch['attention_mask'].to(device)
                labels = batch['label'].to(device)

                optimizer.zero_grad()
                outputs = model(input_ids, attention_mask)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()
                _, predicted = torch.max(outputs, 1)
                train_total += labels.size(0)
                train_correct += (predicted == labels).sum().item()

            train_acc = 100 * train_correct / train_total if train_total else 0
            avg_loss = train_loss / len(train_loader) if train_loader else 0

            status = f"Epoch {epoch + 1}/{self.epochs} — Loss: {avg_loss:.4f}, Train Acc: {train_acc:.1f}%"

            # Validation phase
            if use_validation:
                model.eval()
                val_correct = 0
                val_total = 0
                with torch.no_grad():
                    for batch in val_loader:
                        input_ids = batch['input_ids'].to(device)
                        attention_mask = batch['attention_mask'].to(device)
                        labels = batch['label'].to(device)
                        outputs = model(input_ids, attention_mask)
                        _, predicted = torch.max(outputs, 1)
                        val_total += labels.size(0)
                        val_correct += (predicted == labels).sum().item()

                val_acc = 100 * val_correct / val_total if val_total else 0
                status += f", Val Acc: {val_acc:.1f}%"

                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    torch.save({
                        'model_state_dict': model.state_dict(),
                        'label_encoder': label_encoder,
                        'n_classes': n_classes
                    }, model_path / 'best_model.pt')
                    status += " (saved)"
            else:
                # No validation — save every epoch
                torch.save({
                    'model_state_dict': model.state_dict(),
                    'label_encoder': label_encoder,
                    'n_classes': n_classes
                }, model_path / 'best_model.pt')

            self.log.emit(status)
            self.progress.emit(epoch + 1, self.epochs, status)

        # ── Save tokenizer + label encoder ──────────────────────────────────
        tokenizer.save_pretrained(model_path / 'tokenizer')
        with open(model_path / 'label_encoder.pkl', 'wb') as f:
            pickle.dump(label_encoder, f)

        summary = f"Training complete! {n_classes} categories"
        if use_validation:
            summary += f", best val accuracy: {best_val_acc:.1f}%"
        summary += f" — model saved to {model_path}"

        self.log.emit(f"\n{summary}")
        self.finished.emit(True, summary)
