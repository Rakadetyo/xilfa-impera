# 2026-08-19 Saved schedule format templates

## Why

Building a schedule is repeated work. Every Saturday with the same team count
produces the same fixture list, and any manual refinement — reordering to avoid
back-to-backs, appending a pickup slot — is lost the moment the next game starts.

Admins should be able to save a schedule they like as a named format, then pick
that format on a future game and get the same schedule back.

The library is shared: five admins save formats for each other, not just for
themselves.

### What a template is

An ordered list of fixtures expressed as **team ordinals**, plus the session
cadence. It is a stamp, not a live link — applying it copies rows into
`game_match`, so editing or deleting a template never changes a game that
already used it.

Players never travel. Neither do team names or colours. Ordinal *N* resolves to
the *N*th team of the target game, ordered by `game_team.id`:

```
game 85  ordinal 1 -> game_team.id=442  "Team 1"  Deryan, Janssen, Kurniawan
game 84  ordinal 1 -> game_team.id=437  "Team 1"  Andy, Brian, Davin
```

Same template, same fixture structure, each game keeps its own rosters.

## Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | What is captured | Pairings, order, duration, break time |
| 2 | Timing model | Uniform cadence (game-level duration/break), not per-match |
| 3 | Ownership | Global visibility, creator-attributed; only creator or superadmin may rename/delete |
| 4 | Team-count binding | Strict. Shown greyed out with a reason when counts differ |
| 5 | Snapshot source | The on-screen order (save order + name in one action) |
| 6 | Ordinal resolution | Position only, by `game_team.id`. Names are decoration |
| 7 | Storage on the game | `schedule_format = 'custom'` plus a dedicated `schedule_template_id` |
| 8 | Destructive apply | Confirm when results exist; fix `generate_schedule` first |
| 9 | Management surface | Inline on the schedule tab. Unique names; same name you own overwrites |
| 10 | Columns carried | `match_order`, `round_number`, ordinals, `is_tbd`, `has_time` |
| 11 | Untimed rows | Preserved. Rows without a time stay `--:--` and consume no slot |

### Deliberately out of scope

- **Per-match durations and mid-session breaks.** Needs a `game_match` schema
  change and per-row inputs. That is a timing feature, not a template feature.
- **Elimination brackets.** `next_match_id` is a row reference and would need
  positional rewriting. Saved knockout brackets would lose winner progression,
  so templates target round-robin-style sessions only.
- **`court_label`.** The column exists but nothing writes to it.
- **Adapting a template to a different team count.** Only coherent for complete
  round robins; silently wrong for anything custom.
- **Start time.** Stays a property of the game, not the format. Confirmed
  2026-08-19: 19:00 belongs to that Saturday, not to the format. The form's
  start time is what the replayed slots are computed from.

## Prerequisites

Two existing bugs sit directly under this feature. Both are fixed first, as
their own commits, so the new code is safe by construction.

### P1 — `generate_schedule` destroys results silently

`DELETE FROM game_match WHERE game_id = ?` runs with no guard, and
`PRAGMA foreign_keys = 0`, so the declared `ON DELETE CASCADE` does nothing.
Current exposure:

```
game 80: 11 scored matches, 90 player stat rows
game 81:  9 scored matches, 46 player stat rows
game 84: 10 scored matches, 30 player stat rows
```

One click of Generate Schedule on game 80 deletes 11 results and leaves 90
`game_player_stat` rows orphaned — not deleted, just detached from a match that
no longer exists. No orphans exist yet, so this has not bitten anyone.

Fix: count affected matches first; if any has a score or stats, require
confirmation. On confirm, delete `game_player_stat` rows explicitly before
deleting matches.

### P2 — `game_team` is never ordered

None of the nine `game_team` queries has an `ORDER BY`. They rely on SQLite's
implicit rowid ordering, which is unspecified. Ordinal resolution makes that
load-bearing, so add `ORDER BY id` — at minimum in `generate_schedule` and
`game_detail`.

## Schema

```sql
CREATE TABLE IF NOT EXISTS schedule_template (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    team_count        INTEGER NOT NULL,
    duration_per_game INTEGER NOT NULL DEFAULT 8,
    break_time        INTEGER NOT NULL DEFAULT 0,
    created_by        INTEGER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS schedule_template_match (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id  INTEGER NOT NULL,
    match_order  INTEGER NOT NULL,
    round_number INTEGER,
    home_ordinal INTEGER,          -- NULL = Pickup / Free
    away_ordinal INTEGER,          -- NULL = Pickup / Free
    is_tbd       INTEGER DEFAULT 0,
    has_time     INTEGER DEFAULT 1,
    FOREIGN KEY (template_id) REFERENCES schedule_template(id) ON DELETE CASCADE
);
```

Plus, on `game`:

```sql
ALTER TABLE game ADD COLUMN schedule_template_id   INTEGER;
ALTER TABLE game ADD COLUMN schedule_template_name TEXT;
```

