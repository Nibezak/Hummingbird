import sqlite3
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome 
    FROM cycles 
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
''')
cycles = c.fetchall()
print(f"Total resolved cycles: {len(cycles)}")

brackets = [
    ('15-30s', 15, 30),
    ('31-45s', 31, 45),
    ('46-60s', 46, 60),
    ('61-90s', 61, 90),
    ('91-120s', 91, 120)
]

print(f"{'Bracket':<8} | {'Type':<8} | {'N':<4} | {'Med':<7} | {'90th':<7} | {'95th':<7} | {'98th':<7} | {'99th':<7} | {'Max':<7}")
print("-" * 75)

for b_name, min_r, max_r in brackets:
    squeezes = []
    dumps = []
    
    for cid, strike, final, winner in cycles:
        c.execute('''
            SELECT gap_dollars FROM snapshots 
            WHERE cycle_id = ? AND remaining_seconds BETWEEN ? AND ?
        ''', (cid, min_r, max_r))
        snaps = c.fetchall()
        
        cycle_squeezes = []
        cycle_dumps = []
        for (gap,) in snaps:
            if gap is None: continue
            if gap < 0 and final > strike:
                cycle_squeezes.append(abs(gap))
            elif gap > 0 and final < strike:
                cycle_dumps.append(gap)
                
        if cycle_squeezes:
            squeezes.append(max(cycle_squeezes))
        if cycle_dumps:
            dumps.append(max(cycle_dumps))
            
    sq = np.array(squeezes) if squeezes else np.array([0])
    dp = np.array(dumps) if dumps else np.array([0])
    
    print(f"{b_name:<8} | Squeeze  | {len(sq):<4} | ${np.median(sq):.1f} | ${np.percentile(sq, 90):.1f} | ${np.percentile(sq, 95):.1f} | ${np.percentile(sq, 98):.1f} | ${np.percentile(sq, 99):.1f} | ${np.max(sq):.1f}")
    print(f"{b_name:<8} | Dump     | {len(dp):<4} | ${np.median(dp):.1f} | ${np.percentile(dp, 90):.1f} | ${np.percentile(dp, 95):.1f} | ${np.percentile(dp, 98):.1f} | ${np.percentile(dp, 99):.1f} | ${np.max(dp):.1f}")

conn.close()
