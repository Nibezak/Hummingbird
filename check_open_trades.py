import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, shares, status
    FROM dry_run_trades
    WHERE status = 'OPEN'
''')
open_trades = cursor.fetchall()
print(f"Open trades right now: {len(open_trades)}")
for ot in open_trades:
    print(ot)

# Also check latest cycle
cursor.execute("SELECT cycle_id, start_time, strike_price, final_price, winning_outcome, status FROM cycles ORDER BY cycle_id DESC LIMIT 2")
print("\nLatest cycles:")
for c in cursor.fetchall():
    print(c)

conn.close()
