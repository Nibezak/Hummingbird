import sqlite3

conn = sqlite3.connect('c:/projects/btc-5m-recorder/btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT s.cycle_id, s.timestamp, s.spot_price, s.remaining_seconds, s.gap_dollars, c.strike_price, c.final_price
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.final_price IS NOT NULL
''')

rows = c.fetchall()
print(f'Total snapshot rows joined with resolved cycles: {len(rows)}')

all_moves_45_60 = []
flips_45_60 = []

for cid, ts, spot, rem, gap, strike, final in rows:
    if 45 <= rem <= 60:
        move = final - spot
        initial_gap = gap
        final_gap = final - strike
        all_moves_45_60.append((move, cid, rem, spot, final, initial_gap, final_gap))
        # check if it flipped
        if (initial_gap < 0 and final_gap > 0): # UP squeeze reversal
            flips_45_60.append(('UP_SQUEEZE_FLIP', abs(initial_gap), move, cid, rem, initial_gap, final_gap))
        elif (initial_gap > 0 and final_gap < 0): # DOWN dump reversal
            flips_45_60.append(('DOWN_DUMP_FLIP', abs(initial_gap), abs(move), cid, rem, initial_gap, final_gap))

all_moves_45_60.sort(key=lambda x: x[0], reverse=True)

print('\n=== TOP 5 LARGEST ABSOLUTE UPWARD PRICE MOVES (T-45s to T-60s) ===')
for m in all_moves_45_60[:5]:
    print(f'Move: +${m[0]:.2f} | Cycle: {m[1]} | Rem: {m[2]}s | Initial Gap: ${m[5]:.2f} -> Final Gap: ${m[6]:.2f}')

print('\n=== TOP 5 LARGEST ABSOLUTE DOWNWARD PRICE MOVES (T-45s to T-60s) ===')
for m in all_moves_45_60[-5:]:
    print(f'Move: ${m[0]:.2f} | Cycle: {m[1]} | Rem: {m[2]}s | Initial Gap: ${m[5]:.2f} -> Final Gap: ${m[6]:.2f}')

print('\n=== ALL FLIPS / REVERSALS IN T-45s to T-60s (Sorted by Deficit Overcome) ===')
flips_45_60.sort(key=lambda x: x[1], reverse=True)
for f in flips_45_60[:15]:
    print(f'{f[0]}: Deficit Overcome: ${f[1]:.2f} | Total Move: ${f[2]:.2f} | Cycle: {f[3]} | Rem: {f[4]}s | Start Gap: ${f[5]:.2f} -> End Gap: ${f[6]:.2f}')
