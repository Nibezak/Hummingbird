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

# Latest trades
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    ORDER BY trade_id DESC
    LIMIT 10
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

print("=== AUDITED & RECONCILED METRICS ===")
print(f"Total Cycles: {cycle_count}")
print(f"Total Snapshots: {snapshot_count}")
print(f"Total Learning Events: {learning_count}")
print("\n--- BOT A (Session 3) ---")
print(f"Trades: {a_trades} | Wins: {a_wins} | Losses: {a_losses} | Win Rate: {a_wins/a_trades*100:.1f}%")
print(f"Bankroll: ${a_bal:.2f} (from ${a_init:.2f}) | Total PnL: ${a_pnl:+.2f} ({((a_bal-a_init)/a_init)*100:.1f}%)")
print(f"Current Streak: {a_streak} Consecutive Wins")

print("\n--- BOT B (Session 4) ---")
print(f"Trades: {b_trades} | Wins: {b_wins} | Losses: {b_losses} | Win Rate: {b_wins/b_trades*100:.1f}%")
print(f"Bankroll: ${b_bal:.2f} (from ${b_init:.2f}) | Total PnL: ${b_pnl:+.2f} ({((b_bal-b_init)/b_init)*100:.1f}%)")
print(f"Current Streak: {b_streak} Consecutive Wins")

print("\nLatest Trades:")
for t in recent_trades:
    print(t)

conn.close()
