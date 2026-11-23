import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome, status, start_time
    FROM cycles 
    WHERE cycle_id >= 1795288800 
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()
print(f"Total cycles since recalibration: {len(cycles)}")

print(f"{'Cycle':<11} | {'Strike':<9} | {'Final':<9} | {'Win':<5} | {'Max UP Gap':<12} | {'Max DN Gap':<12} | {'Min Ask UP':<10} | {'Min Ask DN':<10}")
print("-" * 95)

for cid, strike, final, winner, status, st_time in cycles:
    c.execute('''
        SELECT max(gap_dollars), min(gap_dollars), min(up_best_ask), min(down_best_ask)
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds BETWEEN 15 AND 120
    ''', (cid,))
    row = c.fetchone()
    max_up, min_dn, min_up_ask, min_dn_ask = row
    max_up_val = f"+{max_up:.1f}" if max_up is not None else "N/A"
    min_dn_val = f"-{abs(min_dn):.1f}" if min_dn is not None else "N/A"
    strike_val = f"{strike:.1f}" if strike is not None else "N/A"
    final_val = f"{final:.1f}" if final is not None else "N/A"
    win_val = winner if winner else "ACTIVE"
    up_ask_s = f"{min_up_ask}" if min_up_ask is not None else "None"
    dn_ask_s = f"{min_dn_ask}" if min_dn_ask is not None else "None"
    print(f"{cid:<11} | {strike_val:<9} | {final_val:<9} | {win_val:<5} | {max_up_val:<12} | {min_dn_val:<12} | {up_ask_s:<10} | {dn_ask_s:<10}")

conn.close()
