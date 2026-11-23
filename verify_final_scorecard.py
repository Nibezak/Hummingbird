import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Bot A
cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END), SUM(pnl) FROM dry_run_trades WHERE session_id = 3")
a_tot, a_win, a_loss, a_pnl = cursor.fetchone()

# Bot B
cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_winner=0 AND status='RESOLVED_LOSS' THEN 1 ELSE 0 END), SUM(pnl) FROM dry_run_trades WHERE session_id = 4")
b_tot, b_win, b_loss, b_pnl = cursor.fetchone()

cursor.execute("SELECT balance, initial_balance FROM wallet WHERE session_id = 3")
a_bal, a_init = cursor.fetchone()

cursor.execute("SELECT balance, initial_balance FROM wallet WHERE session_id = 4")
b_bal, b_init = cursor.fetchone()

print(f"Bot A: {a_tot} trades | {a_win} W - {a_loss} L ({a_win/a_tot*100:.1f}%) | Bal: ${a_bal:.2f} | PnL: ${a_pnl:+.2f}")
print(f"Bot B: {b_tot} trades | {b_win} W - {b_loss} L ({b_win/b_tot*100:.1f}%) | Bal: ${b_bal:.2f} | PnL: ${b_pnl:+.2f}")

conn.close()
