# 2026-08-19 Fix: adding a team wiped locked assignments

## Why

Reported by user:

> "kalo udah generate 4 tim, terus mau tambah 1 tim lagi, dia generate ulang semua,
> kondisi udah di lock semua tim"

With 4 teams generated and every player locked, adding a 5th team tore up every
existing team and rebuilt from scratch.

### Root cause

There was **no "add a team" control in the UI**. The only way to change team count
was the `num_teams` field inside `#generate-form`, which posts to
`POST /manage/games/{id}/teams/generate`. That handler opened with:

```sql
UPDATE game_attendee SET team_id = NULL WHERE game_id = ?;
DELETE FROM game_team WHERE game_id = ?;
```

Two compounding problems:

1. `generate_teams_route` never read the `locked` column at all. `randomize_teams`
   respects locks; `generate` did not. So the lock UI did nothing on the code path
   people actually use.
2. A correct `create_team` endpoint already existed (`POST /teams`, a plain INSERT
   touching nothing else) but no template posted to it — it was unreachable.

Measured on the original code with 20 locked players, 4 teams → 5:

```
players whose team CHANGED : 20/20
players left UNASSIGNED    :  0/20
```

The symptom is a full reshuffle onto newly created teams, not blanking.

## Checklist

- [x] Wire `+ Add Team` button to the existing `POST /teams` endpoint
- [x] Auto-name (`Team N`) and auto-pick an unused colour for appended teams
- [x] Keep `game.num_teams` in sync when a team is appended
- [x] Make `generate` preserve locked players and the teams holding them
- [x] Clamp team count instead of destroying assignments when the request is
      below the number of teams holding locked players
- [x] Preserve original from-scratch behaviour when nothing is locked
- [x] Fix `game_match` ALTER block running before its `CREATE TABLE`
      (blocked every fresh DB, including the test DB)
- [x] Regression tests
- [x] Verify in browser
- [ ] Review + commit
- [ ] Deploy

## Behaviour after the fix

| Situation | Result |
|---|---|
| No locked players | Unchanged — full rebuild from scratch |
| Some locked | Locked keep their team; unlocked redistribute into the new count |
| All locked, more teams | Locked stay put; new teams created empty |
| Fewer teams than hold locked players | Clamped, message shown, nothing destroyed |
| `+ Add Team` | Appends one empty team, never touches existing assignments |

## Tests

`tests/test_teams.py` — 12 tests. Same suite run against both versions:

```
against ORIGINAL code:   8 failed, 4 passed
against FIXED code:     12 passed
```

Fixtures build a throwaway SQLite DB per test (`tests/conftest.py`) and never
touch `impera.db`. Auth is monkeypatched, so no credentials appear in test code.

```bash
.venv/bin/python -m pytest tests/ -v
```

## Manual verification

Mock game 85 ("MOCK — team-add repro"): 20 players, 4 teams x 5, all locked.

1. `+ Add Team` → Team 5 (Red) appended empty; all 20 assignments byte-identical
2. Number of Teams 5 → 6, Generate Teams → Teams 1-4 rosters and locks intact,
   Teams 5 & 6 created empty, 0 unassigned
3. Unlock Team 4's five players, Generate Teams → Teams 1-3 (locked) unchanged;
   the five unlocked players redistributed across Teams 4, 5 and 6

## Files touched

- `app/routers/games/teams.py` — `create_team` defaults, lock-aware `generate`
- `app/templates/games/detail.html` — `+ Add Team` button
- `app/db/migrations.py` — `game_match` ALTER moved after its CREATE, guarded
- `tests/conftest.py`, `tests/helpers.py`, `tests/test_teams.py` — new
