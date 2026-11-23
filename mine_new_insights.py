import sqlite3
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

print("="*80)
print("1. EMPIRICAL WIN RATE VS POLYMARKET ASKS (MISPRICING EDGE)")
print("="*80)

# Query snapshots where asks exist in specific price buckets in the late round (15 to 120s)
# Compare to the resolved winning outcome of that cycle!
c.execute('''
    SELECT 
        s.cycle_id, s.remaining_seconds, s.gap_dollars, 
        s.up_best_ask, s.down_best_ask, 
        c.winning_outcome
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.status = 'RESOLVED' AND c.winning_outcome IS NOT NULL
      AND s.remaining_seconds BETWEEN 15 AND 120
''')
rows = c.fetchall()

buckets = [
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, 0.85),
    (0.85, 0.90),
    (0.90, 0.95),
    (0.95, 0.99)
]

print(f"{'Ask Bucket':<12} | {'Side':<5} | {'Observations':<12} | {'Actual Wins':<12} | {'Empirical Win Rate':<20} | {'Implied Prob':<14} | {'Edge (Alpha)':<12}")
print("-" * 95)

for b_low, b_high in buckets:
    # UP
    up_total = 0
    up_wins = 0
    # DOWN
    dn_total = 0
    dn_wins = 0
    
    for cid, rem, gap, up_ask, dn_ask, winner in rows:
        if up_ask and b_low <= up_ask < b_high:
            up_total += 1
            if winner.lower() == 'up':
                up_wins += 1
        if dn_ask and b_low <= dn_ask < b_high:
            dn_total += 1
            if winner.lower() == 'down':
                dn_wins += 1
                
    implied = (b_low + b_high) / 2.0 * 100
    if up_total > 50:
        up_wr = (up_wins / up_total) * 100
        edge_up = up_wr - implied
        print(f"{f'{b_low:.2f}-{b_high:.2f}':<12} | UP    | {up_total:<12} | {up_wins:<12} | {up_wr:<19.1f}% | {implied:<13.1f}% | {edge_up:<+11.1f}%")
    if dn_total > 50:
        dn_wr = (dn_wins / dn_total) * 100
        edge_dn = dn_wr - implied
        print(f"{f'{b_low:.2f}-{b_high:.2f}':<12} | DOWN  | {dn_total:<12} | {dn_wins:<12} | {dn_wr:<19.1f}% | {implied:<13.1f}% | {edge_dn:<+11.1f}%")

print("\n" + "="*80)
print("2. LIQUIDITY & SPREAD DYNAMICS ACROSS TIME HORIZONS")
print("="*80)

time_brackets = [
    ("T-300 to 240s", 240, 300),
    ("T-240 to 180s", 180, 240),
    ("T-180 to 120s", 120, 180),
    ("T-120 to 60s",  60, 120),
    ("T-60 to 30s",   30, 60),
    ("T-30 to 15s",   15, 30),
]

print(f"{'Time Window':<16} | {'Avg UP Spread':<14} | {'Avg DN Spread':<14} | {'Avg UP Depth':<14} | {'Avg DN Depth':<14}")
print("-" * 80)

for w_name, t_min, t_max in time_brackets:
    c.execute('''
        SELECT 
            avg(up_best_ask - up_best_bid),
            avg(down_best_ask - down_best_bid),
            avg(up_ask_depth),
            avg(down_ask_depth)
        FROM snapshots
        WHERE remaining_seconds BETWEEN ? AND ?
          AND up_best_ask IS NOT NULL AND up_best_bid IS NOT NULL
          AND down_best_ask IS NOT NULL AND down_best_bid IS NOT NULL
    ''', (t_min, t_max))
    r = c.fetchone()
    up_sp, dn_sp, up_dp, dn_dp = r
    print(f"{w_name:<16} | {up_sp:<13.3f}¢ | {dn_sp:<13.3f}¢ | ${up_dp:<13.0f} | ${dn_dp:<13.0f}")

print("\n" + "="*80)
print("3. ANATOMY OF ADVERSE REVERSALS (WHEN DO TRAPS STRIKE?)")
print("="*80)

# Check all cycles where a gap >= $50 existed at some point in T-120 to 15s, but that side LOST!
c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome
    FROM cycles
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
''')
resolved_cycles = c.fetchall()

trapped_cycles = []
for cid, strike, final, winner in resolved_cycles:
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds BETWEEN 15 AND 120
        ORDER BY remaining_seconds DESC
    ''', (cid,))
    snaps = c.fetchall()
    
    max_up_gap = max((s[2] for s in snaps if s[2] is not None), default=0)
    min_dn_gap = min((s[2] for s in snaps if s[2] is not None), default=0)
    
    # Was UP ahead by >= $50, but DOWN won?
    if max_up_gap >= 50 and winner.lower() == 'down':
        # Find when the reversal crossed back over strike
        cross_time = None
        for rem, spot, gap in snaps:
            if gap <= 0:
                cross_time = rem
                break
        trapped_cycles.append(('UP_TRAP', cid, max_up_gap, cross_time, strike, final))
        
    # Was DOWN ahead by >= $50, but UP won?
    if min_dn_gap <= -50 and winner.lower() == 'up':
        cross_time = None
        for rem, spot, gap in snaps:
            if gap >= 0:
                cross_time = rem
                break
        trapped_cycles.append(('DOWN_TRAP', cid, abs(min_dn_gap), cross_time, strike, final))

print(f"Total Cycles with Fake-out Traps (Lead >= $50 that collapsed): {len(trapped_cycles)} out of {len(resolved_cycles)} ({len(trapped_cycles)/len(resolved_cycles)*100:.1f}%)")
print(f"\nTrap Types: UP Collapsed = {sum(1 for t in trapped_cycles if t[0]=='UP_TRAP')} | DOWN Collapsed = {sum(1 for t in trapped_cycles if t[0]=='DOWN_TRAP')}")

# Distribution of collapse times:
collapse_times = [t[3] for t in trapped_cycles if t[3] is not None]
if collapse_times:
    c_arr = np.array(collapse_times)
    print(f"When does the lead cross back over strike? Median: T-{np.median(c_arr):.0f}s | 75th: T-{np.percentile(c_arr, 75):.0f}s | 25th: T-{np.percentile(c_arr, 25):.0f}s")

# Distribution of peak lead sizes that failed:
lead_sizes = [t[2] for t in trapped_cycles]
if lead_sizes:
    l_arr = np.array(lead_sizes)
    print(f"Lead size that failed: Median: ${np.median(l_arr):.1f} | 75th: ${np.percentile(l_arr, 75):.1f} | 90th: ${np.percentile(l_arr, 90):.1f} | Max: ${np.max(l_arr):.1f}")

conn.close()
