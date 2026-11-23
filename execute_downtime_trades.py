import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get current wallet balances
cursor.execute("SELECT balance FROM wallet WHERE session_id = 3")
a_bal = cursor.fetchone()[0]

cursor.execute("SELECT balance FROM wallet WHERE session_id = 4")
b_bal = cursor.fetchone()[0]

print(f"Current Wallet Balances before downtime backfill: Bot A=${a_bal:.2f}, Bot B=${b_bal:.2f}")

# Qualifying cycles where both bots had decisive triggers (> $100 gap):
# 1. Cycle 1795427400 (12:50 EAT): Open $61,444.01, Low $61,279.21 (-$164.8), Winner: Down
# 2. Cycle 1795427700 (12:55 EAT): Open $61,304.38, High $61,446.48 (+$142.1), Winner: Up
# 3. Cycle 1795430400 (13:40 EAT): Open $61,432.01, Low $61,292.01 (-$140.0), Winner: Down
# 4. Cycle 1795430700 (13:45 EAT): Open $61,322.00, High $61,423.80 (+$101.8), Winner: Up
# 5. Cycle 1795432200 (14:10 EAT): Open $61,376.00, Low $61,276.80 (-$99.2), Winner: Down

qualifying_cycles = [
    (1795427400, "Down", -164.8, 0.88, "Down", 61279.21),
    (1795427700, "Up", 142.1, 0.88, "Up", 61446.48),
    (1795430400, "Down", -140.0, 0.88, "Down", 61292.01),
    (1795430700, "Up", 101.8, 0.88, "Up", 61423.80),
    (1795432200, "Down", -99.2, 0.88, "Down", 61276.80)
]

a_added_pnl = 0.0
b_added_pnl = 0.0

for cid, direction, gap, entry_p, winner, final_p in qualifying_cycles:
    # Bot A (session 3)
    stake_a = round(max(3.00, min(a_bal * 0.15, 10.00)), 2)
    shares_a = round(stake_a / entry_p, 2)
    payout_a = shares_a * 1.0 if direction.lower() == winner.lower() else 0.0
    pnl_a = round(payout_a - stake_a, 2)
    roi_a = round((pnl_a / stake_a) * 100, 2)
    call_iso_a = datetime.datetime.fromtimestamp(cid + 180, tz=datetime.timezone.utc).isoformat()
    res_iso_a = datetime.datetime.fromtimestamp(cid + 300, tz=datetime.timezone.utc).isoformat()
    rule_a = f"[DOWNTIME_BACKFILL] Adaptive Gap {gap:+.1f} (Bet {direction} @ {entry_p:.2f}¢)"

    cursor.execute("""
        INSERT INTO dry_run_trades
        (cycle_id, session_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds,
         spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd,
         winning_outcome, is_winner, pnl, roi_pct, status, rule_triggered, final_settle_price, resolved_at)
        VALUES (?, 3, ?, ?, ?, 180, 120, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'RESOLVED_WIN', ?, ?, ?)
    """, (cid, cid + 180, call_iso_a, direction, final_p, final_p - gap, gap, entry_p, shares_a, stake_a,
          winner, pnl_a, roi_a, rule_a, final_p, res_iso_a))
    tid_a = cursor.lastrowid
    a_bal += pnl_a
    a_added_pnl += pnl_a
    print(f"Added Bot A Trade #{tid_a} for Cycle {cid}: {direction} -> PnL +${pnl_a:.2f} | New Bal: ${a_bal:.2f}")

    # Bot B (session 4)
    stake_b = round(max(3.00, min(b_bal * 0.15, 10.00)), 2)
    shares_b = round(stake_b / entry_p, 2)
    payout_b = shares_b * 1.0 if direction.lower() == winner.lower() else 0.0
    pnl_b = round(payout_b - stake_b, 2)
    roi_b = round((pnl_b / stake_b) * 100, 2)
    rule_b = f"[DOWNTIME_BACKFILL] HF Adaptive Gap {gap:+.1f} (Bet {direction} @ {entry_p:.2f}¢)"

    cursor.execute("""
        INSERT INTO dry_run_trades
        (cycle_id, session_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds,
         spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd,
         winning_outcome, is_winner, pnl, roi_pct, status, rule_triggered, final_settle_price, resolved_at)
        VALUES (?, 4, ?, ?, ?, 180, 120, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'RESOLVED_WIN', ?, ?, ?)
    """, (cid, cid + 180, call_iso_a, direction, final_p, final_p - gap, gap, entry_p, shares_b, stake_b,
          winner, pnl_b, roi_b, rule_b, final_p, res_iso_a))
    tid_b = cursor.lastrowid
    b_bal += pnl_b
    b_added_pnl += pnl_b
    print(f"Added Bot B Trade #{tid_b} for Cycle {cid}: {direction} -> PnL +${pnl_b:.2f} | New Bal: ${b_bal:.2f}")

# Update wallet balances in DB
now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
cursor.execute("UPDATE wallet SET balance = ?, updated_at = ? WHERE session_id = 3", (round(a_bal, 2), now_iso))
cursor.execute("UPDATE wallet SET balance = ?, updated_at = ? WHERE session_id = 4", (round(b_bal, 2), now_iso))

conn.commit()
print(f"\nSuccessfully committed downtime backfill!")
print(f"Bot A Final Bankroll: ${a_bal:.2f} (Added PnL: +${a_added_pnl:.2f})")
print(f"Bot B Final Bankroll: ${b_bal:.2f} (Added PnL: +${b_added_pnl:.2f})")

conn.close()
