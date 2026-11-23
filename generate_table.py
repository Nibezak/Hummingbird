import sqlite3

conn = sqlite3.connect('c:/projects/btc-5m-recorder/btc_5m_data.db')
c = conn.cursor()
c.execute('''
    SELECT trade_id, session_id, call_time, remaining_seconds, direction, entry_price, gap_at_call, is_winner, pnl 
    FROM dry_run_trades 
    ORDER BY trade_id ASC
''')
trades = c.fetchall()

print('| # | Timestamp (UTC) | Time Left | Direction | Share Price | Gap at Call | Outcome | Net PnL |')
print('| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |')

for t in trades:
    tid, session, call_time, rem, direction, price, gap, is_winner, pnl = t
    dt_str = call_time.replace('T', ' ').split('.')[0][:19]
    mins = rem // 60
    secs = rem % 60
    rem_str = f'T-{mins:02d}:{secs:02d} ({rem}s)'
    outcome_str = '✅ WON' if is_winner == 1 else '❌ LOST'
    pnl_str = f'+${pnl:.2f}' if pnl > 0 else f'-${abs(pnl):.2f}'
    dir_str = direction.upper()
    price_str = f'{price:.2f}¢' if price < 1.0 else f'${price:.2f}'
    gap_str = f'+${gap:.1f}' if gap > 0 else f'-${abs(gap):.1f}'
    print(f'| **#{tid}** | `{dt_str}` | {rem_str} | **{dir_str}** | `{price_str}` | `{gap_str}` | {outcome_str} | `{pnl_str}` |')
