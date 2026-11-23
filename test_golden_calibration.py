import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome 
    FROM cycles 
    WHERE cycle_id > 1795271700 AND status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()
print(f"Total resolved cycles since Trade #130: {len(cycles)}")

# Let's test the 'Golden Window' thresholds (similar to trades 90-127 that gave the 40-win streak):
def get_golden_th(rem):
    if rem >= 91: return 105.0, -90.0
    elif rem >= 61: return 85.0, -75.0
    elif rem >= 46: return 65.0, -55.0
    elif rem >= 31: return 50.0, -40.0
    else: return 35.0, -25.0

trades = []
for cid, strike, final, winner in cycles:
    c.execute('''
        SELECT remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ? AND remaining_seconds BETWEEN 15 AND 120
        ORDER BY remaining_seconds DESC
    ''', (cid,))
    snaps = c.fetchall()
    
    trade = None
    for rem, spot, gap, up_ask, dn_ask, up_dep, dn_dep in snaps:
        if gap is None: continue
        up_th, dn_th = get_golden_th(rem)
        
        # UP
        if gap >= up_th and up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
            is_win = 1 if winner.lower() == 'up' else 0
            trade = (cid, rem, 'Up', gap, up_ask, is_win, winner)
            break
        # DOWN
        elif gap <= dn_th and dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
            is_win = 1 if winner.lower() == 'down' else 0
            trade = (cid, rem, 'Down', gap, dn_ask, is_win, winner)
            break
            
    if trade:
        trades.append(trade)

wins = sum(1 for t in trades if t[5] == 1)
losses = len(trades) - wins
wr = (wins / len(trades) * 100) if trades else 0

print(f"\nSimulation with Golden Thresholds across the 142 cycles:")
print(f"Total Trades: {len(trades)} | Wins: {wins} | Losses: {losses} | Win Rate: {wr:.1f}%\n")

for t in trades[:15]:
    status_str = "✅ WON" if t[5] == 1 else "❌ LOST"
    print(f"Cycle {t[0]} @ T-{t[1]:02d}s | {t[2]:<4} @ {t[4]:.2f}¢ | Gap: ${t[3]:+.1f} | Result: {status_str} (Winner: {t[6]})")

conn.close()
