import pandas as pd
import sqlite3
import argparse
from pathlib import Path


def sync_excel_to_database(excel_path: str, db_path: str, dry_run: bool = False):
    """Sync category corrections from Excel back to database using ID"""

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Load Excel file
    print(f"Reading Excel file: {excel_path}")
    xls = pd.ExcelFile(excel_path)

    total_updated = 0
    total_processed = 0
    errors = []

    for sheet_name in xls.sheet_names:
        print(f"\nProcessing sheet: {sheet_name}")
        df = pd.read_excel(excel_path, sheet_name=sheet_name)

        # Check for ID column
        if 'ID' not in df.columns:
            print(f"  ⚠️  Skipping - no ID column (old format)")
            continue

        # Check required columns
        required_cols = ['ID', 'Category']
        if not all(col in df.columns for col in required_cols):
            print(f"  ⚠️  Skipping - missing required columns")
            continue

        sheet_updated = 0

        for idx, row in df.iterrows():
            total_processed += 1

            # Get ID and category
            trans_id = int(row['ID'])
            category = str(row['Category']).strip() if pd.notna(row['Category']) else ''

            # Remove emoji if present
            category = category.replace('🤖', '').strip()

            # Skip if no category
            if not category:
                continue

            # Get current category from database
            cursor.execute("""
                           SELECT category, ai_classified
                           FROM transactions
                           WHERE id = ?
                           """, (trans_id,))

            result = cursor.fetchone()

            if result:
                current_category, ai_classified = result

                # Only update if category has changed
                if current_category != category:
                    if not dry_run:
                        # Update category, set ai_classified to 0 (manual correction)
                        cursor.execute("""
                                       UPDATE transactions
                                       SET category      = ?,
                                           ai_classified = 0
                                       WHERE id = ?
                                       """, (category, trans_id))

                    print(f"  ✓ ID {trans_id}: '{current_category or '(empty)'}' → '{category}'")
                    sheet_updated += 1
                    total_updated += 1
            else:
                errors.append(f"Row {idx + 2}: ID {trans_id} not found in database")

        if sheet_updated > 0:
            print(f"  Updated {sheet_updated} transactions")
        else:
            print(f"  No changes needed")

    # Commit changes
    if not dry_run:
        conn.commit()
        print(f"\n✓ Database updated")

    conn.close()

    # Summary
    print(f"\n{'=' * 60}")
    if dry_run:
        print("DRY RUN COMPLETE")
        print(f"Would update: {total_updated} transactions")
    else:
        print("SYNC COMPLETE")
        print(f"Total processed: {total_processed} rows")
        print(f"Total updated: {total_updated} transactions")

    if errors:
        print(f"\nErrors/Warnings ({len(errors)}):")
        for error in errors[:10]:
            print(f"  ⚠️  {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")


def main():
    parser = argparse.ArgumentParser(
        description='Sync category corrections from Excel back to database using ID column',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync corrections from Excel to database
  python excel_to_db_sync.py -i expenses.xlsx -d expenses.db

  # Dry run to see what would change
  python excel_to_db_sync.py -i expenses.xlsx -d expenses.db --dry-run

Workflow:
  1. Export: python statement_manager.py -d expenses.db -e expenses.xlsx
  2. Edit categories in Excel (ID column is read-only reference)
  3. Sync back: python excel_to_db_sync.py -i expenses.xlsx -d expenses.db
        """
    )

    parser.add_argument('-i', '--input', required=True,
                        help='Path to Excel file with corrections')
    parser.add_argument('-d', '--database', required=True,
                        help='Path to SQLite database file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be updated without modifying database')

    args = parser.parse_args()

    # Validate files exist
    if not Path(args.input).exists():
        print(f"Error: Excel file not found: {args.input}")
        return

    if not Path(args.database).exists():
        print(f"Error: Database file not found: {args.database}")
        return

    if args.dry_run:
        print("DRY RUN MODE - No database updates will be made\n")

    sync_excel_to_database(args.input, args.database, args.dry_run)


if __name__ == "__main__":
    main()