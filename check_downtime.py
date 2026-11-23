import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check latest cycle and snapshot
cursor.execute("SELECT MAX(cycle_id), MAX(start_time), COUNT(*) FROM cycles")
print("Latest cycle in DB:", cursor.fetchone())

cursor.execute("SELECT MAX(id), MAX(timestamp), MAX(recorded_at), COUNT(*) FROM snapshots")
print("Latest snapshot in DB:", cursor.fetchone())

# Check latest trade
cursor.execute("SELECT MAX(trade_id), MAX(call_time), COUNT(*) FROM dry_run_trades")
print("Latest trade in DB:", cursor.fetchone())

cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
print("Wallets:", cursor.fetchall())

conn.close()
