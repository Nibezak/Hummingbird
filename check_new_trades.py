import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE trade_id > 158
    ORDER BY trade_id ASC
''')
for r in cursor.fetchall():
    print(r)

conn.close()
