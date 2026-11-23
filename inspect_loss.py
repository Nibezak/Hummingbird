import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get latest trades
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, shares, pnl, is_winner, status, rule_triggered, final_settle_price
    FROM dry_run_trades
    ORDER BY trade_id DESC
    LIMIT 10
''')
trades = cursor.fetchall()

print("Latest 10 trades:")
for t in trades:
    print(t)

# Check wallets
cursor.execute("SELECT id, session_id, balance, initial_balance FROM wallet")
print("\nWallets:")
for w in cursor.fetchall():
    print(w)

conn.close()
