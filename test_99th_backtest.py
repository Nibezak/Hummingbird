import sqlite3
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

c.execute('''
    SELECT cycle_id, strike_price, final_price, winning_outcome 
    FROM cycles 
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
    ORDER BY cycle_id ASC
''')
cycles = c.fetchall()

# 99th percentile:
# 15-30s: Squeeze $65.9, Dump $89.0
# 31-45s: Squeeze $90.6, Dump $157.1
# 46-60s: Squeeze $116.5, Dump $179.2
# 61-90s: Squeeze $109.5, Dump $183.9
# 91-120s: Squeeze $112.4, Dump $148.4

def get_th_99(rem, bot_type='A'):
    if bot_type == 'A':
        if rem >= 91: return round(148.4 * 1.15, 1), -round(112.4 * 1.15, 1)
        elif rem >= 61: return round(183.9 * 1.15, 1), -round(109.5 * 1.15, 1)
        elif rem >= 46: return round(179.2 * 1.15, 1), -round(116.5 * 1.15, 1)
        elif rem >= 31: return round(157.1 * 1.15, 1), -round(90.6 * 1.15, 1)
        else: return round(89.0 * 1.15, 1), -round(65.9 * 1.15, 1)
    else: # Bot B (+5%)
        if rem >= 91: return round(148.4 * 1.05, 1), -round(112.4 * 1.05, 1)
        elif rem >= 61: return round(183.9 * 1.05, 1), -round(109.5 * 1.05, 1)
        elif rem >= 46: return round(179.2 * 1.05, 1), -round(116.5 * 1.05, 1)
        elif rem >= 31: return round(157.1 * 1.05, 1), -round(90.6 * 1.05, 1)
        else: return round(89.0 * 1.05, 1), -round(65.9 * 1.05, 1)

for bot_type in ['A', 'B']:
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
            up_th, dn_th = get_th_99(rem, bot_type)
            
            # UP
            if gap >= up_th and up_ask and 0.70 <= up_ask <= 0.95 and (up_dep or 0) >= 5.0:
                is_win = 1 if winner.lower() == 'up' else 0
                trade = ('Up', rem, gap, up_ask, is_win)
                break
            # DOWN
            elif gap <= dn_th and dn_ask and 0.70 <= dn_ask <= 0.95 and (dn_dep or 0) >= 5.0:
                is_win = 1 if winner.lower() == 'down' else 0
                trade = ('Down', rem, gap, dn_ask, is_win)
                break
                
        if trade:
            trades.append(trade)
            
    wins = sum(1 for t in trades if t[4] == 1)
    losses = len(trades) - wins
    wr = (wins / len(trades) * 100) if trades else 0
    print(f"Bot {bot_type} (99th percentile): {len(trades)} Trades | {wins} Wins | {losses} Losses | Win Rate: {wr:.1f}%")

conn.close()
