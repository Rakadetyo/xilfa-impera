from itertools import combinations


def _rr_modular(ids: list, n: int) -> list:
    pairs = []
    for d in range(1, n // 2 + 1):
        step = n // 2 if d == 1 else 1
        start = 0
        for _ in range(n):
            a, b = start % n, (start + d) % n
            pairs.append((ids[min(a, b)], ids[max(a, b)]))
            start = (start + step) % n
    return pairs


def _rr_greedy(ids: list) -> list:
    remaining = list(combinations(ids, 2))
    result = [remaining.pop(0)]
    while remaining:
        prev = set(result[-1])
        non_conflict = [m for m in remaining if not (set(m) & prev)]
        pick = non_conflict[0] if non_conflict else remaining[0]
        result.append(pick)
        remaining.remove(pick)
    return result


def generate_round_robin(teams: list) -> list:
    ids = sorted([t["id"] for t in teams])
    n = len(ids)
    if n < 2:
        return []
    pairs = _rr_modular(ids, n) if n % 2 == 1 else _rr_greedy(ids)
    return [
        {"team_home_id": home, "team_away_id": away, "round_number": i + 1, "bracket_slot": None, "next_match_id": None, "is_tbd": 0}
        for i, (home, away) in enumerate(pairs)
    ]


def generate_single_elimination(teams: list) -> list:
    import math
    matches = []
    team_ids = [t["id"] for t in teams]
    n = len(team_ids)
    if n < 2:
        return []
    num_rounds = math.ceil(math.log2(n))
    bracket_size = 2 ** num_rounds
    seeds = team_ids.copy()
    matches_in_round_1 = bracket_size // 2
    slot = 1
    for i in range(0, matches_in_round_1 * 2, 2):
        if i + 1 < n:
            matches.append({"team_home_id": seeds[i], "team_away_id": seeds[i + 1], "round_number": 1, "bracket_slot": f"R1-{slot}", "is_tbd": 0})
            slot += 1
        elif i < n:
            matches.append({"team_home_id": seeds[i], "team_away_id": None, "round_number": 1, "bracket_slot": f"R1-{slot}", "is_tbd": 1})
            slot += 1
    for r in range(2, num_rounds + 1):
        for m in range(bracket_size // (2 ** r)):
            matches.append({"team_home_id": None, "team_away_id": None, "round_number": r, "bracket_slot": f"R{r}-{m + 1}", "is_tbd": 1})
    return matches


def generate_double_elimination(teams: list) -> list:
    return generate_single_elimination(teams)


def generate_group_knockout(teams: list) -> list:
    matches = []
    n = len(teams)
    if n <= 4:
        num_groups, teams_per_group = 1, n
    elif n <= 6:
        num_groups, teams_per_group = 2, 3
    else:
        num_groups, teams_per_group = 2, n // 2
    team_ids = [t["id"] for t in teams]
    for g in range(num_groups):
        start = g * teams_per_group
        group_teams = team_ids[start:min(start + teams_per_group, len(team_ids))]
        for i in range(len(group_teams)):
            for j in range(i + 1, len(group_teams)):
                matches.append({"team_home_id": group_teams[i], "team_away_id": group_teams[j], "round_number": 1, "bracket_slot": f"G{g + 1}", "is_tbd": 0})
    for k in range(max(2, num_groups * 2) // 2):
        matches.append({"team_home_id": None, "team_away_id": None, "round_number": 2, "bracket_slot": f"KF{k + 1}", "is_tbd": 1})
    return matches


def generate_king_of_court(teams: list) -> list:
    team_ids = [t["id"] for t in teams]
    if len(team_ids) < 2:
        return []
    matches = [{"team_home_id": team_ids[0], "team_away_id": team_ids[1], "round_number": 1, "bracket_slot": None, "is_tbd": 0}]
    for _ in range(2):
        matches.append({"team_home_id": None, "team_away_id": None, "round_number": 1, "bracket_slot": None, "is_tbd": 1})
    return matches


SUGGESTIONS = {
    2: "single_elimination",
    3: "round_robin",
    4: "round_robin",
    5: "king_of_court",
    6: "group_knockout",
    7: "group_knockout",
    8: "single_elimination",
}
