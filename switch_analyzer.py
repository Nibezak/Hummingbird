"""
Empirical Reversal & Switch Analyzer
====================================
Analyzes the entire SQLite recording database to find:
1. The largest price reversal ('switch') that has ever occurred in each time window.
2. The absolute largest dollar swing from any point T to settlement.
3. The empirical safe boundary where 0 switches have ever occurred.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")


def analyze_switches():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Time brackets (remaining seconds):
    # [180s - 120s] (Minute 2-3 left)
    # [120s - 60s]  (Minute 1-2 left)
    # [60s - 30s]   (30s to 1m left)
    # [30s - 0s]    (Final 30s)

    brackets = [
        ("3m to 2m left (180s - 120s)", 120, 180),
        ("2m to 1m left (120s - 60s)", 60, 120),
        ("1m to 30s left (60s - 30s)", 30, 60),
        ("Final 30s left (30s - 0s)", 0, 30),
    ]

    print("=" * 95)
    print("📊 EMPIRICAL SWITCH & REVERSAL ANALYSIS (ACROSS ALL RECORDED CYCLES)")
    print("=" * 95)

    for label, min_rem, max_rem in brackets:
        print(f"\n⏱️ TIME WINDOW: {label}")
        print("-" * 95)

        # 1. Largest DOWN gap that switched to UP
        cur.execute("""
            SELECT 
                s.cycle_id, s.remaining_seconds, s.spot_price, c.strike_price, s.gap_dollars, 
                c.final_price, (c.final_price - s.spot_price)
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' 
              AND c.winning_outcome = 'Up' 
              AND s.gap_dollars < 0
              AND s.remaining_seconds >= ? AND s.remaining_seconds < ?
            ORDER BY s.gap_dollars ASC
            LIMIT 1
        """, (min_rem, max_rem))
        down_rev = cur.fetchone()

        # 2. Largest UP gap that switched to DOWN
        cur.execute("""
            SELECT 
                s.cycle_id, s.remaining_seconds, s.spot_price, c.strike_price, s.gap_dollars, 
                c.final_price, (c.final_price - s.spot_price)
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' 
              AND c.winning_outcome = 'Down' 
              AND s.gap_dollars > 0
              AND s.remaining_seconds >= ? AND s.remaining_seconds < ?
            ORDER BY s.gap_dollars DESC
            LIMIT 1
        """, (min_rem, max_rem))
        up_rev = cur.fetchone()

        # 3. Maximum price swing in ANY direction to settlement
        cur.execute("""
            SELECT 
                s.cycle_id, s.remaining_seconds, s.spot_price, c.final_price,
                ABS(c.final_price - s.spot_price) as max_swing
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED'
              AND s.remaining_seconds >= ? AND s.remaining_seconds < ?
            ORDER BY max_swing DESC
            LIMIT 1
        """, (min_rem, max_rem))
        max_swing = cur.fetchone()

        if down_rev:
            cid, rem, spot, strike, gap, final_p, swing = down_rev
            print(f"  🔴 Largest DOWN Switch to UP:  Gap: ${gap:+.2f} at T-{rem}s (Cycle {cid}: Spot ${spot:,.2f} -> Final ${final_p:,.2f} | Swung ${swing:+.2f})")
        else:
            print("  🔴 Largest DOWN Switch to UP:  None (0 reversals recorded)")

        if up_rev:
            cid, rem, spot, strike, gap, final_p, swing = up_rev
            print(f"  🟢 Largest UP Switch to DOWN:  Gap: ${gap:+.2f} at T-{rem}s (Cycle {cid}: Spot ${spot:,.2f} -> Final ${final_p:,.2f} | Swung ${swing:+.2f})")
        else:
            print("  🟢 Largest UP Switch to DOWN:  None (0 reversals recorded)")

        if max_swing:
            cid, rem, spot, final_p, m_swing = max_swing
            print(f"  ⚡ Maximum Absolute Price Move: ${m_swing:,.2f} (Cycle {cid} moved from ${spot:,.2f} to ${final_p:,.2f} in {rem}s)")

    print("\n" + "=" * 95)

    # Let's inspect the top 5 absolute largest switches of all time (past 90s elapsed)
    print("\n🏆 ALL-TIME TOP 5 LARGEST SWITCHES (PAST FIRST 90 SECONDS):")
    print("-" * 95)
    cur.execute("""
        SELECT 
            s.cycle_id, s.remaining_seconds, s.spot_price, c.strike_price, s.gap_dollars, 
            c.final_price, c.winning_outcome, (c.final_price - s.spot_price) as move
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED'
          AND s.elapsed_seconds >= 90
          AND (
            (c.winning_outcome = 'Up' AND s.gap_dollars < 0) OR
            (c.winning_outcome = 'Down' AND s.gap_dollars > 0)
          )
        ORDER BY ABS(s.gap_dollars) DESC
        LIMIT 5
    """)
    top_switches = cur.fetchall()
    for rank, row in enumerate(top_switches, 1):
        cid, rem, spot, strike, gap, final_p, winner, move = row
        print(f"#{rank} Cycle {cid} | T-{rem}s left | Gap was ${gap:+.2f} | Strike: ${strike:,.2f} -> Settled ${final_p:,.2f} ({winner.upper()} won | Moved ${move:+.2f})")

    conn.close()


if __name__ == "__main__":
    analyze_switches()