`schedule_template_name` is copied at apply time so history stays readable after
a template is deleted.

Both `ALTER` statements go in `app/db/migrations.py` guarded against a fresh
database, and both `CREATE TABLE` statements precede any `ALTER` touching them.

**The `ON DELETE CASCADE` above is decorative** — foreign keys are not enforced.
Deleting a template must explicitly delete its `schedule_template_match` rows in
Python.

### NULL ordinals are meaningful

`home_ordinal IS NULL` is **Pickup / Free** — the empty option in the Home/Away
selects — a state the user chose, not a missing team. It is not affected by the
strict team-count rule.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/manage/games/{game_id}/schedule/save-template` | Save current on-screen schedule under a name |
| POST | `/manage/schedule-templates/{id}/rename` | Rename (creator or superadmin) |
| POST | `/manage/schedule-templates/{id}/delete` | Delete, plus its match rows (creator or superadmin) |

Applying reuses the existing `POST /manage/games/{game_id}/schedule/generate`.
The Format select submits `format=template:12` **on the wire only**; the handler
splits it and stores `schedule_format='custom'` with `schedule_template_id=12`.
The `template:` prefix never reaches the database.

### Save

Submits the name plus the current DOM row order, so it captures what is on
screen rather than what was last persisted — no "you have unsaved changes"
modal, and no silently saving a stale order. Disabled when there are no matches.

Ordinals are derived by mapping each row's `team_home_id` / `team_away_id`
against the game's teams ordered by `id`. A team id of `NULL` stores `NULL`.
`has_time` is set from whether the row has a `scheduled_start`.

If the name exists and the caller owns it, the template is replaced (its match
rows deleted and rewritten). If it exists and belongs to someone else, reject
with a message.

### Apply

1. Reject if `template.team_count != len(teams)`.
2. If any existing match has a score or stats, require confirmation (P1).
3. Delete dependent `game_player_stat` rows, then `game_match` rows.
4. Set `duration_per_game` and `break_time` from the template; `schedule_format`
   to `'custom'`; `schedule_template_id` and `schedule_template_name`.
5. Insert one `game_match` per template row, resolving ordinals against teams
   ordered by `id`.
6. Walk rows in `match_order`. Rows with `has_time = 1` get the next sequential
   slot from the form's start time; rows with `has_time = 0` get no
   `scheduled_start` and do not advance the counter.

## UI

All on the schedule tab. Nothing added to the sidebar.

- **Format select** gains two groups: *Built-in* (unchanged) and *My formats*.
  Templates whose `team_count` matches are selectable; others appear greyed out
  reading `4-team quick — needs 4 teams, you have 6`, so a saved format is never
  invisible.
- **Save as format** button beside Save Order. Opens a name prompt, warns when
  the name will overwrite one of yours.
- **Manage formats** link opens a small list: name, team count, creator, match
  count, with rename and delete for rows you own or if you are superadmin.

## Tests

Extend `tests/`, which already has a throwaway-DB fixture per test.

- Round trip: save a 15-match round robin from a 6-team game, apply to a
  different 6-team game, assert identical `(match_order, home_ordinal,
  away_ordinal, round_number)` and that teams resolve to the target game's own
  `game_team` rows
- Players and team names are untouched by apply
- Pickup / Free rows survive: `NULL` ordinals stay `NULL`
- Untimed rows stay untimed, and do not shift the times of later matches
- `duration` and `break_time` come back from the template
- Applying to a mismatched team count is rejected
- Ordinals resolve by `id` order, including a game with non-contiguous team ids
- Deleting a template leaves games that used it fully intact
- Deleting a template removes its `schedule_template_match` rows (no orphans)
- Overwrite by same owner replaces rows rather than duplicating
- Overwrite attempt by a different user is rejected
- P1: generating over a scored schedule without confirmation is refused; with
  confirmation, no orphaned `game_player_stat` rows remain

## Checklist

- [x] P1 — guard `generate_schedule` against destroying results; delete
      `game_player_stat` rows explicitly *(232fdf3)*
- [x] P2 — add `ORDER BY id` to `game_team` queries *(232fdf3)*
- [ ] Migrations: two tables, two `game` columns, fresh-DB guarded
- [ ] `app/services/schedule_template.py` — save, load, resolve ordinals, apply
- [ ] Save endpoint, with overwrite and ownership rules
- [ ] Rename and delete endpoints, with ownership checks and manual cleanup
- [ ] Extend `generate_schedule` to accept and split `template:<id>`
- [ ] Format select grouping, with greyed-out mismatches
- [ ] Save as format button and Manage formats list
- [ ] Tests
- [ ] Verify in browser on a real game
- [ ] Review + commit
- [ ] Deploy

## Status

All design questions resolved. Both prerequisites are merged (`232fdf3`);
implementation of the feature itself has not started.
