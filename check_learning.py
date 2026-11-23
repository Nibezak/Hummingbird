import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

print("Cycle 1795404000 (+639 surge):")
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, up_ask_depth, down_best_ask, down_ask_depth
    FROM snapshots
    WHERE cycle_id = 1795404000 AND remaining_seconds BETWEEN 15 AND 120
    ORDER BY elapsed_seconds ASC
    LIMIT 6
''')
for s in cursor.fetchall():
    print(s)

print("\nCycle 1795404300 (-387 dump):")
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, up_ask_depth, down_best_ask, down_ask_depth
    FROM snapshots
    WHERE cycle_id = 1795404300 AND remaining_seconds BETWEEN 15 AND 120
    ORDER BY elapsed_seconds ASC
    LIMIT 6
''')
for s in cursor.fetchall():
    print(s)

conn.close()
