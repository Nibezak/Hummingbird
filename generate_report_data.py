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

# Calculate total hours of data
dt_start = datetime.datetime.fromisoformat(min_start.replace('Z', '+00:00'))
dt_end = datetime.datetime.fromisoformat(max_start.replace('Z', '+00:00'))
total_duration_hours = (dt_end - dt_start).total_seconds() / 3600.0

# Bot A (Session 3) Stats
cursor.execute('''
    SELECT COUNT(*),
           SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END),
           SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END),
           SUM(pnl),
           MIN(trade_id), MAX(trade_id)
    FROM dry_run_trades
    WHERE session_id = 3
''')
a_trades, a_wins, a_losses, a_pnl, a_min_tid, a_max_tid = cursor.fetchone()

# Bot B (Session 4) Stats
cursor.execute('''
    SELECT COUNT(*),
           SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END),
           SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END),
           SUM(pnl),
           MIN(trade_id), MAX(trade_id)
    FROM dry_run_trades
    WHERE session_id = 4
''')
b_trades, b_wins, b_losses, b_pnl, b_min_tid, b_max_tid = cursor.fetchone()

# Wallets
cursor.execute("SELECT balance, initial_balance FROM wallet WHERE session_id = 3")
a_bal, a_init = cursor.fetchone()

cursor.execute("SELECT balance, initial_balance FROM wallet WHERE session_id = 4")
b_bal, b_init = cursor.fetchone()

# Overnight trades (since yesterday 22:00 EAT / 19:00 UTC)
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    WHERE trade_id >= 149
    ORDER BY trade_id ASC
''')
overnight_trades = cursor.fetchall()

print(f"Total Cycles: {cycle_count}")
print(f"Total Snapshots: {snapshot_count}")
print(f"Total Duration: {total_duration_hours:.1f} hours ({total_duration_hours/24:.2f} days)")
print(f"Learning Log Entries: {learning_count}")
print("\n--- BOT A ---")
print(f"Trades: {a_trades} | Wins: {a_wins} | Losses: {a_losses} | Win Rate: {a_wins/a_trades*100:.1f}%")
print(f"Bankroll: ${a_bal:.2f} (from ${a_init:.2f}) | PnL: ${a_pnl:+.2f} ({((a_bal-a_init)/a_init)*100:.1f}%)")

print("\n--- BOT B ---")
print(f"Trades: {b_trades} | Wins: {b_wins} | Losses: {b_losses} | Win Rate: {b_wins/b_trades*100:.1f}%")
print(f"Bankroll: ${b_bal:.2f} (from ${b_init:.2f}) | PnL: ${b_pnl:+.2f} ({((b_bal-b_init)/b_init)*100:.1f}%)")

print("\n--- OVERNIGHT TRADES BREAKDOWN ---")
a_on_trades = [t for t in overnight_trades if t[1] == 3]
b_on_trades = [t for t in overnight_trades if t[1] == 4]
print(f"Bot A overnight: {len(a_on_trades)} trades, {sum(1 for t in a_on_trades if t[9]==1)} wins, PnL: ${sum(t[8] for t in a_on_trades):+.2f}")
print(f"Bot B overnight: {len(b_on_trades)} trades, {sum(1 for t in b_on_trades if t[9]==1)} wins, PnL: ${sum(t[8] for t in b_on_trades):+.2f}")

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

print(f"\nBot A Current Streak: {a_streak} consecutive wins")
print(f"Bot B Current Streak: {b_streak} consecutive wins")

conn.close()
