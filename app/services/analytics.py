from collections import Counter
from datetime import datetime


def _fmt_month(ym: str) -> str:
    """'2025-05' → 'May 2025'"""
    return datetime.strptime(ym, "%Y-%m").strftime("%B %Y")


def get_game_activity(conn) -> dict:
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

    # Most / least packed month (by total players, min 1 game)
    months_with_games = [m for m in monthly if m["game_count"] > 0]
    most_packed  = max(months_with_games, key=lambda m: m["total_players"]) if months_with_games else None
    least_packed = min(months_with_games, key=lambda m: m["total_players"]) if months_with_games else None
    if most_packed:
        most_packed  = {**most_packed,  "month": _fmt_month(most_packed["month"])}
    if least_packed:
        least_packed = {**least_packed, "month": _fmt_month(least_packed["month"])}

    # Community momentum: avg attendance last 8 games vs previous 8
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

    # Overall stats
    total_games = len(games)
    avg_fill    = round(sum(g["fill_rate"]      for g in games) / total_games, 1) if total_games else 0
    avg_players = round(sum(g["attendee_count"] for g in games) / total_games, 1) if total_games else 0

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

    # Loyalty leaderboard: top 15 by games attended
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.nickname,
            p.is_member,
            COUNT(ga.id) as games_attended
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        WHERE p.status = 1
        GROUP BY p.id
        ORDER BY games_attended DESC
        LIMIT 15
    """)
    leaderboard = [dict(r) for r in cursor.fetchall()]

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

    # Potential members: non-member active players with 5+ games
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.nickname,
            p.contact_no,
            COUNT(ga.id) as games_attended
        FROM player p
        JOIN game_attendee ga ON ga.player_id = p.id AND ga.is_attend = 1
        WHERE p.is_member = 0 AND p.status = 1
        GROUP BY p.id
        HAVING games_attended >= 5
        ORDER BY games_attended DESC
    """)
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
        LIMIT 10
    """)
    dropouts = [dict(r) for r in cursor.fetchall()]

    return {
        "leaderboard": leaderboard,
        "frequency_buckets": frequency_buckets,
        "new_vs_returning": new_vs_returning,
        "potential_members": potential_members,
        "potential_member_count": len(potential_members),
        "dropout_watch": dropouts,
    }


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

    return {
        "ratings_per_game": ratings_per_game,
        "distribution": distribution,
        "great_tags": great_counter.most_common(10),
        "improve_tags": improve_counter.most_common(10),
        "overall_avg": overall["avg"] or 0,
        "total_ratings": overall["total"],
        "games_with_ratings": len(ratings_per_game),
    }
