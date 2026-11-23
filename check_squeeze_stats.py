import sqlite3
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price 
    FROM cycles 
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
''')
cycles = c.fetchall()

squeezes_61_90 = []
for cid, strike, final in cycles:
    c.execute('SELECT gap_dollars FROM snapshots WHERE cycle_id = ? AND remaining_seconds BETWEEN 61 AND 90', (cid,))
    for (g,) in c.fetchall():
        if g is not None and g < 0 and final > strike:
            squeezes_61_90.append(abs(g))

print(f"Total adverse UP squeezes in 61-90s: {len(squeezes_61_90)}")
sq_arr = np.array(squeezes_61_90)
print(f"Median: ${np.median(sq_arr):.2f}")
print(f"90th:   ${np.percentile(sq_arr, 90):.2f}")
print(f"95th:   ${np.percentile(sq_arr, 95):.2f}")
print(f"98th:   ${np.percentile(sq_arr, 98):.2f}")
print(f"Max:    ${np.max(sq_arr):.2f}")

conn.close()
