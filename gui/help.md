# BudgetBuddy Help

## Classification Engine

BudgetBuddy can classify your transactions automatically using two different engines:

### Anthropic API (Claude)

Uses Claude AI via the internet to classify each transaction. This is typically more accurate, especially for unusual transactions, but costs a small amount per request (~$0.001 per transaction).

**To set up:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Paste it into the API Key field and click **Save Key**
3. The key is stored securely in your OS credential manager (Windows Credential Manager) — it is NOT stored in any file, so it's safe to share this app with others

### Local Model (DistilBERT)

Uses a small neural network trained on YOUR data that runs entirely on your computer. It's free, instant, and works offline — but needs to be trained first.

**Recommended workflow:**
1. Import all your historical statements
2. Use the API to classify everything
3. Review and correct any mistakes in the Transactions view
4. Train the local model (Settings > Local Model Training)
5. Future imports can use the local model for free

**Accuracy:** The local model's accuracy depends on how much training data you have. With 100+ examples per category, expect 85-95% accuracy. Categories with fewer than 10 examples will be less reliable.

---

## Import Transactions

Import transactions by copying your bank/credit card statement text to the clipboard.

**Supported format:** Australian bank statements using 6-digit dates (DDMMYY). For example:
```
070325 WOOLWORTHS 1234 SYDNEY 45.67
               Card 1234567890123456789
080325 SHELL COLES EXPRESS MARRI 62.30
```

**Import** — Adds transactions to the database. Duplicates (same date, reference, amount) are automatically skipped.

**Import + Auto-Classify** — Imports and immediately classifies using whichever engine is selected above.

**Classify Last Import** — Appears after an import. Classifies only the newly imported transactions (useful when catching up on multiple months).

---

## AI Classification

Runs the selected classification engine on all uncategorised transactions.

- The engine used depends on your selection in **Classification Engine** above
- If your selected engine isn't available (no API key / no trained model), BudgetBuddy will fall back to the other engine
- Classification runs in the background — you can stop it at any time
- Transactions are updated in batches, so even if you stop early, some will have been classified

**Tip:** After classification, review the results in the **Transactions** view. Any corrections you make become training data for the local model.

---

## Local Model Training

Train a DistilBERT model on your categorised transactions.

### Requirements
- At least 30 categorised transactions (more is better)
- Python packages: `torch`, `transformers`, `scikit-learn` (`pip install torch transformers scikit-learn`)

### Training Parameters
- **Epochs** — Number of full passes through the training data. Default 10 is usually good. Increase to 15-20 if accuracy is low.
- Training takes **5-15 minutes** on CPU, faster with a GPU

### Category Warnings
- Categories with fewer than 10 examples will show a warning
- The model may confuse similar categories (e.g., "Groceries" vs "Household") if there aren't enough distinct examples
- **Category mismatch** warning appears if the trained model has different categories than the app — this means you should retrain

### When to Retrain
- After manually correcting a significant number of classifications
- After importing and classifying new months of data
- When the app warns about a category mismatch
- Periodically (e.g., every few months) as your spending patterns change

---

## Data Coverage

A visual grid showing how many transactions you have per month.

- **Green** (10+ transactions) — Normal month, good coverage
- **Amber** (<10 transactions) — Partial month, may be incomplete
- **Red** (0 transactions) — Gap in data, likely a missing statement import

**Tip:** Australian bank statements typically run from ~7th to ~6th of the following month. If a calendar month shows as a gap, the transactions may be split across two statement periods.

---

## Categories

BudgetBuddy uses 19 expense categories across 9 groups:

| Group | Categories |
|-------|-----------|
| **Home** | Housing, Utilities |
| **Transport** | Fuel, Car, Public Transport |
| **Living** | Groceries, Household, Dining Out |
| **Health** | Health, Fitness |
| **Family** | Children |
| **Lifestyle** | Entertainment, Clothing, Personal Care |
| **Financial** | Insurance, Fees & Charges |
| **Work** | Work Deductible (tax deductible) |
| **Other** | Other, Uncategorised |

