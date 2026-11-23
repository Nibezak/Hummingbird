"""
Polymarket BTC 5-Minute Dry-Run Performance Scorecard
=====================================================
Shows real-time accuracy, win-rate, time remaining at entry, 
and final outcomes for the active session (Run #2) and all-time.

Run anytime with: python dry_run_report.py
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
CURRENT_SESSION = 3


def show_report():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dry_run_trades'")
    if not cur.fetchone():
        print("ℹ️ No dry-run trades recorded yet.")
        conn.close()
        return

    # Check Wallet
    wallet_bal = 10.00
    init_bal = 10.00
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wallet'")
    if cur.fetchone():
        cur.execute("SELECT balance, initial_balance FROM wallet WHERE id = 1")
        w_row = cur.fetchone()
        if w_row:
            wallet_bal = float(w_row[0])
            init_bal = float(w_row[1]) if w_row[1] is not None else 10.00

    # Run #2 Session stats
    cur.execute("SELECT COUNT(*) FROM dry_run_trades WHERE session_id = ?", (CURRENT_SESSION,))
    s2_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dry_run_trades WHERE session_id = ? AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
    s2_resolved = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dry_run_trades WHERE session_id = ? AND is_winner = 1", (CURRENT_SESSION,))
    s2_wins = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dry_run_trades WHERE session_id = ? AND is_winner = 0 AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
    s2_losses = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(pnl), 0) FROM dry_run_trades WHERE session_id = ? AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
    s2_pnl = cur.fetchone()[0]

    s2_win_rate = (s2_wins / s2_resolved * 100) if s2_resolved > 0 else 0.0

    print("=" * 96)
    print(f"🎯 POLYMARKET BTC 5-MINUTE DRY-RUN SCORECARD — RUN #{CURRENT_SESSION} ACTIVE")
    print("=" * 96)
    print(f"💰 Current Bankroll:   ${wallet_bal:.2f} (Started with ${init_bal:.2f})")
    print(f"📊 Run #{CURRENT_SESSION} Trades:     Total: {s2_total} | Wins: {s2_wins} | Losses: {s2_losses} | Win Rate: {s2_win_rate:.1f}%")
    print(f"📈 Net PnL (Run #{CURRENT_SESSION}):  ${s2_pnl:+,.2f}")
    print("🛡️ Guardrail Rules:     Strictly Final 2 Minutes (remaining <= 120s) | Empirical Safe Boundaries")
    print("=" * 96)

    cur.execute("""
        SELECT 
            t.trade_id, t.cycle_id, t.session_id, t.call_time, t.direction, t.entry_price, t.shares, t.invested_usd,
            t.remaining_seconds, t.elapsed_seconds, t.spot_at_call, t.strike_price,
            c.final_price, c.winning_outcome, t.is_winner, t.pnl, t.roi_pct, t.status, t.rule_triggered
        FROM dry_run_trades t
        LEFT JOIN cycles c ON t.cycle_id = c.cycle_id
        ORDER BY t.trade_id DESC 
        LIMIT 10
    """)
    rows = cur.fetchall()

    if not rows:
        print("\n⏳ Bot is scanning for the next safe entry... Trades will appear here once triggered.\n")
        conn.close()
        return

    print("\nRecent Trade Calls & Outcomes (Most recent first):")
    print("-" * 96)
    for r in rows:
        (t_id, cid, sess_id, call_t, direction, entry_p, shares, invested, rem, elap, spot_call, strike,
         final_p, winner, is_win, pnl, roi, status, rule) = r

        time_short = call_t[11:19] if call_t and len(call_t) >= 19 else ""
        mins_rem = rem // 60 if rem is not None else 0
        secs_rem = rem % 60 if rem is not None else 0
        rem_str = f"T-{mins_rem:02d}:{secs_rem:02d} ({rem}s left)"

        if status == "OPEN":
            status_badge = "⏳ IN PROGRESS (Open)"
            outcome_str = f"Strike: ${strike:,.2f} | Awaiting final settlement..."
            pnl_str = "--"
        else:
            status_badge = "✅ WON" if is_win == 1 else "❌ LOST (-100%)"
            diff = (final_p - strike) if (final_p and strike) else 0.0
            winner_str = winner.upper() if winner else "?"
            outcome_str = f"Strike: ${strike:,.2f} ➔ Final: ${final_p:,.2f} (${diff:+,.2f}) | Settled Winner: {winner_str}"
            pnl_str = f"${pnl:+.2f} ({roi:+.1f}% ROI)"

        print(f"#{t_id:02d} [Run #{sess_id} | {time_short}] Cycle {cid} | Sizing: ${invested:.2f} | Status: {status_badge}")
        print(f"    ├─ When Called:  {rem_str} | Spot: ${spot_call:,.2f} | Call: {direction.upper()} @ {entry_p:.2f}¢ ({shares} shares)")
        print(f"    ├─ Final Result: {outcome_str}")
        print(f"    ├─ Performance:  PnL: {pnl_str}")
        print(f"    └─ Rule Trigger: {rule}")
        print("-" * 96)

    conn.close()


if __name__ == "__main__":
    show_report()
