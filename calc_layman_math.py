import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# Check latest trades
c.execute('SELECT count(*), max(trade_id) FROM dry_run_trades')
cnt, max_tid = c.fetchone()
print(f"Total trades in DB: {cnt}, Max Trade ID: {max_tid}")

# Check average win payout
c.execute('SELECT avg(entry_price), avg(roi_pct), avg(pnl) FROM dry_run_trades WHERE is_winner = 1')
avg_price, avg_roi, avg_pnl = c.fetchone()
print(f"Avg Winning Entry Price: {avg_price:.3f} | Avg ROI on Wins: {avg_roi:.1f}% | Avg Win PnL: {avg_pnl:.2f}")

# Check average loss
c.execute('SELECT avg(invested_usd), count(*) FROM dry_run_trades WHERE is_winner = 0')
avg_loss_stake, loss_cnt = c.fetchone()
print(f"Total Losses across all sessions: {loss_cnt} | Avg Loss Amount: {avg_loss_stake:.2f}")

# Recovery ratio
recovery_wins_needed = avg_loss_stake / avg_pnl if avg_pnl else 0
print(f"Mathematically: It takes {recovery_wins_needed:.1f} consecutive wins to recover from ONE loss!")

# Check current balances
c.execute('SELECT id, balance FROM wallet')
for w in c.fetchall():
    print(f"Wallet {w[0]}: {w[1]:.2f}")

# Bot A specific
c.execute('SELECT avg(pnl) FROM dry_run_trades WHERE session_id = 3 AND is_winner = 1')
pnl_a = c.fetchone()[0]
c.execute('SELECT avg(invested_usd) FROM dry_run_trades WHERE session_id = 3 AND is_winner = 0')
loss_a = c.fetchone()[0]
print(f"Bot A: Avg Win PnL: {pnl_a:.2f} | Avg Loss: {loss_a:.2f} | Recovery Wins Needed: {loss_a/pnl_a:.1f}")

# Bot B specific
c.execute('SELECT avg(pnl) FROM dry_run_trades WHERE session_id = 4 AND is_winner = 1')
pnl_b = c.fetchone()[0]
c.execute('SELECT avg(invested_usd) FROM dry_run_trades WHERE session_id = 4 AND is_winner = 0')
loss_b = c.fetchone()[0]
print(f"Bot B: Avg Win PnL: {pnl_b:.2f} | Avg Loss: {loss_b:.2f} | Recovery Wins Needed: {loss_b/pnl_b:.1f}")

# Total data points
c.execute('SELECT count(*) FROM cycles')
tot_cycles = c.fetchone()[0]
c.execute('SELECT count(*) FROM snapshots')
tot_snaps = c.fetchone()[0]
print(f"Cycles: {tot_cycles} | Snapshots: {tot_snaps}")

conn.close()
