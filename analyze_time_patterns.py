import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

print("Cycle 1795364400 snapshots in final 2 minutes:")
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, up_ask_depth, down_best_ask, down_ask_depth
    FROM snapshots
    WHERE cycle_id = 1795364400 AND remaining_seconds BETWEEN 15 AND 120
    ORDER BY elapsed_seconds ASC
    LIMIT 10
''')
for s in cursor.fetchall():
    print(s)

print("\nCycle 1795366800 snapshots in final 2 minutes:")
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, up_ask_depth, down_best_ask, down_ask_depth
    FROM snapshots
    WHERE cycle_id = 1795366800 AND remaining_seconds BETWEEN 15 AND 120
    ORDER BY elapsed_seconds ASC
    LIMIT 10
''')
for s in cursor.fetchall():
    print(s)

conn.close()
