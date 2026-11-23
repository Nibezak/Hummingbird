"""
Forensic Jump & Excursion Analysis Across Entire Database
"""
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. Total Recording Duration
cur.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM snapshots")
min_ts, max_ts, total_snaps = cur.fetchone()
cur.execute("SELECT MIN(cycle_id), MAX(cycle_id), COUNT(*) FROM cycles")
min_cid, max_cid, total_cycles = cur.fetchone()

start_dt = datetime.fromtimestamp(min_ts, tz=timezone.utc)
end_dt = datetime.fromtimestamp(max_ts, tz=timezone.utc)
total_hours = (max_ts - min_ts) / 3600.0

print("=" * 95)
print("⏱️ RECORDING DURATION & DATABASE TOTALS")
print("=" * 95)
print(f"• Total Data Span:       {total_hours:.2f} hours ({total_hours*60:.0f} minutes)")
print(f"• Start Time (UTC):      {start_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"• Latest Time (UTC):     {end_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"• Total 5-Minute Cycles: {total_cycles} cycles")
print(f"• Total 1-Sec Snapshots: {total_snaps:,} snapshots")
print("=" * 95)

# 2. Absolute Highest Upward Jump (From snapshot spot price to settlement)
cur.execute("""
    SELECT s.cycle_id, s.remaining_seconds, s.elapsed_seconds, s.spot_price, c.strike_price, c.final_price,
           (c.final_price - s.spot_price) AS jump_up
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.status = 'RESOLVED'
    ORDER BY jump_up DESC
    LIMIT 3
""")
top_jumps_up = cur.fetchall()

print("\n🚀 TOP 3 LARGEST UPWARD JUMPS (Spot to Settlement):")
print("-" * 95)
for r in top_jumps_up:
    cid, rem, elap, spot, strike, final_p, jump = r
    m, s = rem // 60, rem % 60
    print(f"• Jump: +${jump:,.2f} | Cycle {cid} | At T-{m}m {s:02d}s ({rem}s left, {elap}s elapsed)")
    print(f"  Spot: ${spot:,.2f} ➔ Final Settle: ${final_p:,.2f} (Strike: ${strike:,.2f})")

# 3. Absolute Largest Downward Plunge (From snapshot spot price to settlement)
cur.execute("""
    SELECT s.cycle_id, s.remaining_seconds, s.elapsed_seconds, s.spot_price, c.strike_price, c.final_price,
           (s.spot_price - c.final_price) AS plunge_down
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.status = 'RESOLVED'
    ORDER BY plunge_down DESC
    LIMIT 3
""")
top_plunges = cur.fetchall()

print("\n🔻 TOP 3 LARGEST DOWNWARD PLUNGES (Spot to Settlement):")
print("-" * 95)
for r in top_plunges:
    cid, rem, elap, spot, strike, final_p, plunge = r
    m, s = rem // 60, rem % 60
    print(f"• Plunge: -${plunge:,.2f} | Cycle {cid} | At T-{m}m {s:02d}s ({rem}s left, {elap}s elapsed)")
    print(f"  Spot: ${spot:,.2f} ➔ Final Settle: ${final_p:,.2f} (Strike: ${strike:,.2f})")

# 4. Largest Intraday 5-Minute Cycle Total Volatility Range (Max positive gap - Max negative gap)
cur.execute("""
    SELECT cycle_id, strike_price, final_price, winning_outcome, 
           max_positive_gap, max_negative_gap, (max_positive_gap - max_negative_gap) AS total_range
    FROM cycles
    WHERE status = 'RESOLVED'
    ORDER BY total_range DESC
    LIMIT 3
""")
top_ranges = cur.fetchall()

print("\n🌋 TOP 3 MOST VOLATILE 5-MINUTE CYCLES (Full Cycle Peak-to-Trough Range):")
print("-" * 95)
for r in top_ranges:
    cid, strike, final_p, winner, max_pos, max_neg, t_range = r
    print(f"• Total Volatility: ${t_range:,.2f} | Cycle {cid} | Winner: {winner.upper()}")
    print(f"  Peak: +${max_pos:,.2f} | Trough: ${max_neg:,.2f} | Strike: ${strike:,.2f} ➔ Settle: ${final_p:,.2f}")

# 5. Largest Moves By Time Left (What is the highest jump possible in the final 2m, 1m, 30s?)
print("\n⏱️ HIGHEST RECORDED JUMPS BY REMAINING TIME WINDOW:")
print("-" * 95)
windows = [
    ("Final 2 minutes (<= 120s left)", 120),
    ("Final 1.5 minutes (<= 90s left)", 90),
    ("Final 1 minute (<= 60s left)", 60),
    ("Final 30 seconds (<= 30s left)", 30),
    ("Final 15 seconds (<= 15s left)", 15),
]

for label, sec in windows:
    cur.execute("""
        SELECT MAX(ABS(c.final_price - s.spot_price))
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED' AND s.remaining_seconds <= ?
    """, (sec,))
    max_m = cur.fetchone()[0] or 0.0
    print(f"• {label:<35} ➔ Max price jump/drop recorded: ${max_m:,.2f}")

print("=" * 95)
conn.close()
