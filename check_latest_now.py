import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute("SELECT MAX(trade_id), COUNT(*) FROM dry_run_trades")
print("Latest trade ID:", cursor.fetchone())

cursor.execute("SELECT id, session_id, balance FROM wallet")
print("Wallets:", cursor.fetchall())

conn.close()
