import pandas as pd
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path


def parse_date(date_str):
    """Parse date from Excel format (DD/MM/YYYY) to database format (YYYY-MM-DD)"""
    try:
        dt = datetime.strptime(str(date_str).strip(), '%d/%m/%Y')
        return dt.strftime('%Y-%m-%d')
    except:
        # Try alternate format if it's already in YYYY-MM-DD
        return str(date_str).strip()


def excel_to_processed_table(excel_path: str, db_path: str):
    """Load Excel data into processed_transactions table"""

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create processed_transactions table
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS processed_transactions
                   (
                       id               INTEGER PRIMARY KEY AUTOINCREMENT,
                       trans_date       TEXT NOT NULL,
                       description      TEXT NOT NULL,
                       reference_number TEXT NOT NULL,
                       amount           REAL NOT NULL,
                       category         TEXT
                   )
                   """)

    # Clear existing data
    cursor.execute("DELETE FROM processed_transactions")
    print("Cleared existing processed_transactions table")

    # Load Excel file
    print(f"Reading Excel file: {excel_path}\n")
    xls = pd.ExcelFile(excel_path)

    total_rows = 0

    for sheet_name in xls.sheet_names:
        print(f"Processing sheet: {sheet_name}")
        df = pd.read_excel(excel_path, sheet_name=sheet_name)

        # Check required columns
        required_cols = ['Date', 'Description', 'Reference', 'Amount', 'Category']
        if not all(col in df.columns for col in required_cols):
            print(f"  ⚠️  Skipping - missing required columns")
            continue

        sheet_rows = 0

        for idx, row in df.iterrows():
            # Skip header rows or empty rows
            if pd.isna(row['Date']) or pd.isna(row['Amount']):
                continue

            # Parse data
            date_str = str(row['Date']).strip()
            description = str(row['Description']).strip()
            reference = str(row['Reference']).strip() if pd.notna(row['Reference']) else ''
            amount = float(row['Amount'])
            category = str(row['Category']).strip() if pd.notna(row['Category']) else ''

            # Remove emoji if present
            category = category.replace('🤖', '').strip()

            # Convert date format
            db_date = parse_date(date_str)

            # Insert into database
            cursor.execute("""
                           INSERT INTO processed_transactions (trans_date, description, reference_number, amount, category)
                           VALUES (?, ?, ?, ?, ?)
                           """, (db_date, description, reference, amount, category))

            sheet_rows += 1
            total_rows += 1

        print(f"  Inserted {sheet_rows} rows")

    # Commit changes
    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM processed_transactions")
    count = cursor.fetchone()[0]

    print(f"\n{'=' * 60}")
    print(f"✓ SUCCESS")
    print(f"Total rows inserted: {total_rows}")
    print(f"Verified count in database: {count}")

    # Show category summary
    cursor.execute("""
                   SELECT category, COUNT(*) as count
                   FROM processed_transactions
                   WHERE category IS NOT NULL
                     AND category != ''
                   GROUP BY category
                   ORDER BY count DESC
                   """)

    print(f"\nCategory summary:")
    for cat, cnt in cursor.fetchall():
        print(f"  {cat:30s}: {cnt:4d}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Load Excel data into processed_transactions table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load Excel into processed_transactions table
  python excel_to_processed_table.py -i expenses.xlsx -d expenses.db
        """
    )

    parser.add_argument('-i', '--input', required=True,
                        help='Path to Excel file')
    parser.add_argument('-d', '--database', required=True,
                        help='Path to SQLite database file')

    args = parser.parse_args()

    # Validate files exist
    if not Path(args.input).exists():
        print(f"Error: Excel file not found: {args.input}")
        return

    if not Path(args.database).exists():
        print(f"Error: Database file not found: {args.database}")
        return

    excel_to_processed_table(args.input, args.database)


if __name__ == "__main__":
    main()