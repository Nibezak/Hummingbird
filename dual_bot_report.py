import sqlite3
import datetime

DB_PATH = "c:/projects/btc-5m-recorder/btc_5m_data.db"

def report():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Wallet 1 (Bot A - High Security)
    c.execute("SELECT balance, initial_balance FROM wallet WHERE id = 1")
    w1 = c.fetchone()
    b1_cur, b1_init = (w1[0], w1[1]) if w1 else (35.26, 10.00)
    
    # Wallet 2 (Bot B - High Frequency)
    c.execute("SELECT balance, initial_balance FROM wallet WHERE id = 2")
    w2 = c.fetchone()
    b2_cur, b2_init = (w2[0], w2[1]) if w2 else (35.26, 35.26)
    
    # Bot A stats (session_id = 3)
    c.execute("""
        SELECT 
            count(*), 
            sum(case when is_winner=1 then 1 else 0 end),
            sum(case when is_winner=0 then 1 else 0 end),
            sum(pnl)
        FROM dry_run_trades 
        WHERE session_id = 3
    """)
    s3_tot, s3_win, s3_loss, s3_pnl = c.fetchone()
    s3_tot = s3_tot or 0
    s3_win = s3_win or 0
    s3_loss = s3_loss or 0
    s3_pnl = s3_pnl or 0.0
    s3_wr = (s3_win / s3_tot * 100) if s3_tot > 0 else 0.0
    
    # Bot B stats (session_id = 4)
    c.execute("""
        SELECT 
            count(*), 
            sum(case when is_winner=1 then 1 else 0 end),
            sum(case when is_winner=0 then 1 else 0 end),
            sum(pnl)
        FROM dry_run_trades 
        WHERE session_id = 4
    """)
    s4_tot, s4_win, s4_loss, s4_pnl = c.fetchone()
    s4_tot = s4_tot or 0
    s4_win = s4_win or 0
    s4_loss = s4_loss or 0
    s4_pnl = s4_pnl or 0.0
    s4_wr = (s4_win / s4_tot * 100) if s4_tot > 0 else 0.0
    
    # Win streak Bot A
    c.execute("SELECT is_winner FROM dry_run_trades WHERE session_id = 3 ORDER BY trade_id DESC")
    rows_a = c.fetchall()
    streak_a = 0
    for r in rows_a:
        if r[0] == 1: streak_a += 1
        elif r[0] == 0: break
        
    # Win streak Bot B
    c.execute("SELECT is_winner FROM dry_run_trades WHERE session_id = 4 ORDER BY trade_id DESC")
    rows_b = c.fetchall()
    streak_b = 0
    for r in rows_b:
        if r[0] == 1: streak_b += 1
        elif r[0] == 0: break

    print("=" * 96)
    print("🥊 POLYMARKET BTC 5-MINUTE DRY-RUN: HEAD-TO-HEAD BATTLE ROYALE")
    print("=" * 96)
    print(f"{'Metric':<28} | {'🛡️ BOT A (HIGH-SECURITY)':<32} | {'⚡ BOT B (HIGH-FREQUENCY)':<32}")
    print("-" * 96)
    print(f"{'Strategy Calibration':<28} | {'Empirical Record + 15% Buffer':<32} | {'Empirical Record + 5% Buffer':<32}")
    print(f"{'Experiment Start Balance':<28} | {f'${b1_init:.2f} (started $10.00)':<32} | {f'${b2_init:.2f}':<32}")
    print(f"{'Current Bankroll':<28} | {f'${b1_cur:.2f}':<32} | {f'${b2_cur:.2f}':<32}")
    print(f"{'Net Profit / Return':<28} | {f'+${b1_cur - 10.0:.2f} (+{(b1_cur-10.0)/10.0*100:.1f}%)':<32} | {f'+${b2_cur - b2_init:.2f} (+{(b2_cur-b2_init)/b2_init*100:.1f}%)':<32}")
    print(f"{'Trades Taken':<28} | {f'{s3_tot} Trades':<32} | {f'{s4_tot} Trades':<32}")
    print(f"{'Wins / Losses':<28} | {f'{s3_win}W / {s3_loss}L':<32} | {f'{s4_win}W / {s4_loss}L':<32}")
    print(f"{'Win Rate':<28} | {f'{s3_wr:.1f}%':<32} | {f'{s4_wr:.1f}%':<32}")
    print(f"{'Active Winning Streak':<28} | {f'🔥 {streak_a} consecutive wins':<32} | {f'🔥 {streak_b} consecutive wins':<32}")
    print("=" * 96)
    
    # Print recent trades from both bots
    c.execute("""
        SELECT trade_id, session_id, call_time, remaining_seconds, direction, entry_price, gap_at_call, invested_usd, pnl, status
        FROM dry_run_trades 
        WHERE session_id IN (3, 4)
        ORDER BY trade_id DESC LIMIT 8
    """)
    recent = c.fetchall()
    if recent:
        print("\nRecent Activity (Both Bots Combined, latest first):")
        print("-" * 96)
        for r in recent:
            tid, sess, ctime, rem, direction, price, gap, stake, pnl, status = r
            dt = ctime.replace("T", " ").split(".")[0][:19]
            tag = "🛡️ Bot A (Security)" if sess == 3 else "⚡ Bot B (Frequency)"
            pnl_str = f"+${pnl:.2f}" if (pnl and pnl > 0) else (f"-${abs(pnl):.2f}" if pnl else "--")
            res_str = "✅ WON" if status == "RESOLVED_WIN" else ("❌ LOST" if status == "RESOLVED_LOSS" else "⏳ OPEN")
            print(f"#{tid:03d} [{tag}] {dt} UTC | T-{rem}s | {direction.upper()} @ {price:.2f}¢ | Gap ${gap:+.1f} | Stake ${stake:.2f} | {res_str} ({pnl_str})")
        print("-" * 96)

    conn.close()

if __name__ == "__main__":
    report()
