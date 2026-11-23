import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# Group snapshots by UTC hour
c.execute('''
    SELECT 
        cast(strftime('%H', recorded_at) as integer) as hr,
        avg(abs(gap_dollars)),
        max(abs(gap_dollars)),
        avg(up_ask_depth + down_ask_depth),
        count(distinct cycle_id)
    FROM snapshots
    WHERE remaining_seconds BETWEEN 15 AND 120
    GROUP BY hr
    ORDER BY hr ASC
''')
hours_data = c.fetchall()

print(f"{'Hour (UTC)':<12} | {'Sessions':<22} | {'Avg BTC Gap':<14} | {'Max BTC Gap':<14} | {'Avg Total Depth':<16} | {'Cycles Sampled':<14}")
print("-" * 96)

for hr, avg_gap, max_gap, avg_depth, cyc_cnt in hours_data:
    session = ""
    if 0 <= hr < 8: session = "Asia / Late US"
    elif 8 <= hr < 14: session = "London / Europe Open"
    elif 14 <= hr < 21: session = "US Regular Hours"
    else: session = "US Close / Globex"
    
    print(f"{hr:02d}:00 UTC     | {session:<22} | ${avg_gap:<13.1f} | ${max_gap:<13.1f} | ${avg_depth:<15.0f} | {cyc_cnt:<14}")

conn.close()
