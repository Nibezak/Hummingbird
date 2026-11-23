import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check latest trades right now
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    ORDER BY trade_id DESC
    LIMIT 10
''')
print("Latest 10 trades right now:")
for t in cursor.fetchall():
    print(t)

# Check wallets
cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
print("\nWallets right now:")
for w in cursor.fetchall():
    print(w)

conn.close()
