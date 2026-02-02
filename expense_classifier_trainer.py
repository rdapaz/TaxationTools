import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import DistilBertTokenizer, DistilBertModel
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import numpy as np
import json
import argparse
from pathlib import Path
from typing import List, Tuple
import pickle


class ExpenseDataset(Dataset):
    def __init__(self, descriptions: List[str], labels: List[int], tokenizer, max_length=128):
        self.descriptions = descriptions
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.descriptions)

    def __getitem__(self, idx):
        description = str(self.descriptions[idx])
        label = self.labels[idx]

        encoding = self.tokenizer(
            description,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )

        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'label': torch.tensor(label, dtype=torch.long)
        }


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

        pooled_output = outputs.last_hidden_state[:, 0]  # CLS token
        output = self.dropout(pooled_output)
        return self.classifier(output)


def load_data_from_excel(excel_path: str) -> Tuple[List[str], List[str]]:
    """Load all classified transactions from Excel file (all sheets)"""
    descriptions = []
    categories = []

    xls = pd.ExcelFile(excel_path)

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)

        # Filter rows with valid categories (not empty and not containing emoji)
        df = df[df['Category'].notna()]
        df = df[~df['Category'].str.contains('🤖', na=False)]

        for _, row in df.iterrows():
            desc = row['Description']
            cat = row['Category'].strip().lower()

            # Skip if category is empty
            if cat:
                descriptions.append(desc)
                categories.append(cat)

    return descriptions, categories


