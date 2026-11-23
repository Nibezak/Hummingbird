import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get all trades in session 3 and 4
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

# Define windows to test:
# 1. Opening Bell Window: 17:25 to 18:05 EAT (14:25 to 15:05 UTC)
# 2. Entire Opening Hour: 17:00 to 18:00 EAT (14:00 to 15:00 UTC)
# 3. US Morning Block: 17:00 to 20:30 EAT (14:00 to 17:30 UTC)

def analyze_time_slice(start_min_eat, end_min_eat, label):
    # start_min_eat, end_min_eat in minutes of the day (e.g. 17:25 = 17*60 + 25 = 1045)
    in_window_trades = []
    out_window_trades = []
    
    for t in trades:
        dt_eat = parse_eat_time(t[3])
        m_of_day = dt_eat.hour * 60 + dt_eat.minute
        if start_min_eat <= m_of_day < end_min_eat:
            in_window_trades.append(t)
        else:
            out_window_trades.append(t)
            
    def calc_stats(t_list, bot_sess=None):
        if bot_sess:
            t_list = [t for t in t_list if t[1] == bot_sess]
        tot = len(t_list)
        wins = sum(1 for t in t_list if t[8] == 1 or (t[7] and t[7] > 0))
        losses = sum(1 for t in t_list if t[8] == 0 and t[7] and t[7] < 0)
        pnl = sum(t[7] for t in t_list if t[7] is not None)
        win_money = sum(t[7] for t in t_list if t[7] and t[7] > 0)
        loss_money = sum(abs(t[7]) for t in t_list if t[7] and t[7] < 0)
        wr = (wins / tot * 100) if tot > 0 else 0.0
        return tot, wins, losses, wr, win_money, loss_money, pnl

    print(f"\n=================== {label} ===================")
    for sess, name in [(3, 'Bot A (Security)'), (4, 'Bot B (Frequency)'), (None, 'Both Bots Combined')]:
        tot, w, l, wr, win_m, loss_m, net_pnl = calc_stats(in_window_trades, sess)
        print(f"{name:<20} | Trades: {tot:2d} | W: {w:2d} - L: {l:2d} ({wr:5.1f}%) | Gross Wins: +${win_m:6.2f} | Losses: -${loss_m:6.2f} | Net PnL: ${net_pnl:+6.2f}")

# Window 1: Opening Bell (17:25 - 18:05 EAT)
analyze_time_slice(17*60 + 25, 18*60 + 5, "1. OPENING BELL (05:25 PM - 06:05 PM EAT)")

# Window 2: Full 17:00 - 18:00 EAT
analyze_time_slice(17*60, 18*60, "2. FULL HOUR (05:00 PM - 06:00 PM EAT)")

# Window 3: 17:00 - 19:00 EAT
analyze_time_slice(17*60, 19*60, "3. TWO HOURS (05:00 PM - 07:00 PM EAT)")

conn.close()
