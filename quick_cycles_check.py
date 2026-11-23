import sqlite3
conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM cycles")
print("Total cycles in DB:", cursor.fetchone()[0])
cursor.execute("SELECT cycle_id, winning_outcome FROM cycles WHERE cycle_id >= 1795427400 ORDER BY cycle_id ASC LIMIT 10")
for r in cursor.fetchall():
    print(r)
conn.close()
