import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT trade_id, session_id, cycle_id, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE trade_id >= 200
    ORDER BY trade_id ASC
''')
for r in cursor.fetchall():
    print(r)

cursor.execute("SELECT id, session_id, balance FROM wallet")
print("Wallets:", cursor.fetchall())
conn.close()
