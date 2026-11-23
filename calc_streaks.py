import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Check latest trades across both bots
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, is_winner, status
    FROM dry_run_trades
    ORDER BY trade_id DESC
    LIMIT 15
''')
latest_trades = cursor.fetchall()
print("Latest 15 trades in DB:")
for t in latest_trades:
    print(t)

# Bot A (session 3) streak
cursor.execute('''
    SELECT trade_id, cycle_id, call_time, direction, is_winner, status, pnl
    FROM dry_run_trades
    WHERE session_id = 3
    ORDER BY trade_id ASC
''')
a_trades = cursor.fetchall()

a_streak = 0
last_a_loss = None
for t in reversed(a_trades):
    tid, cid, ct, direction, is_win, status, pnl = t
    if is_win == 1 or (pnl is not None and pnl > 0):
        a_streak += 1
    else:
        last_a_loss = t
        break

# Bot B (session 4) streak
cursor.execute('''
    SELECT trade_id, cycle_id, call_time, direction, is_winner, status, pnl
    FROM dry_run_trades
    WHERE session_id = 4
    ORDER BY trade_id ASC
''')
b_trades = cursor.fetchall()

b_streak = 0
last_b_loss = None
for t in reversed(b_trades):
    tid, cid, ct, direction, is_win, status, pnl = t
    if is_win == 1 or (pnl is not None and pnl > 0):
        b_streak += 1
    else:
        last_b_loss = t
        break

# Wallets
cursor.execute("SELECT id, session_id, balance, initial_balance FROM wallet")
wallets = cursor.fetchall()

print("\n--- STREAK RESULTS ---")
print(f"Bot A Total Trades: {len(a_trades)}")
print(f"Bot A Consecutive Wins: {a_streak}")
print(f"Bot A Last Loss: {last_a_loss}")

print(f"\nBot B Total Trades: {len(b_trades)}")
print(f"Bot B Consecutive Wins: {b_streak}")
print(f"Bot B Last Loss: {last_b_loss}")

print("\nWallets:")
for w in wallets:
    print(w)

conn.close()
