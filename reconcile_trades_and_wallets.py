import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check current values for trades 89, 90, 140, 141
trade_ids = [89, 90, 140, 141]
cursor.execute(f"SELECT trade_id, session_id, cycle_id, direction, entry_price, shares, invested_usd, pnl, is_winner, status FROM dry_run_trades WHERE trade_id IN ({','.join(map(str, trade_ids))})")
rows = cursor.fetchall()

print("Current trade rows before reconciliation:")
for r in rows:
    print(r)

# Check wallets before reconciliation
cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
wallets = cursor.fetchall()
print("\nWallets before reconciliation:")
for w in wallets:
    print(w)

now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

# Execute trade reconciliation
# Trade 89: sess 3, Down, shares=3.41, invested=3.00 -> won: payout=3.41, pnl = +0.41 (previously -3.00, diff = +3.41)
# Trade 90: sess 3, Down, shares=3.90, invested=3.00 -> won: payout=3.90, pnl = +0.90 (previously -3.00, diff = +3.90)
# Trade 140: sess 3, Down, shares=5.72, invested=5.43 -> won: payout=5.72, pnl = +0.29 (previously -5.43, diff = +5.72)
# Trade 141: sess 4, Down, shares=6.47, invested=6.15 -> won: payout=6.47, pnl = +0.32 (previously -6.15, diff = +6.47)

reconciliations = [
    (89, 3, 1795203000, 3.41, 3.00, 0.41, 13.67),
    (90, 3, 1795204200, 3.90, 3.00, 0.90, 30.00),
    (140, 3, 1795350300, 5.72, 5.43, 0.29, 5.34),
    (141, 4, 1795350300, 6.47, 6.15, 0.32, 5.20)
]

for tid, sess, cid, shares, inv, pnl, roi in reconciliations:
    cursor.execute("""
        UPDATE dry_run_trades
        SET winning_outcome = 'Down',
            is_winner = 1,
            pnl = ?,
            roi_pct = ?,
            status = 'RESOLVED_WIN',
            resolved_at = ?
        WHERE trade_id = ?
    """, (pnl, roi, now_iso, tid))
    print(f"Updated trade #{tid} -> RESOLVED_WIN (PnL: +${pnl:.2f})")

# Update cycles winning_outcome to 'Down'
for cid in [1795203000, 1795204200, 1795350300]:
    cursor.execute("""
        UPDATE cycles
        SET winning_outcome = 'Down',
            updated_at = ?
        WHERE cycle_id = ?
    """, (now_iso, cid))
    print(f"Updated cycle {cid} -> winning_outcome = 'Down'")

# Now calculate exact wallet balances from all settled trades
# Bot A (session 3): initial_balance = 10.00
cursor.execute("SELECT SUM(pnl) FROM dry_run_trades WHERE session_id = 3 AND status LIKE 'RESOLVED%'")
a_pnl_sum = cursor.fetchone()[0]
new_a_balance = round(10.00 + a_pnl_sum, 2)

# Bot B (session 4): initial_balance = 35.26
cursor.execute("SELECT SUM(pnl) FROM dry_run_trades WHERE session_id = 4 AND status LIKE 'RESOLVED%'")
b_pnl_sum = cursor.fetchone()[0]
new_b_balance = round(35.26 + b_pnl_sum, 2)

cursor.execute("""
    UPDATE wallet
    SET balance = ?, updated_at = ?
    WHERE session_id = 3
""", (new_a_balance, now_iso))

cursor.execute("""
    UPDATE wallet
    SET balance = ?, updated_at = ?
    WHERE session_id = 4
""", (new_b_balance, now_iso))

conn.commit()

print(f"\nReconciliation committed!")
print(f"Bot A (Session 3): Total PnL = ${a_pnl_sum:+.2f} | New Wallet Balance = ${new_a_balance:.2f}")
print(f"Bot B (Session 4): Total PnL = ${b_pnl_sum:+.2f} | New Wallet Balance = ${new_b_balance:.2f}")

# Verify in DB
cursor.execute("SELECT id, session_id, balance, initial_balance, updated_at FROM wallet")
print("\nUpdated wallets in DB:")
for w in cursor.fetchall():
    print(w)

conn.close()