Categories marked as **tax deductible** are tracked separately for end-of-year tax reporting.

---

## Dashboard

The dashboard shows a summary of your spending for a selected month.

- **Month picker** — Select any month from your data range. Months with no data are shown but labelled
- **Smart default** — Automatically selects the most recent month with 50+ transactions (skips partial months)
- **Stat cards** — Total spending, transaction count, daily average, top category, and budget usage
- **Monthly bar chart** — Shows spending over recent months with the selected month highlighted
- **Category breakdown** — Top categories with spending amounts and budget progress bars (if budgets are set)

---

## Transactions

Browse, search, filter, and edit all your transactions.

### Searching

The search box matches against **description**, **date**, and **category** simultaneously:

- Type `woolworths` to find all Woolworths transactions
- Type `2026-02` to show all February 2026 transactions
- Type `groceries` to find all grocery-categorised transactions
- Type `15/03` to find transactions on the 15th of March

### Filtering

- **Category dropdown** — Filter to a single category
- **Date range** — Set From/To dates to narrow the view (defaults to your full data range)
- Filters and search combine — e.g., search for "shell" within the "Fuel" category

### Editing Categories

- **Single transaction** — Double-click the Category cell to get a dropdown, select the new category
- **Bulk edit** — Select multiple rows (Ctrl+click or Shift+click), choose a category from the "Set to:" dropdown, and click **Apply**

### Exporting

Click **Export to Excel** to save the currently displayed transactions (after all filters/search) to an .xlsx file. The export includes Date, Description, Amount, and Category columns.

---

## Reports

Analyse your spending patterns with charts and tax summaries.

### Controls

- **Focus month** — Select which month to compare (defaults to the most recent)
- **Trend range** — How many months to include in the trend chart (3, 6, or 12)
- **Tax year** — Australian financial year (July to June) for the tax deductible summary

### Tax Deductible Summary

Four stat cards at the top show:

- **Tax Deductible (FY)** — Total tax-deductible spending for the selected financial year
- **Deductible Items** — Number of tax-deductible transactions
- **Avg Monthly Spend** — Your average total monthly spending
- **Projected Annual** — Projected annual spending based on your average

### Monthly Comparison

A paired bar chart showing the focus month vs the previous month, broken down by category. Useful for spotting unusual spending spikes.

### Spending Trend

A line chart showing your top 6 categories over the selected trend range. Each category is colour-coded. Look for upward or downward trends.

### Current vs 3-Month Average

A horizontal bar chart comparing the focus month's spending to the rolling 3-month average per category. Helps identify whether a given month was typical or an outlier.

---

## Budgets

Set monthly budget targets for each category.

### Setting Budgets

- **Auto-Fill** — Seed budgets from your historical spending averages (choose 3, 6, or 12 months). Amounts are rounded to the nearest $50
- **Manual entry** — Use the spinners to set each category's budget. Use the up/down arrows or type directly
- **Save All** — Saves all budgets to the database. The button flashes green to confirm
- Categories under the "Other" group (Other, Uncategorised) are excluded from budgets

### Charts

- **Budget Allocation pie chart** — Live preview of how your total budget is split across categories. Updates instantly as you adjust spinners
- **Budget vs Actual** — Horizontal bar chart comparing your budget to actual spending for the most recent month. Categories where you've overspent are shown in red

### Tips

- Start with Auto-Fill from 3-month averages, then round up categories where you want a buffer
- The total budget is shown in the top-right of the seed bar
- Budget data is used on the Dashboard to show a budget usage percentage and progress bars per category

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+1 | Dashboard |
| Ctrl+2 | Transactions |
| Ctrl+3 | Reports |
| Ctrl+4 | Budgets |
| Ctrl+5 | Settings |
| Ctrl+E | Export transactions to Excel (when on Transactions tab) |
