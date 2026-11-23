import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# Get all cycles since trade #130 (cycle 1795271700)
c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome, status, datetime(start_time, 'unixepoch')
    FROM cycles 
    WHERE cycle_id > 1795271700 
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()
print(f"Total cycles since Trade #130: {len(cycles)}")

# Let's check adaptive safe boundaries
c.execute('SELECT bracket, min_remaining, max_remaining, safe_up_gap, safe_down_gap, record_up_squeeze, record_down_dump FROM adaptive_safe_boundaries')
bounds = c.fetchall()
print("\n=== ACTIVE SAFE BOUNDARIES ===")
for b in bounds:
    print(f"  {b[0]:<8} (T-{b[1]}-{b[2]}s): Bot A UP >= +{b[3]:.1f}, DN <= {b[4]:.1f} | Bot B UP >= +{b[6]*1.05:.1f}, DN <= -{b[5]*1.05:.1f}")

total_snaps_in_window = 0
snaps_in_late_round = 0 # 15 <= rem <= 120

qualifying_bot_A = []
qualifying_bot_B = []

# Near misses breakdown
gap_met_but_ask_bad = []
gap_met_but_ask_none = []
ask_good_but_gap_short = []

for cid, strike, final, winner, status, st_time in cycles:
    if not strike: continue
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ? 
        ORDER BY id ASC
    ''', (cid,))
    snaps = c.fetchall()
    total_snaps_in_window += len(snaps)
    
    for rem, spot, gap, up_ask, dn_ask, up_dep, dn_dep in snaps:
        if rem > 120 or rem < 15:
            continue
        snaps_in_late_round += 1
        if gap is None:
            continue
            
        # Determine active threshold for rem
        if rem >= 91:
            up_A, dn_A = 123.0, -115.3
            up_B, dn_B = 112.4, -105.3
        elif rem >= 61:
            up_A, dn_A = 131.6, -105.0
            up_B, dn_B = 120.2, -95.9
        elif rem >= 46:
            up_A, dn_A = 109.5, -128.2
            up_B, dn_B = 100.0, -117.1
        elif rem >= 31:
            up_A, dn_A = 148.9, -85.8
            up_B, dn_B = 136.0, -78.3
        else:
            up_A, dn_A = 93.5, -82.4
            up_B, dn_B = 85.4, -75.3

        # Check Bot A criteria
        # UP
        if gap >= up_A:
            if up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
                qualifying_bot_A.append((cid, rem, 'UP', gap, up_ask, up_dep, winner))
            elif up_ask and up_ask > 0.95:
                gap_met_but_ask_bad.append((cid, rem, 'UP', gap, up_ask))
            elif up_ask is None:
                gap_met_but_ask_none.append((cid, rem, 'UP', gap))
        # DOWN
        elif gap <= dn_A:
            if dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
                qualifying_bot_A.append((cid, rem, 'DOWN', gap, dn_ask, dn_dep, winner))
            elif dn_ask and dn_ask > 0.95:
                gap_met_but_ask_bad.append((cid, rem, 'DOWN', gap, dn_ask))
            elif dn_ask is None:
                gap_met_but_ask_none.append((cid, rem, 'DOWN', gap))

        # Check Bot B criteria
        if gap >= up_B:
            if up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
                qualifying_bot_B.append((cid, rem, 'UP', gap, up_ask, up_dep, winner))
        elif gap <= dn_B:
            if dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
                qualifying_bot_B.append((cid, rem, 'DOWN', gap, dn_ask, dn_dep, winner))

        # Ask was juicy (0.70 to 0.92) but gap didn't reach threshold
        if up_ask and 0.70 <= up_ask <= 0.92 and 30 <= gap < up_B:
            ask_good_but_gap_short.append((cid, rem, 'UP', gap, up_B, up_ask, winner))
        if dn_ask and 0.70 <= dn_ask <= 0.92 and -30 >= gap > dn_B:
            ask_good_but_gap_short.append((cid, rem, 'DOWN', gap, dn_B, dn_ask, winner))

print(f"\nTotal Snapshots Evaluated in 15-120s Window: {snaps_in_late_round}")
print(f"QUALIFYING SIGNALS THAT MET ALL BOT A RULES: {len(qualifying_bot_A)}")
print(f"QUALIFYING SIGNALS THAT MET ALL BOT B RULES: {len(qualifying_bot_B)}")

if qualifying_bot_A or qualifying_bot_B:
    print("\n🚨 DETECTED QUALIFYING SIGNALS:")
    for q in qualifying_bot_A:
        print(f"  Bot A: Cycle {q[0]} T-{q[1]}s | {q[2]} | Gap ${q[3]:.1f} | Ask {q[4]} | Settled: {q[6]}")
    for q in qualifying_bot_B:
        print(f"  Bot B: Cycle {q[0]} T-{q[1]}s | {q[2]} | Gap ${q[3]:.1f} | Ask {q[4]} | Settled: {q[6]}")

print(f"\nBreakdown of Non-Qualifying Near-Misses:")
print(f"  1. Gaps met boundary, but Ask was > 0.95 (e.g. 0.96-0.999): {len(gap_met_but_ask_bad)} snapshots")
print(f"  2. Gaps met boundary, but Ask was None (empty book):        {len(gap_met_but_ask_none)} snapshots")
print(f"  3. Asks were cheap (0.70-0.92), but Gap was short:          {len(ask_good_but_gap_short)} snapshots")

conn.close()
