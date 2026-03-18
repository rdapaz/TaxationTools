# BudgetBuddy

A polished PySide6 desktop application for Australian household budgeting. Import bank transactions, classify them with AI, track spending against budgets, and visualise your finances.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green)
![License: MIT](https://img.shields.io/badge/license-MIT-brightgreen)

## Features

### Desktop GUI
- **Dashboard** — Monthly spending summary with stat cards and category breakdown charts
- **Transactions** — Searchable, sortable transaction list with inline category editing
- **Reports** — Visual spending reports with matplotlib charts (category, trend, monthly comparison)
- **Budgets** — Set monthly budgets per category with progress tracking and alerts
- **Settings** — Classification engine configuration, data import, model training, and data coverage overview

### AI Classification (Dual Engine)
- **Anthropic Claude API** — Cloud-based classification using `claude-sonnet-4-20250514` with batch processing
- **Local DistilBERT Model** — Train your own model from corrected data for free, offline classification
- **Smart Fallback** — If the selected engine is unavailable, automatically falls back to the other
- Toggle between engines from Settings with a single click

### Security
- **Keyring Integration** — API keys stored in Windows Credential Manager (or macOS Keychain / Linux Secret Service), never in config files
- Safe to share the app without exposing API credits

### 19 Budget Categories (9 Groups)

| Group | Categories |
|-------|-----------|
| Housing | Mortgage/Rent, Utilities, Home Maintenance |
| Transport | Fuel, Car Maintenance, Public Transport, Parking & Tolls |
| Food | Groceries, Dining Out |
| Personal | Clothing, Health & Medical, Personal Care |
| Financial | Insurance, Bank Fees & Interest |
| Lifestyle | Entertainment, Subscriptions |
| Family | Childcare & Education, Pets |
| Other | Other |
| — | Uncategorised |

### Quality of Life
- **Transaction Search** — Seamlessly search by description, date (`2026-02` for all Feb transactions), or category
- **Excel Export** — Export currently displayed transactions to styled `.xlsx` with one click or `Ctrl+E`
- **Keyboard Shortcuts** — `Ctrl+1` through `Ctrl+5` for instant tab navigation
- **Help System** — `(?)` buttons on every view and card, rendering a built-in markdown help file
- **Persistent Layout** — Window size and position remembered between launches

## Installation

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
git clone https://github.com/rdapaz/BudgetBuddy.git
cd BudgetBuddy
pip install -e .
```

### Key Dependencies
- `PySide6` — Qt GUI framework
- `anthropic` — Claude API client
- `torch` + `transformers` — Local DistilBERT model
- `matplotlib` — Charts and reports
- `openpyxl` — Excel export
- `keyring` — Secure API key storage
- `scikit-learn` — Model training utilities

## Usage

### Launch the App

```bash
python budgetbuddy.py
```

### Recommended Workflow

1. **Import** — Paste bank transactions from clipboard via Settings → Import
2. **Classify with Claude API** — Use the Anthropic engine to bulk-classify transactions
3. **Review & Correct** — Manually verify and fix any misclassifications in the Transactions tab
4. **Train Local Model** — Once you have enough corrected data, train DistilBERT from Settings
5. **Use Either Engine** — For future imports, use whichever engine you prefer

### Legacy CLI Tools

The original command-line tools are still available:

```bash
# Import from clipboard
python statement_manager.py -d expenses.db -a

# Classify with Go (concurrent)
go run classifier.go -d expenses.db -c config.json -w 10

# Export to Excel
python statement_manager.py -d expenses.db -e expenses.xlsx

# Train local model
python expense_classifier_trainer.py -i expenses.xlsx

# Predict with local model
python expense_classifier_predictor.py -d expenses.db -m models
```

## Project Structure

```
BudgetBuddy/
├── budgetbuddy.py              # App entry point
├── gui/
│   ├── main_window.py          # Main window with sidebar navigation
│   ├── categories.py           # 19 budget categories definition
│   ├── theme.py                # Colours, fonts, shared styles
│   ├── help.md                 # Built-in help documentation
│   ├── models/
│   │   ├── database.py         # SQLite data access layer
│   │   └── api_key.py          # Keyring-based API key management
│   ├── views/
│   │   ├── dashboard.py        # Monthly spending overview
│   │   ├── transactions.py     # Transaction list with search/export
│   │   ├── reports.py          # Charts and visual reports
│   │   ├── budgets.py          # Budget tracking per category
│   │   └── settings.py         # Engine config, import, training
│   ├── widgets/
│   │   ├── chart_canvas.py     # Matplotlib canvas widget
│   │   ├── stat_card.py        # Dashboard stat card widget
│   │   └── help_window.py      # Help dialog with HTML rendering
│   └── workers/
│       ├── classify_worker.py  # API + Local classification threads
│       └── train_worker.py     # DistilBERT training thread
├── statement_manager.py        # Legacy CLI import/export
├── classifier.go               # Legacy Go concurrent classifier
├── expense_classifier_trainer.py   # Legacy CLI trainer
├── expense_classifier_predictor.py # Legacy CLI predictor
└── pyproject.toml
```

## Configuration

- **API Key**: Stored securely via `keyring` — configure in Settings → Classification Engine
- **Engine Preference**: Saved in SQLite `app_settings` table
- **Window Geometry**: Saved via Qt's `QSettings` (Windows Registry)
- **No config files needed** — all settings managed through the GUI

## License

MIT
