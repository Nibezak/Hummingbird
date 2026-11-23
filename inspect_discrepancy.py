import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get details of cycle 1795350300
cursor.execute('''
    SELECT cycle_id, slug, title, start_time, end_time, strike_price, final_price, winning_outcome, status
    FROM cycles
    WHERE cycle_id = 1795350300
''')
cycle = cursor.fetchone()
print("Cycle 1795350300 row in DB:")
print(cycle)

# Get details of trade #140 and #141
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, winning_outcome, is_winner, pnl, roi_pct, status, final_settle_price, resolved_at
    FROM dry_run_trades
    WHERE cycle_id = 1795350300
''')
trades = cursor.fetchall()
print("\nTrades for cycle 1795350300 in DB:")
for t in trades:
    print(t)

# Also check snapshots for 1795350300: spot_price at start, spot_price at end
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, recorded_at
    FROM snapshots
    WHERE cycle_id = 1795350300
    ORDER BY elapsed_seconds ASC
''')
snaps = cursor.fetchall()
print(f"\nSnapshots count: {len(snaps)}")
if snaps:
    print("First 3 snapshots:")
    for s in snaps[:3]: print(s)
    print("Last 5 snapshots:")
    for s in snaps[-5:]: print(s)

conn.close()
