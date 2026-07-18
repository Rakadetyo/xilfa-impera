from collections import Counter
from datetime import datetime


def _fmt_month(ym: str) -> str:
    """'2025-05' → 'May 2025'"""
    return datetime.strptime(ym, "%Y-%m").strftime("%B %Y")


def get_game_activity(conn, packed_months: int = 6) -> dict:
    cursor = conn.cursor()

    # Per-game: date + actual attendees + fill rate
    cursor.execute("""
        SELECT
            g.id,
            g.datetime,
            g.max_players,
            COUNT(ga.id) as attendee_count,
            CASE WHEN g.max_players > 0
                THEN ROUND(COUNT(ga.id) * 100.0 / g.max_players, 1)
                ELSE 0
            END as fill_rate
        FROM game g
        LEFT JOIN game_attendee ga ON ga.game_id = g.id AND ga.is_attend = 1
        GROUP BY g.id
        ORDER BY g.datetime
    """)
    games = [dict(r) for r in cursor.fetchall()]

    # Monthly summary: game count + total + avg player count
    cursor.execute("""
        SELECT
            strftime('%Y-%m', g.datetime) as month,
            COUNT(DISTINCT g.id) as game_count,
            COALESCE(SUM(attendee_counts.cnt), 0) as total_players,
            ROUND(AVG(attendee_counts.cnt), 1) as avg_players
        FROM game g
        LEFT JOIN (
            SELECT game_id, COUNT(*) as cnt
            FROM game_attendee
            WHERE is_attend = 1
            GROUP BY game_id
        ) attendee_counts ON attendee_counts.game_id = g.id
        GROUP BY month
        ORDER BY month
    """)
    monthly = [dict(r) for r in cursor.fetchall()]

    # Filter games to packed_months window (heatmap keeps all-time)
    months_with_games = [m for m in monthly if m["game_count"] > 0]
    if packed_months:
        cutoff_months = set(sorted(set(m["month"] for m in monthly), reverse=True)[:packed_months])
        filtered_games = [g for g in games if g["datetime"][:7] in cutoff_months]
        packed_pool = [m for m in months_with_games if m["month"] in cutoff_months]
    else:
        filtered_games = games
        packed_pool = months_with_games

    most_packed  = max(packed_pool, key=lambda m: m["total_players"]) if packed_pool else None
    least_packed = min(packed_pool, key=lambda m: m["total_players"]) if packed_pool else None
    if most_packed:
        most_packed  = {**most_packed,  "month": _fmt_month(most_packed["month"])}
    if least_packed:
        least_packed = {**least_packed, "month": _fmt_month(least_packed["month"])}

    # Community momentum: avg attendance last 8 games vs previous 8 (always all-time)
    cursor.execute("""
        SELECT cnt, rn FROM (
            SELECT
                COUNT(ga.id) as cnt,
                ROW_NUMBER() OVER (ORDER BY g.datetime DESC) as rn
            FROM game g
            LEFT JOIN game_attendee ga ON ga.game_id = g.id AND ga.is_attend = 1
            GROUP BY g.id
        ) sub
        WHERE rn <= 16
    """)
    momentum_rows = cursor.fetchall()
    recent  = [r["cnt"] for r in momentum_rows if r["rn"] <= 8]
    prev    = [r["cnt"] for r in momentum_rows if r["rn"] > 8]
    recent_avg = round(sum(recent) / len(recent), 1) if recent else 0
    prev_avg   = round(sum(prev)   / len(prev),   1) if prev   else 0
    momentum_pct = round((recent_avg - prev_avg) / prev_avg * 100, 1) if prev_avg else None

    # Summary stats — scoped to filtered window
    total_games = len(filtered_games)
    avg_fill    = round(sum(g["fill_rate"]      for g in filtered_games) / total_games, 1) if total_games else 0
    avg_players = round(sum(g["attendee_count"] for g in filtered_games) / total_games, 1) if total_games else 0

    return {
        "games": games,
        "monthly": monthly,
        "total_games": total_games,
        "avg_fill_rate": avg_fill,
        "avg_players_per_game": avg_players,
        "most_packed": most_packed,
        "least_packed": least_packed,
        "momentum_pct": momentum_pct,
        "momentum_recent_avg": recent_avg,
        "momentum_prev_avg": prev_avg,
    }


