import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE session_id IN (3, 4) AND status LIKE 'RESOLVED%'
    ORDER BY trade_id ASC
''')
trades = cursor.fetchall()

def parse_eat_time(ct_str):
    clean = str(ct_str).replace('Z', '+00:00')
    dt_utc = datetime.datetime.fromisoformat(clean)
    return dt_utc + datetime.timedelta(hours=3)

# Filter trades OUTSIDE of 17:25 - 18:05 EAT
outside_trades = []
for t in trades:
    dt_eat = parse_eat_time(t[3])
    m_of_day = dt_eat.hour * 60 + dt_eat.minute
    if not (17*60 + 25 <= m_of_day < 18*60 + 5):
        outside_trades.append(t)

def get_stats(t_list, sess):
    sub = [t for t in t_list if t[1] == sess]
    tot = len(sub)
    wins = sum(1 for t in sub if t[8] == 1 or (t[7] and t[7] > 0))
    losses = sum(1 for t in sub if t[8] == 0 and t[7] and t[7] < 0)
    net_pnl = sum(t[7] for t in sub if t[7] is not None)
    wr = (wins / tot * 100) if tot > 0 else 0.0
    return tot, wins, losses, wr, net_pnl

print("=== PERFORMANCE EXCLUDING THE OPENING BELL (05:25 - 06:05 EAT) ===")
a_tot, a_w, a_l, a_wr, a_pnl = get_stats(outside_trades, 3)
b_tot, b_w, b_l, b_wr, b_pnl = get_stats(outside_trades, 4)

print(f"Bot A (Security)  : {a_tot:3d} Trades | {a_w:3d} W - {a_l:1d} L ({a_wr:5.1f}%) | Net PnL: ${a_pnl:+6.2f}")
print(f"Bot B (Frequency) : {b_tot:3d} Trades | {b_w:3d} W - {b_l:1d} L ({b_wr:5.1f}%) | Net PnL: ${b_pnl:+6.2f}")

conn.close()
