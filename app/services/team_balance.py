def compute_player_values(attendees, skill_weight=0.6):
    if not attendees:
        return {}
    position_weight = 1.0 - skill_weight
    skills = [a.get("skill_level") or 3 for a in attendees]
    min_s, max_s = min(skills), max(skills)
    skill_range = (max_s - min_s) or 1
    pos_counts: dict = {}
    total_slots = 0
    for a in attendees:
        for key in ("position_1", "position_2"):
            pos = a.get(key)
            if pos and pos != "?":
                pos_counts[pos] = pos_counts.get(pos, 0) + 1
                total_slots += 1
    result: dict = {}
    for a in attendees:
        skill_pct = ((a.get("skill_level") or 3) - min_s) / skill_range
        scarcities = []
        for key in ("position_1", "position_2"):
            pos = a.get(key)
            if pos and pos != "?" and total_slots > 0:
                scarcities.append(1.0 - pos_counts[pos] / total_slots)
        pos_scarcity = max(scarcities) if scarcities else 0.0
        result[a["id"]] = round((skill_pct * skill_weight + pos_scarcity * position_weight) * 100, 1)
    return result


def generate_balanced_teams(attendees, groups, num_teams, players_per_team, value_scores=None):
    attendees_with_teams = [a for a in attendees if a.get("team_id") is not None]
    if not attendees_with_teams:
        attendees_with_teams = attendees

    attendee_by_id = {a["id"]: a for a in attendees_with_teams}
    attendee_skill = {a["id"]: (a.get("skill_level") or 3) for a in attendees_with_teams}

    grouped_ids: set = set()
    for g in groups:
        for aid in g["member_attendee_ids"]:
            if aid in attendee_by_id:
                grouped_ids.add(aid)

    solo_attendees = [a for a in attendees_with_teams if a["id"] not in grouped_ids]
    if value_scores:
        solo_attendees.sort(key=lambda a: -value_scores.get(a["id"], 0))
    else:
        solo_attendees.sort(key=lambda a: -(a.get("skill_level") or 3))

    groups_sorted = sorted(
        groups,
        key=lambda g: sum(attendee_skill.get(aid, 3) for aid in g["member_attendee_ids"]),
        reverse=True,
    )

    team_assignments = [[] for _ in range(num_teams)]
    team_group_counts = [0] * num_teams
    team_skill_sums = [0.0] * num_teams

    for group in groups_sorted:
        min_count = min(team_group_counts)
        eligible = [i for i, c in enumerate(team_group_counts) if c == min_count]
        target = min(eligible, key=lambda i: team_skill_sums[i])
        for aid in group["member_attendee_ids"]:
            if aid in attendee_by_id and len(team_assignments[target]) < players_per_team:
                team_assignments[target].append(aid)
                team_skill_sums[target] += attendee_skill.get(aid, 3)
        team_group_counts[target] += 1

    has_group = [team_group_counts[i] > 0 for i in range(num_teams)]
    no_group_teams = [i for i in range(num_teams) if not has_group[i]]
    group_teams = sorted(
        [i for i in range(num_teams) if has_group[i]],
        key=lambda i: team_skill_sums[i],
        reverse=True,
    )

    solo_idx = 0
    round_num = 0
    max_rounds = (len(solo_attendees) + 1) * (num_teams + 1)

    while solo_idx < len(solo_attendees) and round_num < max_rounds:
        no_group_round = list(no_group_teams) if round_num % 2 == 0 else list(reversed(no_group_teams))
        round_order = no_group_round + group_teams
        picks_this_round = 0

        for team_idx in round_order:
            if solo_idx >= len(solo_attendees):
                break
            if len(team_assignments[team_idx]) >= players_per_team:
                continue
            if has_group[team_idx]:
                no_group_open = [i for i in no_group_teams if len(team_assignments[i]) < players_per_team]
                if no_group_open:
                    my_count = len(team_assignments[team_idx])
                    if min(len(team_assignments[i]) for i in no_group_open) < my_count:
                        continue
            team_assignments[team_idx].append(solo_attendees[solo_idx]["id"])
            team_skill_sums[team_idx] += attendee_skill.get(solo_attendees[solo_idx]["id"], 3)
            solo_idx += 1
            picks_this_round += 1

        if picks_this_round == 0:
            for team_idx in range(num_teams):
                if solo_idx >= len(solo_attendees):
                    break
                if len(team_assignments[team_idx]) < players_per_team:
                    team_assignments[team_idx].append(solo_attendees[solo_idx]["id"])
                    solo_idx += 1
            if picks_this_round == 0:
                break

        round_num += 1

    return team_assignments
