from itertools import combinations


def generate_schedule(teams):
    teams = sorted(teams)
    n = len(teams)
    if n < 2:
        return []
    if n % 2 == 1:
        return _modular_schedule(teams, n)
    return _greedy_schedule(teams)


def _modular_schedule(teams, n):
    """Phase by cyclic diff. d=1 uses step=n//2; others step=1. Guaranteed no back-to-back."""
    schedule = []
    for d in range(1, n // 2 + 1):
        step = n // 2 if d == 1 else 1
        start = 0
        for _ in range(n):
            a, b = start % n, (start + d) % n
            schedule.append((teams[min(a, b)], teams[max(a, b)]))
            start = (start + step) % n
    return schedule


def _greedy_schedule(teams):
    """Prefer no back-to-back. Fall back to any remaining match when stuck."""
    remaining = list(combinations(teams, 2))
    schedule = [remaining.pop(0)]
    while remaining:
        prev = set(schedule[-1])
        non_conflict = [m for m in remaining if not (set(m) & prev)]
        pick = non_conflict[0] if non_conflict else remaining[0]
        schedule.append(pick)
        remaining.remove(pick)
    return schedule


# for n in [2, 3, 4, 5, 6, 7]:
#     teams = list(range(1, n + 1))
#     sched = generate_schedule(teams)
#     conflicts = sum(1 for i in range(len(sched)-1) if set(sched[i]) & set(sched[i+1]))
#     print(f"n={n}: {len(sched)} games, {conflicts} back-to-backs")


def __main__():
    teams = [1, 2, 3, 4, 5]
    sched = generate_schedule(teams)
    conflicts = sum(
        1 for i in range(len(sched) - 1) if set(sched[i]) & set(sched[i + 1])
    )
    print(f"{sched}")


#     teams = [1, 2, 3, 4, 5]
#     games = [[1, 2]]
#     match_index = 1
#     n_games = len(teams) * (len(teams) - 1) // 2

#     while match_index <= n_games - 1:
#         prev_match = []
#         match = []
#         match_created = False

#         for ta in teams:
#             for tb in reversed(teams):
#                 if match_index > 0 and len(games) >= match_index:
#                     prev_match = games[match_index - 1]
#                 if ta in prev_match or tb in prev_match:
#                     continue

#                 if ta == tb:
#                     continue

#                 if ta < tb:
#                     match = [ta, tb]
#                 if tb < ta:
#                     match = [tb, ta]

#                 print(f"Potential Match: {match} | {games}")
#                 if match not in games:
#                     print("adding: ", match)
#                     games.append(match)
#                     match_created = True
#                     break
#             if match_created:
#                 break

#         match_index += 1
#     print(games, len(games))


__main__()
