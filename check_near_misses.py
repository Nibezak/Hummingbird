import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome, status, datetime(start_time, 'unixepoch')
    FROM cycles 
    WHERE cycle_id >= 1795271700 
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()
print(f"Total cycles since trade #130: {len(cycles)}")

print(f"{'Cycle':<11} | {'Time':<5} | {'Strike':<9} | {'Win':<4} | {'Max UP Gap (Rem, Ask)':<25} | {'Max DOWN Gap (Rem, Ask)':<26} | {'Forensic Notes':<35}")
print("-" * 125)

for cid, strike, final_p, winner, status, st_time in cycles:
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds <= 120 AND remaining_seconds >= 15
        ORDER BY remaining_seconds DESC
    ''', (cid,))
    snaps = c.fetchall()
    if not snaps or strike is None:
        continue
    
    max_up_gap = -999999
    min_down_gap = 999999
    best_up = None
    best_down = None
    
    for rem, spot, gap, up_ask, down_ask, up_dep, down_dep in snaps:
        if gap is None:
            continue
        if gap > max_up_gap:
            max_up_gap = gap
            best_up = (rem, gap, up_ask, up_dep)
        if gap < min_down_gap:
            min_down_gap = gap
            best_down = (rem, gap, down_ask, down_dep)
            
    up_s = f"+${best_up[1]:.1f} ({best_up[0]}s, {best_up[2]})" if best_up else "N/A"
    down_s = f"-${abs(best_down[1]):.1f} ({best_down[0]}s, {best_down[2]})" if best_down else "N/A"
    t_str = st_time[11:16] if st_time else "N/A"
    w_str = winner if winner else "?"
    
    best_up_gap = best_up[1] if best_up else 0
    best_down_gap = best_down[1] if best_down else 0
    
    note = ""
    if best_down_gap < -140:
        note = f"CLOSE DOWN: -${abs(best_down_gap):.1f} (need -158.7 A / -144.9 B)"
    elif best_down_gap < -100:
        note = f"Solid DOWN: -${abs(best_down_gap):.1f} (asks: {best_down[2]})"
    elif best_up_gap > 200:
        note = f"Huge UP: +${best_up_gap:.1f} (blocked by +$478 ratchet!)"
    elif best_up_gap > 100:
        note = f"Solid UP: +${best_up_gap:.1f} (blocked by +$478 ratchet!)"
    elif abs(best_up_gap) < 30 and abs(best_down_gap) < 30:
        note = f"Chop / Flat market (gap < $30)"
    else:
        note = f"Normal variance (UP: +${best_up_gap:.0f}, DN: -${abs(best_down_gap):.0f})"
        
    print(f"{cid:<11} | {t_str:<5} | {strike:<9.1f} | {w_str:<4} | {up_s:<25} | {down_s:<26} | {note:<35}")

conn.close()
