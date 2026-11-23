import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Overall DB Stats
cursor.execute("SELECT COUNT(*), MIN(cycle_id), MAX(cycle_id), MIN(start_time), MAX(start_time) FROM cycles")
cycle_count, min_cid, max_cid, min_start, max_start = cursor.fetchone()

cursor.execute("SELECT COUNT(*) FROM snapshots")
snapshot_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM learning_log")
learning_count = cursor.fetchone()[0]

# Total duration
dt_start = datetime.datetime.fromisoformat(min_start.replace('Z', '+00:00'))
dt_end = datetime.datetime.fromtimestamp(max_cid + 300, tz=datetime.timezone.utc)
total_hours = (dt_end - dt_start).total_seconds() / 3600.0

# Bot A (Session 3) Stats
cursor.execute('''
    SELECT COUNT(*),
           SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END),
           SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END),
           SUM(pnl)
    FROM dry_run_trades
    WHERE session_id = 3
''')
a_trades, a_wins, a_losses, a_pnl = cursor.fetchone()

# Bot B (Session 4) Stats
cursor.execute('''
    SELECT COUNT(*),
           SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END),
           SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END),
           SUM(pnl)
    FROM dry_run_trades
    WHERE session_id = 4
''')
b_trades, b_wins, b_losses, b_pnl = cursor.fetchone()

# Wallets
cursor.execute("SELECT balance, initial_balance, updated_at FROM wallet WHERE session_id = 3")
a_bal, a_init, a_upd = cursor.fetchone()

cursor.execute("SELECT balance, initial_balance, updated_at FROM wallet WHERE session_id = 4")
b_bal, b_init, b_upd = cursor.fetchone()

# Latest trades (since #180)
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE trade_id >= 180
    ORDER BY trade_id ASC
''')
recent_trades = cursor.fetchall()

# Streaks
cursor.execute("SELECT is_winner FROM dry_run_trades WHERE session_id = 3 ORDER BY trade_id ASC")
a_results = [r[0] for r in cursor.fetchall()]
a_streak = 0
for r in reversed(a_results):
    if r == 1: a_streak += 1
    else: break

cursor.execute("SELECT is_winner FROM dry_run_trades WHERE session_id = 4 ORDER BY trade_id ASC")
b_results = [r[0] for r in cursor.fetchall()]
b_streak = 0
for r in reversed(b_results):
    if r == 1: b_streak += 1
    else: break

print(f"Total Cycles: {cycle_count}")
print(f"Total Snapshots: {snapshot_count}")
print(f"Total Hours: {total_hours:.1f}h")
print(f"Learning Log Events: {learning_count}")

print(f"\nBot A (Session 3): {a_trades} trades | {a_wins} W - {a_losses} L ({a_wins/a_trades*100:.1f}%) | Bal: ${a_bal:.2f} (Init: ${a_init:.2f}) | PnL: ${a_pnl:+.2f} | Streak: {a_streak}")
print(f"Bot B (Session 4): {b_trades} trades | {b_wins} W - {b_losses} L ({b_wins/b_trades*100:.1f}%) | Bal: ${b_bal:.2f} (Init: ${b_init:.2f}) | PnL: ${b_pnl:+.2f} | Streak: {b_streak}")

print(f"\nRecent Trades (since #180): {len(recent_trades)}")
for t in recent_trades:
    print(t)

conn.close()
