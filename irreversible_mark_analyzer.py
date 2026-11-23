"""
Irreversible Time Mark Analyzer
===============================
Analyzes the entire 1-second snapshot database to answer:
1. At what exact remaining time mark does a Bitcoin price gap NEVER return?
2. What is the maximum possible price move Bitcoin has EVER made in the final:
   - 120s (2m)
   - 90s (1.5m)
   - 60s (1m)
   - 45s
   - 30s
   - 15s
3. What is the guaranteed 100% 'point of no return'?
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")


def analyze_irreversibility():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM cycles WHERE status = 'RESOLVED'")
    total_cycles = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM snapshots")
    total_snaps = cur.fetchone()[0]

    print("=" * 90)
    print(f"🔬 EMPIRICAL POINT-OF-NO-RETURN ANALYSIS ({total_cycles} CYCLES, {total_snaps:,} SNAPSHOTS)")
    print("=" * 90)

    # Time marks to test (remaining seconds)
    time_marks = [150, 120, 100, 90, 75, 60, 45, 30, 20, 15, 10]

    print(f"{'Time Mark Left':<18} | {'Max Squeeze to UP':<20} | {'Max Dump to DOWN':<20} | {'Max Any Move':<15} | {'100% Never Return Gap'}")
    print("-" * 90)

    for sec in time_marks:
        # 1. Largest negative gap at <= sec that reversed to UP
        cur.execute("""
            SELECT s.cycle_id, s.remaining_seconds, s.gap_dollars, (c.final_price - s.spot_price)
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Up' AND s.gap_dollars < 0
              AND s.remaining_seconds <= ?
            ORDER BY s.gap_dollars ASC
            LIMIT 1
        """, (sec,))
        dn_rev = cur.fetchone()
        max_dn_rev_gap = abs(dn_rev[2]) if dn_rev else 0.0

        # 2. Largest positive gap at <= sec that reversed to DOWN
        cur.execute("""
            SELECT s.cycle_id, s.remaining_seconds, s.gap_dollars, (c.final_price - s.spot_price)
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Down' AND s.gap_dollars > 0
              AND s.remaining_seconds <= ?
            ORDER BY s.gap_dollars DESC
            LIMIT 1
        """, (sec,))
        up_rev = cur.fetchone()
        max_up_rev_gap = up_rev[2] if up_rev else 0.0

        # 3. Maximum absolute move from spot to settlement at <= sec
        cur.execute("""
            SELECT MAX(ABS(c.final_price - s.spot_price))
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' AND s.remaining_seconds <= ?
        """, (sec,))
        max_move = cur.fetchone()[0] or 0.0

        mins = sec // 60
        s = sec % 60
        time_str = f"T-{mins}m {s:02d}s ({sec}s)"
        
        dn_str = f"-${max_dn_rev_gap:.2f}" if max_dn_rev_gap > 0 else "$0.00"
        up_str = f"+${max_up_rev_gap:.2f}" if max_up_rev_gap > 0 else "$0.00"
        move_str = f"${max_move:.2f}"
        
        # Safe threshold to 100% never return:
        safe_gap = max(max_dn_rev_gap, max_up_rev_gap) + 1.0
        safe_str = f"Gap > ${safe_gap:.1f}"

        print(f"{time_str:<18} | {dn_str:<20} | {up_str:<20} | {move_str:<15} | {safe_str}")

    print("=" * 90)

    # Now let's see: for fixed gaps ($25, $50, $75, $100), at what time mark do they become 100% safe?
    print("\n🎯 POINT OF NO RETURN FOR SPECIFIC PRICE GAPS:")
    print("-" * 90)
    for target_gap in [25.0, 50.0, 75.0, 100.0, 150.0]:
        # What is the latest remaining second where a gap >= target_gap reversed?
        cur.execute("""
            SELECT MAX(s.remaining_seconds)
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' 
              AND (
                (c.winning_outcome = 'Down' AND s.gap_dollars >= ?) OR
                (c.winning_outcome = 'Up' AND s.gap_dollars <= -?)
              )
        """, (target_gap, target_gap))
        last_reversal_sec = cur.fetchone()[0]
        
        if last_reversal_sec is None:
            print(f"• Gap >= ${target_gap:,.2f}: Has NEVER reversed at ANY point in the 5 minutes!")
        else:
            m = last_reversal_sec // 60
            sec_rem = last_reversal_sec % 60
            print(f"• Gap >= ${target_gap:,.2f}: Last reversal happened at T-{m}m {sec_rem:02d}s ({last_reversal_sec}s remaining).")
            print(f"  ➔ 100% SAFE POINT OF NO RETURN: Under {last_reversal_sec} seconds (T-{last_reversal_sec}s), a ${target_gap:,.2f} gap has NEVER returned (100.0% win rate)!")

    print("=" * 90)
    conn.close()


if __name__ == "__main__":
    analyze_irreversibility()
