# Taxation Tools

A suite of tools for managing and classifying credit card expenses for tax purposes.

## Features

- **Python Script** (`statement_manager.py`): Parse clipboard data, store in SQLite, export to Excel
- **Go Classifier** (`classifier.go`): Concurrent AI-powered classification using Claude API
- **PyTorch Trainer** (`expense_classifier_trainer.py`): Train local model from corrected data
- **Local Predictor** (`expense_classifier_predictor.py`): Classify expenses using trained model

## Setup

### Prerequisites

- Python 3.8+
- Go 1.20+
- Anthropic API key

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd TaxationTools
```

2. Install Python dependencies:
```bash
pip install pyperclip openpyxl anthropic torch transformers scikit-learn pandas
```

3. Install Go dependencies:
```bash
go mod tidy
```

4. Create `config.json` with your API key:
```json
{
  "anthropic_api_key": "sk-ant-your-key-here"
}
```

## Usage

### Basic Workflow

1. **Add transactions from clipboard:**
```bash
python statement_manager.py -d expenses.db -a
```

2. **Classify with AI (fast, concurrent):**
```bash
go run classifier.go -d expenses.db -c config.json -w 10
# Or use compiled binary:
.\classifier.exe -d expenses.db -c config.json -w 10
```

3. **Export to Excel for review:**
```bash
python statement_manager.py -d expenses.db -e expenses.xlsx
```

4. **Train local model from corrected data:**
```bash
python expense_classifier_trainer.py -i expenses.xlsx
```

5. **Use local model for future classifications:**
```bash
python expense_classifier_predictor.py -d expenses.db -m models
```

## Categories

- `software`: Software purchases, SaaS subscriptions
- `professional membership`: Professional organizations, certifications
- `technical library`: Books, technical publications
- `magazines and journals`: Technical magazines, subscriptions
- `training`: Courses, conferences, workshops
- `not work related`: Personal purchases
- `other`: Work-related but uncategorized

## Building

### Go Binary
```bash
go build -o classifier.exe classifier.go
```

## Configuration

Create a `config.json` file (not tracked in git):
```json
{
  "anthropic_api_key": "your-api-key-here"
}
```

## License

MIT

## Notes

- Database files (`.db`) are not tracked in git
- Config files with API keys are not tracked in git
- Excel output files are not tracked in git
- Trained models are not tracked in git (can be large)


# Add transactions WITHOUT AI classification
python statement_manager.py -d expenses.db -a

# Add transactions WITH AI classification
python statement_manager.py -d expenses.db -c config.json -a --classify

# Export to Excel (AI classifications shown with 🤖 emoji)
python statement_manager.py -d expenses.db -e expenses.xlsx

# Complete workflow: add with AI, then export
python statement_manager.py -d expenses.db -c config.json -a --classify -e expenses.xlsx

# Conservative (should work for everyone)
.\classifier.exe -d expenses.db -c config.json -w 5

# Moderate (good for Build Tier 1+)
.\classifier.exe -d expenses.db -c config.json -w 20

# Aggressive (Build Tier 2+)
.\classifier.exe -d expenses.db -c config.json -w 50
```

If you hit rate limits, you'll see errors like:
```
✗ ID 123 failed: rate_limit_error: requests per minute limit exceeded

# Workflow
### 1. Add transactions (Python)
python statement_manager.py -d expenses.db -a

### 2. Classify with Claude AI (Go - fast)
.\classifier.exe -d expenses.db -c config.json -w 10

### 3. Export to Excel
python statement_manager.py -d expenses.db -e expenses.xlsx

### 4. Manually review/correct categories in Excel

### 5. Train your local model from corrected data
python expense_classifier_trainer.py -i expenses.xlsx

### 6. Use your trained model for future classifications (free!)
python expense_classifier_predictor.py -d expenses.db -m models

### 7. Export final results
python statement_manager.py -d expenses.db -e final_expenses.xlsx



# Default: Only classify empty/unclassified (ai_classified=0)
python expense_classifier_predictor.py -d expenses.db -m models

# Re-classify AI predictions too (ai_classified=0 and 1)
python expense_classifier_predictor.py -d expenses.db -m models --reclassify

# Test what would happen without updating
python expense_classifier_predictor.py -d expenses.db -m models --reclassify --dry-run
