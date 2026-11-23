import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

for cid in [1795203000, 1795204200, 1795350300]:
    cursor.execute("SELECT cycle_id, strike_price, final_price, winning_outcome, status, updated_at FROM cycles WHERE cycle_id = ?", (cid,))
    print(cursor.fetchone())

conn.close()
