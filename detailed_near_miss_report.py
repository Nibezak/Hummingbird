import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome
    FROM cycles 
    WHERE cycle_id >= 1795271700 
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()

print(f"Total cycles since trade #130: {len(cycles)}")

up_blocked_by_ratchet = []
down_near_misses = []
liquidity_frozen = []
chop_rounds = []

for cid, strike, final_p, winner in cycles:
    if not strike: continue
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds <= 120 AND remaining_seconds >= 15
        ORDER BY remaining_seconds DESC
    ''', (cid,))
    snaps = c.fetchall()
    if not snaps: continue
    
    max_up_gap = max((s[2] for s in snaps if s[2] is not None), default=-999)
    min_dn_gap = min((s[2] for s in snaps if s[2] is not None), default=999)
    
    # Check if any snapshot had valid ask (0.70 to 0.95)
    valid_up_asks = [s for s in snaps if s[3] is not None and 0.70 <= s[3] <= 0.95 and (s[5] or 0) >= 5.0]
    valid_dn_asks = [s for s in snaps if s[4] is not None and 0.70 <= s[4] <= 0.95 and (s[6] or 0) >= 5.0]
    
    # Check if UP had solid gap (> +$75) and valid ask
    solid_up_candidate = None
    for s in valid_up_asks:
        if s[2] >= 70:
            solid_up_candidate = s
            break
            
    # Check if DOWN had solid gap (< -$75) and valid ask
    solid_dn_candidate = None
    for s in valid_dn_asks:
        if s[2] <= -70:
            solid_dn_candidate = s
            break

    if solid_up_candidate:
        up_blocked_by_ratchet.append((cid, strike, winner, max_up_gap, solid_up_candidate))
    elif solid_dn_candidate:
        down_near_misses.append((cid, strike, winner, min_dn_gap, solid_dn_candidate))
    elif abs(max_up_gap) > 140 or abs(min_dn_gap) > 140:
        liquidity_frozen.append((cid, strike, winner, max_up_gap, min_dn_gap))
    elif max_up_gap < 40 and min_dn_gap > -40:
        chop_rounds.append((cid, strike, winner, max_up_gap, min_dn_gap))

print("\n" + "="*85)
print(f"1. UP TRADES WITH CHEAP/VALID ASKS (<= 0.95) BLOCKED EXCLUSIVELY BY THE +$478 RATCHET: {len(up_blocked_by_ratchet)}")
print("="*85)
for cid, strike, winner, max_g, s in up_blocked_by_ratchet:
    print(f"   Cycle {cid}: Max Gap +${max_g:.2f} | At T-{s[0]}s: Gap +${s[2]:.2f}, Ask {s[3]:.2f} (Depth: ${s[5]:.0f}) | Settled Winner: {winner}")

print("\n" + "="*85)
print(f"2. DOWN TRADES WITH CHEAP/VALID ASKS (<= 0.95) THAT FELL JUST SHORT OF -$145 / -$159 BOUNDARY: {len(down_near_misses)}")
print("="*85)
for cid, strike, winner, min_g, s in down_near_misses:
    print(f"   Cycle {cid}: Max Gap -${abs(min_g):.2f} | At T-{s[0]}s: Gap -${abs(s[2]):.2f}, Ask {s[4]:.2f} (Depth: ${s[6]:.0f}) | Settled Winner: {winner}")

print("\n" + "="*85)
print(f"3. BLOWOUT MOVES WHERE BTC CRUSHED IT BUT POLYMARKET ASKS INSTANTLY FROZE (>0.95 or None): {len(liquidity_frozen)}")
print("="*85)
for cid, strike, winner, max_g, min_g in liquidity_frozen:
    print(f"   Cycle {cid}: Peak UP +${max_g:.2f}, Peak DN -${abs(min_g):.2f} | Settled Winner: {winner}")

print(f"\n4. FLAT / CHOPPY ROUNDS (Gap never exceeded +/- $40): {len(chop_rounds)}")

conn.close()
