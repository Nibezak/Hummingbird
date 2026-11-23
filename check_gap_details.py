import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check cycles between 1795419600 (07:40 UTC / 10:40 EAT) and 1795434600 (11:50 UTC / 14:50 EAT)
cursor.execute('''
    SELECT cycle_id, start_time, status, winning_outcome, strike_price, final_price
    FROM cycles
    WHERE cycle_id >= 1795419600
    ORDER BY cycle_id ASC
''')
cycles = cursor.fetchall()

print(f"Cycles recorded since 07:40 UTC: {len(cycles)}")

# Check for gaps in cycle_id (each cycle is 300 seconds apart)
missing_cycles = []
if cycles:
    for i in range(len(cycles) - 1):
        curr_id = cycles[i][0]
        next_id = cycles[i+1][0]
        if next_id - curr_id > 300:
            missing_cycles.append((curr_id, next_id, (next_id - curr_id) // 300 - 1))

print(f"Missing cycle intervals: {missing_cycles}")

# Also inspect all trades from trade #163 onwards
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE trade_id >= 162
    ORDER BY trade_id ASC
''')
trades = cursor.fetchall()
print(f"\nTrades since #162: {len(trades)}")
for t in trades:
    print(t)

# Check snapshot count per cycle to see if recorder had downtime
cursor.execute('''
    SELECT cycle_id, COUNT(*)
    FROM snapshots
    WHERE cycle_id >= 1795419600
    GROUP BY cycle_id
    ORDER BY cycle_id ASC
''')
snap_counts = cursor.fetchall()
print("\nSnapshot count per cycle since 10:40 EAT:")
for sc in snap_counts:
    print(f"Cycle {sc[0]}: {sc[1]} snapshots")

conn.close()