def train_model(
        descriptions: List[str],
        categories: List[str],
        epochs: int = 10,
        batch_size: int = 16,
        learning_rate: float = 2e-5,
        model_dir: str = "models"
):
    """Train the expense classifier model"""

    # Create model directory
    model_path = Path(model_dir)
    model_path.mkdir(exist_ok=True)

    # Encode labels
    label_encoder = LabelEncoder()
    encoded_labels = label_encoder.fit_transform(categories)
    n_classes = len(label_encoder.classes_)

    print(f"Training on {len(descriptions)} transactions")
    print(f"Number of categories: {n_classes}")
    print(f"Categories: {list(label_encoder.classes_)}")

    # Check class distribution
    from collections import Counter
    class_counts = Counter(encoded_labels)
    print(f"\nClass distribution:")
    for class_id, count in sorted(class_counts.items()):
        class_name = label_encoder.inverse_transform([class_id])[0]
        print(f"  {class_name}: {count} samples")

    # Filter out classes with too few samples (< 2)
    min_samples = 2
    classes_to_keep = [class_id for class_id, count in class_counts.items() if count >= min_samples]

    if len(classes_to_keep) < n_classes:
        print(f"\n⚠️  Removing {n_classes - len(classes_to_keep)} categories with < {min_samples} samples")

        # Filter data
        mask = np.isin(encoded_labels, classes_to_keep)
        descriptions = [d for d, keep in zip(descriptions, mask) if keep]
        encoded_labels = encoded_labels[mask]

        # Re-encode labels to have consecutive indices
        unique_labels = np.unique(encoded_labels)
        label_mapping = {old: new for new, old in enumerate(unique_labels)}
        encoded_labels = np.array([label_mapping[label] for label in encoded_labels])

        # Update label encoder
        kept_classes = [label_encoder.classes_[i] for i in classes_to_keep]
        label_encoder.classes_ = np.array(kept_classes)
        n_classes = len(kept_classes)

        print(f"Training with {n_classes} categories: {list(label_encoder.classes_)}")

    # Determine if we have enough data for validation split
    if len(descriptions) < 20 or min(Counter(encoded_labels).values()) < 2:
        print("\n⚠️  Too few samples for train/validation split")
        print("Training without validation set (using all data for training)")

        X_train = descriptions
        y_train = encoded_labels
        X_val = []
        y_val = []
        use_validation = False
    else:
        # Split data with stratification
        try:
            X_train, X_val, y_train, y_val = train_test_split(
                descriptions, encoded_labels, test_size=0.2, random_state=42, stratify=encoded_labels
            )
            use_validation = True
        except ValueError:
            # If stratification still fails, split without it
            print("\n⚠️  Cannot stratify with current data distribution")
            print("Using random split instead")
            X_train, X_val, y_train, y_val = train_test_split(
                descriptions, encoded_labels, test_size=0.2, random_state=42
            )
            use_validation = True

    print(f"\nTraining samples: {len(X_train)}")
    if use_validation:
        print(f"Validation samples: {len(X_val)}")

    # Initialize tokenizer
    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')

    # Create datasets
    train_dataset = ExpenseDataset(X_train, y_train, tokenizer)
    if use_validation:
        val_dataset = ExpenseDataset(X_val, y_val, tokenizer)

    # Create dataloaders
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    if use_validation:
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

    # Setup device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}\n")

    # Initialize model
    model = ExpenseClassifier(n_classes=n_classes)
    model = model.to(device)

    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    # Training loop
    best_val_acc = 0.0

    for epoch in range(epochs):
        # Training phase
        model.train()
        train_loss = 0
        train_correct = 0
        train_total = 0

        for batch in train_loader:
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

        train_acc = 100 * train_correct / train_total
        avg_train_loss = train_loss / len(train_loader)

        print(f"Epoch {epoch + 1}/{epochs}")
        print(f"  Train Loss: {avg_train_loss:.4f}, Train Acc: {train_acc:.2f}%")

        # Validation phase (if we have validation data)
        if use_validation:
            model.eval()
            val_loss = 0
            val_correct = 0
            val_total = 0

            with torch.no_grad():
                for batch in val_loader:
                    input_ids = batch['input_ids'].to(device)
                    attention_mask = batch['attention_mask'].to(device)
                    labels = batch['label'].to(device)

                    outputs = model(input_ids, attention_mask)
                    loss = criterion(outputs, labels)

                    val_loss += loss.item()
                    _, predicted = torch.max(outputs, 1)
                    val_total += labels.size(0)
                    val_correct += (predicted == labels).sum().item()

            val_acc = 100 * val_correct / val_total
            avg_val_loss = val_loss / len(val_loader)

            print(f"  Val Loss: {avg_val_loss:.4f}, Val Acc: {val_acc:.2f}%")

            # Save best model based on validation
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                torch.save({
                    'model_state_dict': model.state_dict(),
                    'label_encoder': label_encoder,
                    'n_classes': n_classes
                }, model_path / 'best_model.pt')
                print(f"  ✓ Saved best model (val_acc: {val_acc:.2f}%)")
        else:
            # No validation - save model every epoch
            torch.save({
                'model_state_dict': model.state_dict(),
                'label_encoder': label_encoder,
                'n_classes': n_classes
            }, model_path / 'best_model.pt')
            print(f"  ✓ Saved model")

    # Save tokenizer and label encoder separately for easy loading
    tokenizer.save_pretrained(model_path / 'tokenizer')
    with open(model_path / 'label_encoder.pkl', 'wb') as f:
        pickle.dump(label_encoder, f)

    print(f"\n✓ Training complete!")
    if use_validation:
        print(f"  Best validation accuracy: {best_val_acc:.2f}%")
    print(f"  Model saved to: {model_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Train expense classifier from Excel data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train model from Excel file
  python expense_classifier_trainer.py -i expenses.xlsx

  # Train with custom parameters
  python expense_classifier_trainer.py -i expenses.xlsx -e 20 -b 32 -lr 1e-5

  # Specify output directory
  python expense_classifier_trainer.py -i expenses.xlsx -o my_models
        """
    )

    parser.add_argument('-i', '--input', required=True,
                        help='Path to Excel file with classified transactions')
    parser.add_argument('-e', '--epochs', type=int, default=10,
                        help='Number of training epochs (default: 10)')
    parser.add_argument('-b', '--batch-size', type=int, default=16,
                        help='Batch size (default: 16)')
    parser.add_argument('-lr', '--learning-rate', type=float, default=2e-5,
                        help='Learning rate (default: 2e-5)')
    parser.add_argument('-o', '--output', default='models',
                        help='Output directory for model (default: models)')

    args = parser.parse_args()

    print("Loading data from Excel...")
    descriptions, categories = load_data_from_excel(args.input)

    if len(descriptions) < 20:
        print(f"Warning: Only {len(descriptions)} samples found. Need at least 20-30 for meaningful training.")
        return

    print(f"Loaded {len(descriptions)} classified transactions\n")

    train_model(
        descriptions=descriptions,
        categories=categories,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        model_dir=args.output
    )


if __name__ == "__main__":
    main()