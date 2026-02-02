import torch
import argparse
import sqlite3
from transformers import DistilBertTokenizer, DistilBertModel
import torch.nn as nn
import pickle
from pathlib import Path
from typing import List, Tuple


class ExpenseClassifier(nn.Module):
    def __init__(self, n_classes, dropout=0.3):
        super(ExpenseClassifier, self).__init__()
        self.bert = DistilBertModel.from_pretrained('distilbert-base-uncased')
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(self.bert.config.hidden_size, n_classes)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(
            input_ids=input_ids,
            attention_mask=attention_mask
        )

        pooled_output = outputs.last_hidden_state[:, 0]
        output = self.dropout(pooled_output)
        return self.classifier(output)


def load_model(model_dir: str):
    """Load trained model, tokenizer, and label encoder"""
    model_path = Path(model_dir)

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

    model = ExpenseClassifier(n_classes=n_classes)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()

    return model, tokenizer, label_encoder


def predict_category(description: str, model, tokenizer, label_encoder, device) -> str:
    """Predict category for a single description"""
    encoding = tokenizer(
        description,
        add_special_tokens=True,
        max_length=128,
        padding='max_length',
        truncation=True,
        return_attention_mask=True,
        return_tensors='pt'
    )

    input_ids = encoding['input_ids'].to(device)
    attention_mask = encoding['attention_mask'].to(device)

    with torch.no_grad():
        outputs = model(input_ids, attention_mask)
        _, predicted = torch.max(outputs, 1)

    category = label_encoder.inverse_transform([predicted.item()])[0]
    return category


def get_unclassified_transactions(db_path: str, reclassify: bool = False) -> List[Tuple[int, str, float]]:
    """Get transactions that haven't been classified by the local model"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if reclassify:
        # Include both unclassified (0) and AI-classified (1) transactions
        cursor.execute("""
                       SELECT id, description, amount
                       FROM transactions
                       WHERE ai_classified IN (0, 1)
                       ORDER BY trans_date DESC
                       """)
    else:
        # Only unclassified transactions
        cursor.execute("""
                       SELECT id, description, amount
                       FROM transactions
                       WHERE (category IS NULL OR category = '')
                         AND ai_classified = 0
                       ORDER BY trans_date DESC
                       """)

    transactions = cursor.fetchall()
    conn.close()

    return transactions


def update_transaction_category(db_path: str, transaction_id: int, category: str):
    """Update transaction with predicted category"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
                   UPDATE transactions
                   SET category      = ?,
                       ai_classified = 2
                   WHERE id = ?
                   """, (category, transaction_id))

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Classify expenses using trained model',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Classify only unclassified transactions
  python expense_classifier_predictor.py -d expenses.db -m models

  # Re-classify AI predictions with local model (keeps manual corrections)
  python expense_classifier_predictor.py -d expenses.db -m models --reclassify

  # Dry run (don't update database)
  python expense_classifier_predictor.py -d expenses.db -m models --dry-run

  # Dry run with reclassification
  python expense_classifier_predictor.py -d expenses.db -m models --reclassify --dry-run
        """
    )

    parser.add_argument('-d', '--database', required=True,
                        help='Path to SQLite database file')
    parser.add_argument('-m', '--model-dir', default='models',
                        help='Directory containing trained model (default: models)')
    parser.add_argument('--reclassify', action='store_true',
                        help='Re-classify AI predictions (ai_classified=1) with local model')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show predictions without updating database')

    args = parser.parse_args()

    # Setup device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # Load model
    print("Loading model...")
    model, tokenizer, label_encoder = load_model(args.model_dir)
    model = model.to(device)
    print(f"✓ Model loaded from: {args.model_dir}")
    print(f"  Categories: {list(label_encoder.classes_)}\n")

    # Get unclassified transactions
    mode = "Re-classifying AI predictions and unclassified" if args.reclassify else "Classifying unclassified"
    print(f"{mode} transactions...")
    transactions = get_unclassified_transactions(args.database, args.reclassify)

    if len(transactions) == 0:
        if args.reclassify:
            print("✓ No unclassified or AI-classified transactions found")
        else:
            print("✓ No unclassified transactions found")
        return

    print(f"Found {len(transactions)} transactions to classify\n")

    if args.dry_run:
        print("DRY RUN MODE - No database updates will be made\n")

    if args.reclassify and not args.dry_run:
        print("⚠️  RECLASSIFY MODE - Will update AI predictions (ai_classified=1)\n")

    # Classify transactions
    classified = 0

    for i, (trans_id, description, amount) in enumerate(transactions, 1):
        category = predict_category(description, model, tokenizer, label_encoder, device)

        print(f"({i}/{len(transactions)}) ID {trans_id}: {description[:50]}... → {category}")

        if not args.dry_run:
            update_transaction_category(args.database, trans_id, category)
            classified += 1

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print("DRY RUN COMPLETE")
        print(f"Would classify: {classified} transactions")
    else:
        print("CLASSIFICATION COMPLETE")
        print(f"Successfully classified: {classified} transactions")
        print("(Note: ai_classified flag set to 2 for local model predictions)")


if __name__ == "__main__":
    main()