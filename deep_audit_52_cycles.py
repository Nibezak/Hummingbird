import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome, status, datetime(start_time, 'unixepoch')
    FROM cycles 
    WHERE cycle_id >= 1795298400 
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()
print(f"Total cycles in this window: {len(cycles)}")

# Let's inspect the adaptive boundaries currently active
c.execute('SELECT bracket, safe_up_gap, safe_down_gap, record_up_squeeze, record_down_dump FROM adaptive_safe_boundaries')
bounds = c.fetchall()
print("\n=== CURRENT ACTIVE BOUNDARIES ===")
for b in bounds:
    print(f"  {b[0]:<8} | Bot A: UP >= +{b[1]:.1f}, DN <= {b[2]:.1f} | Squeeze Rec: {b[3]:.1f}, Dump Rec: {b[4]:.1f}")

qual_A = []
qual_B = []
near_misses = []

print(f"\n{'Cycle':<11} | {'Strike':<9} | {'Final':<9} | {'Win':<5} | {'Max UP Gap':<12} | {'Max DN Gap':<12} | {'Min Ask UP':<10} | {'Min Ask DN':<10}")
print("-" * 95)

for cid, strike, final, winner, status, st_time in cycles:
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds BETWEEN 15 AND 120
        ORDER BY remaining_seconds DESC
    ''', (cid,))
    snaps = c.fetchall()
    if not snaps: continue
    
    max_up = max((s[2] for s in snaps if s[2] is not None), default=None)
    min_dn = min((s[2] for s in snaps if s[2] is not None), default=None)
    min_up_ask = min((s[3] for s in snaps if s[3] is not None), default=None)
    min_dn_ask = min((s[4] for s in snaps if s[4] is not None), default=None)
    
    max_up_s = f"+{max_up:.1f}" if max_up is not None else "N/A"
    min_dn_s = f"-{abs(min_dn):.1f}" if min_dn is not None else "N/A"
    strike_s = f"{strike:.1f}" if strike is not None else "N/A"
    final_s = f"{final:.1f}" if final is not None else "N/A"
    win_s = winner if winner else "ACT"
    
    # Check if any snapshot met qualifications
    for rem, spot, gap, up_ask, dn_ask, up_dep, dn_dep in snaps:
        if gap is None: continue
        
        # Thresholds
        if rem >= 91:
            up_A, dn_A = 124.2, -115.4
            up_B, dn_B = 113.4, -105.3
        elif rem >= 61:
            up_A, dn_A = 136.1, -106.3
            up_B, dn_B = 124.3, -97.1
        elif rem >= 46:
            up_A, dn_A = 146.8, -128.2
            up_B, dn_B = 134.1, -117.1
        elif rem >= 31:
            up_A, dn_A = 179.8, -86.2
            up_B, dn_B = 164.1, -78.7
        else:
            up_A, dn_A = 93.5, -82.5
            up_B, dn_B = 85.4, -75.3
            
        # Bot A
        if gap >= up_A and up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
            qual_A.append((cid, rem, 'UP', gap, up_ask, up_dep))
        elif gap <= dn_A and dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
            qual_A.append((cid, rem, 'DN', gap, dn_ask, dn_dep))
            
        # Bot B
        if gap >= up_B and up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
            qual_B.append((cid, rem, 'UP', gap, up_ask, up_dep))
        elif gap <= dn_B and dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
            qual_B.append((cid, rem, 'DN', gap, dn_ask, dn_dep))

        # Check near misses: gap within 85% of threshold and ask <= 0.96
        if gap >= (up_B * 0.8) and up_ask and 0.70 <= up_ask <= 0.96:
            near_misses.append((cid, rem, 'UP', gap, up_B, up_ask, winner))
        elif gap <= (dn_B * 0.8) and dn_ask and 0.70 <= dn_ask <= 0.96:
            near_misses.append((cid, rem, 'DN', gap, dn_B, dn_ask, winner))
            
    if (max_up and max_up > 70) or (min_dn and min_dn < -70):
        print(f"{cid:<11} | {strike_s:<9} | {final_s:<9} | {win_s:<5} | {max_up_s:<12} | {min_dn_s:<12} | {str(min_up_ask):<10} | {str(min_dn_ask):<10}")

print(f"\nQualifying trades found for Bot A: {len(qual_A)}")
print(f"Qualifying trades found for Bot B: {len(qual_B)}")
print(f"Near misses recorded: {len(near_misses)}")

if near_misses:
    print("\nSample near misses:")
    for nm in near_misses[:10]:
        print(f"  Cycle {nm[0]} @ T-{nm[1]}s | Dir: {nm[2]} | Gap: {nm[3]:.1f} (Needed: {nm[4]:.1f}) | Ask: {nm[5]} | Settled: {nm[6]}")

conn.close()
