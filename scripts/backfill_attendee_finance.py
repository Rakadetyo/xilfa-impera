#!/usr/bin/env python3
"""
Backfill slot_type and amount_paid for existing game_attendee rows.

Logic:
  slot_type  — 'member' if player has a member row matching the game's month/year period,
               'non-member' otherwise. Only rows where slot_type IS NULL are updated.

  amount_paid — set for rows where is_paid = 1 AND amount_paid IS NULL OR amount_paid = 0,
                using price_per_member (if slot_type = 'member') or price_per_person.
                Rows with is_paid = 0 are left at 0.

Run:
    python scripts/backfill_attendee_finance.py [--dry-run]
"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db

MONTHS = ['January','February','March','April','May','June','July','August',
          'September','October','November','December']


def game_period(dt_str: str) -> str | None:
    try:
        dt = datetime.strptime(str(dt_str)[:10], "%Y-%m-%d")
        return f"{MONTHS[dt.month - 1]} {dt.year}"
    except ValueError:
        return None


def run(dry_run: bool = False):
    prefix = "[DRY RUN] " if dry_run else ""
    conn = get_db()
    cursor = conn.cursor()

    # Fetch all attendees with unresolved slot_type (NULL or legacy 'regular' default)
    cursor.execute("""
        SELECT ga.id, ga.player_id, ga.game_id, ga.is_paid, ga.amount_paid,
               g.datetime, g.price_per_member, g.price_per_person
        FROM game_attendee ga
        JOIN game g ON ga.game_id = g.id
        WHERE ga.slot_type IS NULL OR ga.slot_type = 'regular'
    """)
    rows = cursor.fetchall()

    print(f"{prefix}Found {len(rows)} attendee rows with NULL or legacy 'regular' slot_type.")

    slot_updated = 0
    amount_updated = 0
    skipped = 0

    for row in rows:
        period = game_period(row["datetime"])
        if not period:
            print(f"  [SKIP] attendee #{row['id']} — could not parse game datetime '{row['datetime']}'")
            skipped += 1
            continue

        cursor.execute(
            "SELECT id FROM member WHERE player_id = ? AND member_period = ?",
            (row["player_id"], period)
        )
        slot_type = "member" if cursor.fetchone() else "non-member"

        price = (row["price_per_member"] or 0) if slot_type == "member" else (row["price_per_person"] or 0)
        new_amount = price if row["is_paid"] else 0

        needs_amount_update = row["is_paid"] and (not row["amount_paid"] or row["amount_paid"] == 0)

        print(f"  attendee #{row['id']} (player {row['player_id']}, game {row['game_id']}, period={period})"
              f" → slot_type={slot_type}"
              + (f", amount_paid={new_amount}" if needs_amount_update else ""))

        if not dry_run:
            if needs_amount_update:
                cursor.execute(
                    "UPDATE game_attendee SET slot_type = ?, amount_paid = ? WHERE id = ?",
                    (slot_type, new_amount, row["id"])
                )
                amount_updated += 1
            else:
                cursor.execute(
                    "UPDATE game_attendee SET slot_type = ? WHERE id = ?",
                    (slot_type, row["id"])
                )
            slot_updated += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print("=" * 40)
    print(f"Rows processed  : {len(rows)}")
    print(f"slot_type set   : {slot_updated if not dry_run else len(rows) - skipped}")
    print(f"amount_paid set : {amount_updated if not dry_run else sum(1 for r in rows if r['is_paid'] and not r['amount_paid'])}")
    print(f"Skipped         : {skipped}")
    print("=" * 40)
    if dry_run:
        print("DRY RUN — no changes written.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill slot_type and amount_paid for game_attendee")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
