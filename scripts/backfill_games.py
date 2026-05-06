#!/usr/bin/env python3
"""
Backfill historical games from a CSV file.

CSV format:
    date,player_name,is_member
    2024-03-15,John Doe,1
    2024-03-15,Jane Smith,0

- date: YYYY-MM-DD
- player_name: must match player.name in DB (case-insensitive)
- is_member: 1 or 0 (optional, defaults to 0)

Rules:
- One game per unique date
- Skip if game already exists for that date
- Skip if player not found in DB
- Skip if player already in game
"""

import csv
import sys
import os
from pathlib import Path

# Allow running from any directory
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db


def load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            date = row.get("date", "").strip()
            player_name = row.get("player_name", "").strip()
            is_member = row.get("is_member", "0").strip()

            if not date or not player_name:
                print(f"  [SKIP] Row {i}: missing date or player_name")
                continue

            rows.append({
                "date": date,
                "player_name": player_name,
                "is_member": 1 if is_member == "1" else 0,
            })
    return rows


def build_player_map(cursor) -> dict[str, int]:
    cursor.execute("SELECT id, name FROM player WHERE status = 1")
    return {row["name"].lower(): row["id"] for row in cursor.fetchall()}


def run(csv_path: str, dry_run: bool = False):
    print(f"{'[DRY RUN] ' if dry_run else ''}Loading {csv_path}...")
    rows = load_csv(csv_path)

    # Group by date
    games_map: dict[str, list[dict]] = {}
    for row in rows:
        games_map.setdefault(row["date"], []).append(row)

    conn = get_db()
    cursor = conn.cursor()

    player_map = build_player_map(cursor)

    games_created = 0
    games_skipped = 0
    players_added = 0
    players_skipped = 0
    players_not_found = []

    for date in sorted(games_map.keys()):
        attendees = games_map[date]

        # Check if game exists for this date
        cursor.execute(
            "SELECT id FROM game WHERE date(datetime) = ?", (date,)
        )
        existing = cursor.fetchone()

        if existing:
            game_id = existing["id"]
            print(f"  [EXISTS] {date} → game #{game_id}")
            games_skipped += 1
        else:
            if not dry_run:
                cursor.execute(
                    "INSERT INTO game (datetime) VALUES (?)",
                    (f"{date}T00:00",),
                )
                game_id = cursor.lastrowid
            else:
                game_id = "NEW"
            print(f"  [CREATE] {date} → game #{game_id}")
            games_created += 1

        # Add players
        for entry in attendees:
            name_lower = entry["player_name"].lower()
            player_id = player_map.get(name_lower)

            if player_id is None:
                print(f"    [NOT FOUND] '{entry['player_name']}'")
                players_not_found.append(entry["player_name"])
                players_skipped += 1
                continue

            if not dry_run:
                cursor.execute(
                    "SELECT id FROM game_attendee WHERE game_id = ? AND player_id = ?",
                    (game_id, player_id),
                )
                if cursor.fetchone():
                    print(f"    [SKIP] {entry['player_name']} already in game")
                    players_skipped += 1
                    continue

                cursor.execute(
                    "INSERT INTO game_attendee (game_id, player_id, is_paid, is_attend) VALUES (?, ?, ?, 1)",
                    (game_id, player_id, entry["is_member"]),
                )
                players_added += 1
                print(f"    [ADD] {entry['player_name']} (is_paid={entry['is_member']})")
            else:
                print(f"    [WOULD ADD] {entry['player_name']} (is_paid={entry['is_member']})")
                players_added += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print("=" * 40)
    print(f"Games created : {games_created}")
    print(f"Games skipped : {games_skipped} (already existed)")
    print(f"Players added : {players_added}")
    print(f"Players skipped: {players_skipped}")
    if players_not_found:
        unique_not_found = sorted(set(players_not_found))
        print(f"\nNot found in DB ({len(unique_not_found)}):")
        for name in unique_not_found:
            print(f"  - {name}")
    print("=" * 40)
    if dry_run:
        print("DRY RUN — no changes written.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill historical games from CSV")
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print(f"Error: file not found: {args.csv_file}")
        sys.exit(1)

    run(args.csv_file, dry_run=args.dry_run)
