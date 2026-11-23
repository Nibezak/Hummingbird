import sqlite3
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT gap_dollars FROM snapshots 
    WHERE remaining_seconds BETWEEN 15 AND 120 
      AND up_best_ask BETWEEN 0.70 AND 0.95 
      AND up_ask_depth >= 5.0
''')
up_gaps = [r[0] for r in c.fetchall() if r[0] is not None]

c.execute('''
    SELECT gap_dollars FROM snapshots 
    WHERE remaining_seconds BETWEEN 15 AND 120 
      AND down_best_ask BETWEEN 0.70 AND 0.95 
      AND down_ask_depth >= 5.0
''')
dn_gaps = [r[0] for r in c.fetchall() if r[0] is not None]

print(f"Total snapshots where UP Ask is 0.70-0.95: {len(up_gaps)}")
if up_gaps:
    up_arr = np.array(up_gaps)
    print(f"  UP Gaps: 10th: +${np.percentile(up_arr, 10):.1f} | Med: +${np.median(up_arr):.1f} | 75th: +${np.percentile(up_arr, 75):.1f} | 90th: +${np.percentile(up_arr, 90):.1f} | 95th: +${np.percentile(up_arr, 95):.1f} | Max: +${np.max(up_arr):.1f}")

print(f"\nTotal snapshots where DOWN Ask is 0.70-0.95: {len(dn_gaps)}")
if dn_gaps:
    dn_arr = np.array([abs(g) for g in dn_gaps])
    print(f"  DOWN Gaps (abs): 10th: ${np.percentile(dn_arr, 10):.1f} | Med: ${np.median(dn_arr):.1f} | 75th: ${np.percentile(dn_arr, 75):.1f} | 90th: ${np.percentile(dn_arr, 90):.1f} | 95th: ${np.percentile(dn_arr, 95):.1f} | Max: ${np.max(dn_arr):.1f}")

conn.close()
