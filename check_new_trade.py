import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get latest trades after #184
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, shares, pnl, is_winner, status, rule_triggered
    FROM dry_run_trades
    WHERE trade_id >= 184
    ORDER BY trade_id ASC
''')
trades = cursor.fetchall()

print(f"Total trades since #184: {len(trades)}")
for t in trades:
    print(t)

# Check wallets
cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
print("\nWallets:")
for w in cursor.fetchall():
    print(w)

# Also check latest cycle in cycles table
cursor.execute("SELECT cycle_id, start_time, strike_price, final_price, winning_outcome, status FROM cycles ORDER BY cycle_id DESC LIMIT 3")
print("\nLatest cycles:")
for c in cursor.fetchall():
    print(c)

conn.close()
