"""
Find Point of No Return for Various Gap Sizes
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

gaps = [20, 30, 40, 50, 60, 75, 100, 120, 150]

print("=" * 80)
print("🎯 EXACT POINT OF NO RETURN (BY GAP SIZE)")
print("Across 150 Recorded 5-Minute Cycles (19,000+ Ticks)")
print("=" * 80)

for g in gaps:
    # 1. UP gap >= g that ended up resolving DOWN
    cur.execute("""
        SELECT MIN(s.remaining_seconds), MAX(s.remaining_seconds), s.cycle_id, s.gap_dollars
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Down'
          AND s.gap_dollars >= ?
    """, (g,))
    up_row = cur.fetchone()
    # The SMALLEST remaining_seconds where a reversal was still possible:
    min_rem_up = up_row[0]

    # 2. DOWN gap <= -g that ended up resolving UP
    cur.execute("""
        SELECT MIN(s.remaining_seconds), MAX(s.remaining_seconds), s.cycle_id, s.gap_dollars
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Up'
          AND s.gap_dollars <= -?
    """, (g,))
    dn_row = cur.fetchone()
    min_rem_dn = dn_row[0]

    # The point of no return is when remaining_seconds is LESS than the minimum remaining time a reversal ever happened!
    # If a reversal happened as late as T-63s, then under 63s it has NEVER returned!
    print(f"\n📏 For a ${g} Gap:")
    if min_rem_up is not None:
        print(f"  • UP Reversal: Latest dump occurred with {min_rem_up}s remaining (T-{min_rem_up//60}m {min_rem_up%60:02d}s).")
        print(f"    ➔ Under {min_rem_up} seconds, an UP gap of +${g} has 100% NEVER returned!")
    else:
        print(f"  • UP Reversal: Has NEVER reversed at ANY point in 5 minutes (0 occurrences)!")

    if min_rem_dn is not None:
        print(f"  • DOWN Reversal: Latest squeeze occurred with {min_rem_dn}s remaining (T-{min_rem_dn//60}m {min_rem_dn%60:02d}s).")
        print(f"    ➔ Under {min_rem_dn} seconds, a DOWN gap of -${g} has 100% NEVER returned!")
    else:
        print(f"  • DOWN Reversal: Has NEVER reversed at ANY point in 5 minutes (0 occurrences)!")

conn.close()