def get_player_stats(conn) -> dict:
    cursor = conn.cursor()

    current_period = datetime.now().strftime("%B %Y")

    # Loyalty leaderboard: top 15 by games attended
    # is_member = has active member record for current period
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.nickname,
            CASE WHEN m.id IS NOT NULL THEN 1 ELSE 0 END as is_member,
            COUNT(ga.id) as games_attended
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        LEFT JOIN member m ON m.player_id = p.id AND m.member_period = ?
        WHERE p.status = 1
        GROUP BY p.id
        ORDER BY games_attended DESC
        LIMIT 15
    """, (current_period,))
    leaderboard = [dict(r) for r in cursor.fetchall()]

    # Streak leaderboard: consecutive weeks attended (most recent first)
    # Group games by ISO week — attending ANY game in a week = attended that week
    cursor.execute("SELECT id, datetime FROM game WHERE datetime <= datetime('now') ORDER BY datetime DESC")
    past_games = cursor.fetchall()

    def _week_key(dt_str: str):
        try:
            # fromisoformat handles both "2026-05-10T08:00" and "2026-05-10 08:00:00"
            return datetime.fromisoformat(dt_str).isocalendar()[:2]
        except Exception:
            return None

    # Ordered unique weeks, most recent first
    seen_weeks: list = []
    week_to_game_ids: dict = {}
    for r in past_games:
        wk = _week_key(r["datetime"])
        if wk is None:
            continue
        if wk not in week_to_game_ids:
            seen_weeks.append(wk)
            week_to_game_ids[wk] = set()
        week_to_game_ids[wk].add(r["id"])

    cursor.execute("SELECT player_id, game_id FROM game_attendee WHERE is_attend = 1")
    attended_map: dict[int, set] = {}
    for r in cursor.fetchall():
        attended_map.setdefault(r["player_id"], set()).add(r["game_id"])

    cursor.execute("SELECT id, name, nickname FROM player WHERE status = 1")
    players_info = {r["id"]: dict(r) for r in cursor.fetchall()}

    cursor.execute("SELECT player_id FROM member WHERE member_period = ?", (current_period,))
    current_members = {r["player_id"] for r in cursor.fetchall()}

    streak_rows = []
    for player_id, game_set in attended_map.items():
        if player_id not in players_info:
            continue
        streak = 0
        for wk in seen_weeks:
            if game_set & week_to_game_ids[wk]:  # attended any game this week
                streak += 1
            else:
                break
        if streak > 0:
            p = players_info[player_id]
            streak_rows.append({
                "id": player_id,
                "name": p["name"],
                "nickname": p["nickname"],
                "is_member": 1 if player_id in current_members else 0,
                "streak": streak,
            })

    streak_leaderboard = sorted(streak_rows, key=lambda x: -x["streak"])[:10]

    # Attendance frequency buckets
    cursor.execute("""
        SELECT COUNT(ga.id) as games_attended
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        WHERE p.status = 1
        GROUP BY p.id
    """)
    counts = [r["games_attended"] for r in cursor.fetchall()]
    frequency_buckets = {
        "1": sum(1 for c in counts if c == 1),
        "2-5": sum(1 for c in counts if 2 <= c <= 5),
        "6-10": sum(1 for c in counts if 6 <= c <= 10),
        "11+": sum(1 for c in counts if c >= 11),
    }

    # New vs returning per month
    cursor.execute("""
        WITH first_game AS (
            SELECT ga.player_id, MIN(g.datetime) as first_dt
            FROM game_attendee ga
            JOIN game g ON g.id = ga.game_id
            WHERE ga.is_attend = 1
            GROUP BY ga.player_id
        )
        SELECT
            strftime('%Y-%m', g.datetime) as month,
            COUNT(DISTINCT CASE
                WHEN strftime('%Y-%m', fg.first_dt) = strftime('%Y-%m', g.datetime)
                THEN ga.player_id END) as new_players,
            COUNT(DISTINCT CASE
                WHEN strftime('%Y-%m', fg.first_dt) < strftime('%Y-%m', g.datetime)
                THEN ga.player_id END) as returning_players
        FROM game_attendee ga
        JOIN game g ON g.id = ga.game_id
        JOIN first_game fg ON fg.player_id = ga.player_id
        WHERE ga.is_attend = 1
        GROUP BY month
        ORDER BY month
    """)
    new_vs_returning = [dict(r) for r in cursor.fetchall()]

    # Potential members: no active membership this period, 5+ games attended
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.nickname,
            p.contact_no,
            COUNT(ga.id) as games_attended
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        LEFT JOIN member m ON m.player_id = p.id AND m.member_period = ?
        WHERE p.status = 1 AND m.id IS NULL
        GROUP BY p.id
        HAVING games_attended >= 5
        ORDER BY games_attended DESC
    """, (current_period,))
    potential_members = [dict(r) for r in cursor.fetchall()]

    # Dropout: players who attended 3+ games but last game > 60 days ago
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.nickname,
            COUNT(ga.id) as total_games,
            MAX(g.datetime) as last_game,
            CAST(julianday('now') - julianday(MAX(g.datetime)) AS INTEGER) as days_since
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        JOIN game g ON g.id = ga.game_id
        WHERE p.status = 1
        GROUP BY p.id
        HAVING total_games >= 3 AND days_since > 60
        ORDER BY days_since DESC
    """)
    dropouts = [dict(r) for r in cursor.fetchall()]

    return {
        "leaderboard": leaderboard,
        "streak_leaderboard": streak_leaderboard,
        "frequency_buckets": frequency_buckets,
        "new_vs_returning": new_vs_returning,
        "potential_members": potential_members,
        "potential_member_count": len(potential_members),
        "dropout_watch": dropouts,
    }


def get_all_player_games(conn, year: int | None = None) -> dict:
    cursor = conn.cursor()

    # Available years for the filter
    cursor.execute("SELECT DISTINCT strftime('%Y', datetime) as yr FROM game ORDER BY yr DESC")
    years = [r["yr"] for r in cursor.fetchall() if r["yr"]]

    if year:
        cursor.execute("""
            SELECT
                p.id,
                p.name,
                p.nickname,
                COUNT(ga.id) as games_attended
            FROM player p
            JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
            JOIN game g ON g.id = ga.game_id
            WHERE p.status = 1 AND strftime('%Y', g.datetime) = ?
            GROUP BY p.id
            ORDER BY games_attended DESC, p.name
        """, (str(year),))
    else:
        cursor.execute("""
            SELECT
                p.id,
                p.name,
                p.nickname,
                COUNT(ga.id) as games_attended
            FROM player p
            JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
            WHERE p.status = 1
            GROUP BY p.id
            ORDER BY games_attended DESC, p.name
        """)
    players = [dict(r) for r in cursor.fetchall()]

    return {"players": players, "years": years}


def get_finance_stats(conn) -> dict:
    cursor = conn.cursor()

    # Revenue per game from attendee payments
    cursor.execute("""
        SELECT
            g.id,
            g.datetime,
            COALESCE(SUM(ga.amount_paid), 0) as attendee_revenue,
            COUNT(ga.id) as attendee_count
        FROM game g
        LEFT JOIN game_attendee ga ON ga.game_id = g.id AND ga.is_attend = 1
        GROUP BY g.id
        ORDER BY g.datetime
    """)
    game_revenue = [dict(r) for r in cursor.fetchall()]

    # Finance entries (income/expense) per game
    cursor.execute("""
        SELECT
            game_id,
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as extra_income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as extra_expense
        FROM game_finance_entry
        GROUP BY game_id
    """)
    entries_by_game = {r["game_id"]: dict(r) for r in cursor.fetchall()}

    # Partner fees per game
    cursor.execute("""
        SELECT game_id, COALESCE(SUM(fee), 0) as partner_fees
        FROM game_partner
        GROUP BY game_id
    """)
    fees_by_game = {r["game_id"]: r["partner_fees"] for r in cursor.fetchall()}

    # Merge into per-game P&L
    for g in game_revenue:
        gid = g["id"]
        e = entries_by_game.get(gid, {"extra_income": 0, "extra_expense": 0})
        g["total_revenue"] = g["attendee_revenue"] + e["extra_income"]
        g["total_expense"] = e["extra_expense"] + fees_by_game.get(gid, 0)
        g["profit"] = g["total_revenue"] - g["total_expense"]

    # Unpaid slots
    cursor.execute("""
        SELECT
            COUNT(*) as unpaid_count,
            COALESCE(SUM(
                CASE ga.slot_type
                    WHEN 'member' THEN g.price_per_member
                    ELSE g.price_per_person
                END
            ), 0) as unpaid_estimated
        FROM game_attendee ga
        JOIN game g ON g.id = ga.game_id
        WHERE ga.is_paid = 0 AND ga.is_attend = 1
    """)
    unpaid = dict(cursor.fetchone())

    total_revenue = sum(g["total_revenue"] for g in game_revenue)
    total_expense = sum(g["total_expense"] for g in game_revenue)

    return {
        "game_revenue": game_revenue,
        "total_revenue": round(total_revenue, 0),
        "total_expense": round(total_expense, 0),
        "total_profit": round(total_revenue - total_expense, 0),
        "unpaid_count": unpaid["unpaid_count"],
        "unpaid_estimated": round(unpaid["unpaid_estimated"], 0),
    }


def get_quality_stats(conn) -> dict:
    cursor = conn.cursor()

    # Average rating per game over time
    cursor.execute("""
        SELECT
            g.id,
            g.datetime,
            ROUND(AVG(gr.rating), 2) as avg_rating,
            COUNT(gr.id) as rating_count
        FROM game g
        JOIN game_rating gr ON gr.game_id = g.id
        GROUP BY g.id
        ORDER BY g.datetime
    """)
    ratings_per_game = [dict(r) for r in cursor.fetchall()]

    # Rating distribution
    cursor.execute("""
        SELECT rating, COUNT(*) as count
        FROM game_rating
        GROUP BY rating
        ORDER BY rating
    """)
    distribution = {str(r["rating"]): r["count"] for r in cursor.fetchall()}
    for i in range(1, 6):
        distribution.setdefault(str(i), 0)

    # Tag frequency from great_things
    cursor.execute("SELECT great_things FROM game_rating WHERE great_things != ''")
    great_counter: Counter = Counter()
    for row in cursor.fetchall():
        for tag in row["great_things"].split(","):
            tag = tag.strip()
            if tag:
                great_counter[tag] += 1

    # Tag frequency from could_be_improved
    cursor.execute("SELECT could_be_improved FROM game_rating WHERE could_be_improved != ''")
    improve_counter: Counter = Counter()
    for row in cursor.fetchall():
        for tag in row["could_be_improved"].split(","):
            tag = tag.strip()
            if tag:
                improve_counter[tag] += 1

    # Overall stats
    cursor.execute("SELECT ROUND(AVG(rating), 2) as avg, COUNT(*) as total FROM game_rating")
    overall = dict(cursor.fetchone())

    # Recent feedback (non-empty feedback text, most recent first)
    cursor.execute("""
        SELECT
            gr.id,
            gr.rating,
            gr.feedback,
            gr.great_things,
            gr.could_be_improved,
            gr.is_anonymous,
            gr.created_at,
            p.name as player_name,
            g.datetime as game_datetime
        FROM game_rating gr
        JOIN player p ON p.id = gr.player_id
        JOIN game g ON g.id = gr.game_id
        WHERE gr.feedback IS NOT NULL AND TRIM(gr.feedback) != ''
        ORDER BY gr.created_at DESC
        LIMIT 100
    """)
    recent_feedback = [dict(r) for r in cursor.fetchall()]

    # All unique tags for filter UI
    all_tags = sorted(set(
        list(great_counter.keys()) + list(improve_counter.keys())
    ))

    max_dist = max(distribution.values()) if distribution else 1

    return {
        "ratings_per_game": ratings_per_game,
        "distribution": distribution,
        "max_dist": max_dist,
        "great_tags": great_counter.most_common(10),
        "improve_tags": improve_counter.most_common(10),
        "overall_avg": overall["avg"] or 0,
        "total_ratings": overall["total"],
        "games_with_ratings": len(ratings_per_game),
        "recent_feedback": recent_feedback,
        "all_tags": all_tags,
    }


def get_member_stats(conn) -> dict:
    cursor = conn.cursor()

    current_period = datetime.now().strftime("%B %Y")

    # Previous period from actual data (not just -1 month, in case of gaps)
    cursor.execute("""
        SELECT member_period FROM member
        WHERE member_period != ?
        GROUP BY member_period
        ORDER BY MIN(member_start_date) DESC
        LIMIT 1
    """, (current_period,))
    row = cursor.fetchone()
    prev_period = row["member_period"] if row else None

    # Summary: active, paid, new, churn
    cursor.execute("SELECT COUNT(DISTINCT player_id) as cnt FROM member WHERE member_period = ?", (current_period,))
    active_count = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM member WHERE member_period = ? AND is_paid = 1", (current_period,))
    paid_count = cursor.fetchone()["cnt"]

    # New = first ever membership record for this player
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM member m
        WHERE m.member_period = ?
        AND NOT EXISTS (
            SELECT 1 FROM member m2
            WHERE m2.player_id = m.player_id AND m2.id < m.id
        )
    """, (current_period,))
    new_count = cursor.fetchone()["cnt"]

    # Churn = was member last period, not this period
    churn_count = 0
    churn_list  = []
    if prev_period:
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM member m
            WHERE m.member_period = ?
            AND NOT EXISTS (
                SELECT 1 FROM member m2
                WHERE m2.player_id = m.player_id AND m2.member_period = ?
            )
        """, (prev_period, current_period))
        churn_count = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT p.id, p.name, p.nickname, m.membership_price, m.is_paid
            FROM member m
            JOIN player p ON p.id = m.player_id
            WHERE m.member_period = ?
            AND NOT EXISTS (
                SELECT 1 FROM member m2
                WHERE m2.player_id = m.player_id AND m2.member_period = ?
            )
            ORDER BY p.name
        """, (prev_period, current_period))
        churn_list = [dict(r) for r in cursor.fetchall()]

    paid_pct = round(paid_count / active_count * 100) if active_count else 0

    retention_rate = None
    if prev_period:
        cursor.execute("SELECT COUNT(DISTINCT player_id) as cnt FROM member WHERE member_period = ?", (prev_period,))
        prev_count = cursor.fetchone()["cnt"]
        if prev_count:
            retained = prev_count - churn_count
            retention_rate = round(retained / prev_count * 100)

    # Membership growth per period
    cursor.execute("""
        SELECT member_period, COUNT(DISTINCT player_id) as member_count,
               MIN(member_start_date) as sort_date
        FROM member
        GROUP BY member_period
        ORDER BY sort_date
    """)
    growth = [dict(r) for r in cursor.fetchall()]

    # Dead members — paid this period, 0 games attended in current month
    cursor.execute("""
        SELECT p.id, p.name, p.nickname, m.membership_price,
               COALESCE(att.games_played, 0) as games_this_period
        FROM member m
        JOIN player p ON p.id = m.player_id
        LEFT JOIN (
            SELECT ga.player_id, COUNT(*) as games_played
            FROM game_attendee ga
            JOIN game g ON g.id = ga.game_id
            WHERE ga.is_attend = 1
              AND strftime('%Y-%m', g.datetime) = strftime('%Y-%m', 'now')
            GROUP BY ga.player_id
        ) att ON att.player_id = m.player_id
        WHERE m.member_period = ? AND m.is_paid = 1
          AND COALESCE(att.games_played, 0) = 0
        ORDER BY p.name
    """, (current_period,))
    dead_members = [dict(r) for r in cursor.fetchall()]

    # Member ROI — cost per game this period
    cursor.execute("""
        SELECT p.id, p.name, p.nickname, m.membership_price, m.is_paid,
               COALESCE(att.games_played, 0) as games_this_period,
               CASE WHEN COALESCE(att.games_played, 0) > 0
                    THEN ROUND(m.membership_price * 1.0 / att.games_played, 0)
                    ELSE NULL
               END as cost_per_game
        FROM member m
        JOIN player p ON p.id = m.player_id
        LEFT JOIN (
            SELECT ga.player_id, COUNT(*) as games_played
            FROM game_attendee ga
            JOIN game g ON g.id = ga.game_id
            WHERE ga.is_attend = 1
              AND strftime('%Y-%m', g.datetime) = strftime('%Y-%m', 'now')
            GROUP BY ga.player_id
        ) att ON att.player_id = m.player_id
        WHERE m.member_period = ?
        ORDER BY cost_per_game ASC, games_this_period DESC
    """, (current_period,))
    roi = [dict(r) for r in cursor.fetchall()]

    return {
        "current_period": current_period,
        "prev_period": prev_period,
        "active_count": active_count,
        "paid_count": paid_count,
        "paid_pct": paid_pct,
        "new_count": new_count,
        "churn_count": churn_count,
        "retention_rate": retention_rate,
        "growth": growth,
        "dead_members": dead_members,
        "churn_list": churn_list,
        "roi": roi,
    }
