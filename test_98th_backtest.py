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

# Test 98th percentile boundaries
# 91-120s: UP +138.6, DN -120.2 (Bot A) | UP +126.5, DN -109.7 (Bot B)
# 61-90s:  UP +141.8, DN -119.5 (Bot A) | UP +129.5, DN -109.1 (Bot B)
# 46-60s:  UP +107.9, DN -112.5 (Bot A) | UP +98.5,  DN -102.7 (Bot B)
# 31-45s:  UP +87.4,  DN -95.3  (Bot A) | UP +79.8,  DN -87.0  (Bot B)
# 15-30s:  UP +80.8,  DN -61.5  (Bot A) | UP +73.8,  DN -56.2  (Bot B)

def get_th(rem, bot_type='A'):
    if bot_type == 'A':
        if rem >= 91: return 138.6, -120.2
        elif rem >= 61: return 141.8, -119.5
        elif rem >= 46: return 107.9, -112.5
        elif rem >= 31: return 87.4, -95.3
        else: return 80.8, -61.5
    else: # Bot B (+5%)
        if rem >= 91: return 126.5, -109.7
        elif rem >= 61: return 129.5, -109.1
        elif rem >= 46: return 98.5, -102.7
        elif rem >= 31: return 79.8, -87.0
        else: return 73.8, -56.2

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
            up_th, dn_th = get_th(rem, bot_type)
            
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
    print(f"Bot {bot_type} (98th percentile): {len(trades)} Trades | {wins} Wins | {losses} Losses | Win Rate: {wr:.1f}%")

conn.close()
