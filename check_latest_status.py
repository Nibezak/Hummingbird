import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get the absolute latest cycles up to now
cursor.execute('''
    SELECT cycle_id, start_time, end_time, strike_price, final_price, winning_outcome, max_positive_gap, max_negative_gap, status
    FROM cycles
    ORDER BY cycle_id DESC
    LIMIT 10
''')
latest_cycles = cursor.fetchall()
print("Latest 10 cycles:")
for c in latest_cycles:
    print(c)

# Get the latest trades up to now
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    ORDER BY trade_id DESC
    LIMIT 10
''')
print("\nLatest 10 trades:")
for t in cursor.fetchall():
    print(t)

# Check snapshots count
cursor.execute("SELECT COUNT(*) FROM snapshots")
print(f"\nTotal snapshots in db: {cursor.fetchone()[0]}")

# Check current active safe boundaries
cursor.execute("SELECT * FROM adaptive_safe_boundaries")
print("\nCurrent adaptive_safe_boundaries:")
for b in cursor.fetchall():
    print(b)

conn.close()
