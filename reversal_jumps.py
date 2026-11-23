"""
Reversal Specific Jump Query
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 90)
print("🔄 LARGEST ADVERSE REVERSALS (Losing Side Jumping Across Strike to Win)")
print("=" * 90)

windows = [
    ("Final 2 minutes (<= 120s left)", 120),
    ("Final 1.5 minutes (<= 90s left)", 90),
    ("Final 1 minute (<= 60s left)", 60),
    ("Final 30 seconds (<= 30s left)", 30),
    ("Final 15 seconds (<= 15s left)", 15),
]

for label, sec in windows:
    # Max DOWN to UP reversal
    cur.execute("""
        SELECT s.cycle_id, s.remaining_seconds, s.spot_price, c.strike_price, s.gap_dollars, c.final_price,
               (c.final_price - s.spot_price) AS squeeze
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Up' AND s.gap_dollars < 0
          AND s.remaining_seconds <= ?
        ORDER BY s.gap_dollars ASC
        LIMIT 1
    """, (sec,))
    dn_row = cur.fetchone()

    # Max UP to DOWN reversal
    cur.execute("""
        SELECT s.cycle_id, s.remaining_seconds, s.spot_price, c.strike_price, s.gap_dollars, c.final_price,
               (s.spot_price - c.final_price) AS dump
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED' AND c.winning_outcome = 'Down' AND s.gap_dollars > 0
          AND s.remaining_seconds <= ?
        ORDER BY s.gap_dollars DESC
        LIMIT 1
    """, (sec,))
    up_row = cur.fetchone()

    print(f"\n⏱️ {label}:")
    if dn_row:
        cid, rem, spot, strike, gap, final_p, sq = dn_row
        print(f"  🔴 Max DOWN Squeeze to UP: Gap was ${gap:,.2f} at T-{rem}s ➔ Final: ${final_p:,.2f} (Jumped +${sq:,.2f} | Cycle {cid})")
    else:
        print("  🔴 Max DOWN Squeeze to UP: None")

    if up_row:
        cid, rem, spot, strike, gap, final_p, dmp = up_row
        print(f"  🟢 Max UP Dump to DOWN:    Gap was +${gap:,.2f} at T-{rem}s ➔ Final: ${final_p:,.2f} (Dumped -${dmp:,.2f} | Cycle {cid})")
    else:
        print("  🟢 Max UP Dump to DOWN: None")

conn.close()
