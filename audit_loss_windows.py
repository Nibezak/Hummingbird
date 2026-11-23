import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get all actual losses in dry_run_trades across all sessions
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl, status
    FROM dry_run_trades
    WHERE is_winner = 0 OR pnl < 0
    ORDER BY trade_id ASC
''')
losses = cursor.fetchall()

print(f"Total Actual Losses in DB: {len(losses)}")
print("Trade_ID | Session | Date & UTC Time         | Local Time (EAT) | Market Context")
for l in losses:
    tid, sess, cid, ct, direction, gap, entry_p, inv, pnl, status = l
    dt = datetime.datetime.fromisoformat(ct.replace('Z', '+00:00'))
    dt_eat = dt + datetime.timedelta(hours=3)
    ny_hour = (dt.hour - 5) % 24
    print(f"#{tid:03d}     | Sess {sess}  | {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC | {dt_eat.strftime('%H:%M:%S')} EAT   | NY: {ny_hour:02d}:{dt.minute:02d} | Bet: {direction} @ {entry_p} | PnL: ${pnl}")

# Now let's check current trade #190 / #191
print("\nCurrent Trade #190 & #191:")
cursor.execute("SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl FROM dry_run_trades WHERE trade_id IN (190, 191)")
for r in cursor.fetchall():
    print(r)

conn.close()
