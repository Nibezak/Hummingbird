import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check cycles
cursor.execute("SELECT COUNT(*), MIN(cycle_id), MAX(cycle_id), MIN(start_time), MAX(start_time) FROM cycles")
cycles_info = cursor.fetchone()
print("Cycles info:", cycles_info)

# Check wallets
cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
wallets = cursor.fetchall()
print("\nWallets:")
for w in wallets:
    print(w)

# Check trades count per session
cursor.execute("SELECT session_id, COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END), SUM(pnl) FROM dry_run_trades GROUP BY session_id")
print("\nTrades by session:")
for row in cursor.fetchall():
    print(row)

# Get all trades since 1795359600 (the last trade we saw yesterday was #148 in cycle 1795359600)
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, gap_at_call, entry_price, invested_usd, pnl, is_winner, status, rule_triggered
    FROM dry_run_trades
    WHERE trade_id > 140
    ORDER BY trade_id ASC
''')
recent_trades = cursor.fetchall()
print(f"\nRecent trades (since #140): {len(recent_trades)}")
for t in recent_trades:
    print(t)

# Check learning_log count and new entries
cursor.execute("SELECT COUNT(*) FROM learning_log")
print(f"\nTotal learning_log entries: {cursor.fetchone()[0]}")

conn.close()
