import sqlite3

conn = sqlite3.connect('c:/projects/btc-5m-recorder/btc_5m_data.db')
c = conn.cursor()

# Query all snapshots for resolved cycles where remaining_seconds <= 120 and remaining_seconds >= 15
c.execute('''
    SELECT s.remaining_seconds, s.spot_price, s.gap_dollars, c.strike_price, c.final_price, s.cycle_id
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.final_price IS NOT NULL AND s.remaining_seconds BETWEEN 15 AND 120
''')

rows = c.fetchall()

# Let's group by brackets: 
# 15-30s, 31-45s, 46-60s, 61-90s, 91-120s
brackets = {
    '15-30s': {'up_squeeze_max': 0.0, 'down_dump_max': 0.0, 'worst_cycle_up': None, 'worst_cycle_dn': None},
    '31-45s': {'up_squeeze_max': 0.0, 'down_dump_max': 0.0, 'worst_cycle_up': None, 'worst_cycle_dn': None},
    '46-60s': {'up_squeeze_max': 0.0, 'down_dump_max': 0.0, 'worst_cycle_up': None, 'worst_cycle_dn': None},
    '61-90s': {'up_squeeze_max': 0.0, 'down_dump_max': 0.0, 'worst_cycle_up': None, 'worst_cycle_dn': None},
    '91-120s': {'up_squeeze_max': 0.0, 'down_dump_max': 0.0, 'worst_cycle_up': None, 'worst_cycle_dn': None},
}

def get_bracket(rem):
    if 15 <= rem <= 30: return '15-30s'
    if 31 <= rem <= 45: return '31-45s'
    if 46 <= rem <= 60: return '46-60s'
    if 61 <= rem <= 90: return '61-90s'
    if 91 <= rem <= 120: return '91-120s'
    return None

for rem, spot, gap, strike, final, cid in rows:
    b = get_bracket(rem)
    if not b: continue
    
    # If gap was negative (DOWN was winning), did BTC squeeze UP and cross strike?
    # Or what was the maximum adverse surge?
    move = final - spot
    if gap < 0 and final > strike: # True reversal flip
        squeeze = final - spot
        deficit = abs(gap)
        if deficit > brackets[b]['up_squeeze_max']:
            brackets[b]['up_squeeze_max'] = deficit
            brackets[b]['worst_cycle_up'] = (cid, rem, deficit, squeeze)
            
    # If gap was positive (UP was winning), did BTC dump DOWN and cross strike?
    if gap > 0 and final < strike: # True reversal flip
        dump = spot - final
        deficit = gap
        if deficit > brackets[b]['down_dump_max']:
            brackets[b]['down_dump_max'] = deficit
            brackets[b]['worst_cycle_dn'] = (cid, rem, deficit, dump)

print("=== EMPIRICAL MAXIMUM ADVERSE REVERSALS BY TIME BRACKET (538 CYCLES) ===")
for b, data in brackets.items():
    print(f"\nBracket [{b}]:")
    print(f"  Max Flipped Lead for DOWN (UP Squeeze): ${data['up_squeeze_max']:.2f} (Cycle: {data['worst_cycle_up']})")
    print(f"  Max Flipped Lead for UP (DOWN Dump):    ${data['down_dump_max']:.2f} (Cycle: {data['worst_cycle_dn']})")
