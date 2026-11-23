"""
Autonomous BTC 5-Minute Polymarket Dry-Run Trading Bot (High-Frequency Mode)
- Strategy: Adaptive Dynamic Empirical Boundary with +5% Buffer (Tighter safety margin, higher trade frequency)
- Starts with: $35.26 bankroll (Session #4)
- Sizing: Dynamic Compounding 15% of bankroll (min $3.00, max $10.00)
- Lockout: Strict final 2 minutes (remaining <= 120s and >= 15s)
- Execution: Simulated against real top-of-book depth (>= $5.00 size)
- Tracks independently in wallet table (id = 2) and dry_run_trades (session_id = 4)
"""

import os
import sys
import time
import json
import sqlite3
import datetime

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
BOT_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dry_run_bot_frequency.log")
CURRENT_SESSION = 4
WALLET_ID = 2
STARTING_BANKROLL = 35.26
BUFFER_PCT = 0.05  # +5% buffer over historical worst-case reversal
CHECK_INTERVAL_SECONDS = 1.0


def bot_log(msg):
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(BOT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] {msg}\n")
    except Exception:
        pass


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_bot_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dry_run_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER,
                session_id INTEGER,
                timestamp INTEGER,
                call_time TEXT,
                direction TEXT,
                elapsed_seconds INTEGER,
                remaining_seconds INTEGER,
                spot_at_call REAL,
                strike_price REAL,
                gap_at_call REAL,
                entry_price REAL,
                shares REAL,
                invested_usd REAL,
                winning_outcome TEXT,
                is_winner INTEGER,
                pnl REAL,
                roi_pct REAL,
                status TEXT,
                rule_triggered TEXT,
                final_settle_price REAL,
                resolved_at TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet (
                id INTEGER PRIMARY KEY,
                session_id INTEGER,
                balance REAL,
                initial_balance REAL,
                updated_at TEXT
            );
        """)
        cur = conn.cursor()
        cur.execute("SELECT session_id, balance FROM wallet WHERE id = ?", (WALLET_ID,))
        row = cur.fetchone()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not row or row[0] != CURRENT_SESSION:
            conn.execute("""
                INSERT OR REPLACE INTO wallet (id, session_id, balance, initial_balance, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (WALLET_ID, CURRENT_SESSION, STARTING_BANKROLL, STARTING_BANKROLL, now_iso))
            msg = f"💰 [FREQUENCY WALLET INITIALIZED] Session #{CURRENT_SESSION} loaded with ${STARTING_BANKROLL:.2f} starting bankroll."
            print(msg)
            bot_log(msg)
    conn.close()


def get_wallet_balance(conn):
    cur = conn.cursor()
    cur.execute("SELECT balance FROM wallet WHERE id = ?", (WALLET_ID,))
    row = cur.fetchone()
    return float(row[0]) if row else STARTING_BANKROLL


def update_wallet_balance(conn, pnl):
    cur = conn.cursor()
    cur.execute("SELECT balance FROM wallet WHERE id = ?", (WALLET_ID,))
    row = cur.fetchone()
    current = float(row[0]) if row else STARTING_BANKROLL
    new_bal = max(0.0, round(current + pnl, 2))
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with conn:
        conn.execute("UPDATE wallet SET balance = ?, updated_at = ? WHERE id = ?", (new_bal, now_iso, WALLET_ID))
    return new_bal


def get_adaptive_boundaries(conn, remaining):
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT record_up_squeeze, record_down_dump 
            FROM adaptive_safe_boundaries 
            WHERE ? BETWEEN min_remaining AND max_remaining
        """, (remaining,))
        row = cur.fetchone()
        if row:
            rec_squeeze, rec_dump = row[0], row[1]
            safe_up = round(max(rec_dump * (1.0 + BUFFER_PCT), rec_dump + 3.0), 1)
            safe_down = round(max(rec_squeeze * (1.0 + BUFFER_PCT), rec_squeeze + 3.0), 1)
            return safe_up, -safe_down
    except Exception:
        pass
    # Golden Time-Decayed fallbacks (+5% buffer)
    if remaining >= 90: return 95.9, -82.2
    elif remaining >= 60: return 77.6, -68.5
    elif remaining >= 45: return 59.3, -50.2
    elif remaining >= 30: return 45.7, -36.5
    else: return 31.9, -22.8


def resolve_settled_trades(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.trade_id, t.cycle_id, t.session_id, t.direction, t.entry_price, t.shares, t.invested_usd, 
            t.remaining_seconds, t.elapsed_seconds, t.spot_at_call, t.strike_price,
            c.final_price, c.winning_outcome, c.status
        FROM dry_run_trades t
        JOIN cycles c ON t.cycle_id = c.cycle_id
        WHERE t.status = 'OPEN' AND t.session_id = ? AND c.status = 'RESOLVED' AND c.final_price IS NOT NULL
    """, (CURRENT_SESSION,))
    settled_rows = cur.fetchall()

    for row in settled_rows:
        (t_id, cid, sess_id, direction, entry_p, shares, invested, rem, elap, spot_call, strike,
         final_price, winner, c_status) = row

        is_winner = 1 if direction.lower() == winner.lower() else 0
        payout = (shares * 1.0) if is_winner else 0.0
        pnl = round(payout - invested, 2)
        roi_pct = round((pnl / invested) * 100, 2)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        status_str = "RESOLVED_WIN" if is_winner else "RESOLVED_LOSS"

        with conn:
            conn.execute("""
                UPDATE dry_run_trades 
                SET winning_outcome = ?, final_settle_price = ?, is_winner = ?, 
                    pnl = ?, roi_pct = ?, status = ?, resolved_at = ?
                WHERE trade_id = ?
            """, (winner, final_price, is_winner, pnl, roi_pct, status_str, now_iso, t_id))

        new_wallet = update_wallet_balance(conn, pnl)
        diff = final_price - strike
        verdict_icon = "✅ WON!" if is_winner else "❌ LOST (-100%)"
        banner = (
            f"\n{'=' * 82}\n"
            f"⚡ [CYCLE RESOLVED & TRADE SETTLED - HIGH FREQUENCY BOT #4]\n"
            f"Trade Call:         #{t_id:02d} (Session #{sess_id}) for Cycle {cid}\n"
            f"When Called:        T-{rem}s remaining (Elapsed: {elap}s)\n"
            f"Spot at Call:       ${spot_call:,.2f} (Strike: ${strike:,.2f})\n"
            f"Our Prediction:     {direction.upper()} @ {entry_p:.2f}¢ (Stake: ${invested:.2f} -> {shares} shares)\n"
            f"Final Settle Price: ${final_price:,.2f} (Net Move: ${diff:+,.2f})\n"
            f"Settled Winner:     {winner.upper()}\n"
            f"Outcome:            {verdict_icon} | PnL: ${pnl:+.2f} ({roi_pct:+.1f}% ROI)\n"
            f"💰 New Bankroll:    ${new_wallet:.2f}\n"
            f"{'=' * 82}\n"
        )
        print(banner)
        bot_log(banner)


def is_in_blackout_window():
    """
    Returns True if current time is within high-volatility institutional rebalancing windows:
    1) NYSE Opening Bell: 05:25 PM - 06:05 PM EAT / 14:25 - 15:05 UTC (865 <= min < 905)
    2) European Market Close (London Fix): 07:20 PM - 07:40 PM EAT / 16:20 - 16:40 UTC (980 <= min < 1000)
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    utc_minute = now_utc.hour * 60 + now_utc.minute
    is_nyse_bell = 865 <= utc_minute < 905
    is_eu_close = 980 <= utc_minute < 1000
    return is_nyse_bell or is_eu_close


def check_for_trade_entry(conn):
    wallet_balance = get_wallet_balance(conn)
    if wallet_balance < 0.50:
        return  # Bankroll depleted

    # ── HIGH-VOLATILITY CIRCUIT BREAKER ──
    if is_in_blackout_window():
        return  # Blackout active (Protecting bankroll from NYSE opening and EU close whipsaws)

    cur = conn.cursor()
    # Get latest snapshot
    cur.execute("""
        SELECT 
            s.cycle_id, s.elapsed_seconds, s.remaining_seconds, s.spot_price, s.gap_dollars,
            s.up_best_ask, s.up_ask_depth, s.down_best_ask, s.down_ask_depth,
            c.strike_price
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'ACTIVE'
        ORDER BY s.id DESC 
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        return

    (cycle_id, elapsed, remaining, spot_price, gap_dollars,
     up_ask, up_depth, down_ask, down_depth, strike) = row

    if not strike:
        return

    # Check if a trade already exists for this cycle for this session
    cur.execute("SELECT trade_id FROM dry_run_trades WHERE cycle_id = ? AND session_id = ?", (cycle_id, CURRENT_SESSION))
    if cur.fetchone():
        return  # Max 1 trade per cycle per bot

    # STRICT LATE-ROUND RULE:
    # Strictly require remaining <= 90s (T-90s to T-15s).
    # All 2-minute (T-120s) entries are permanently eliminated to protect against macro reversals.
    if remaining > 90 or remaining < 15:
        return

    # ── EMPIRICAL HIGH-FREQUENCY BOUNDARY (+5% BUFFER) ──
    up_safe_gap, dn_safe_gap = get_adaptive_boundaries(conn, remaining)

    decision = None

    # UP Condition
    if gap_dollars >= up_safe_gap:
        if up_ask and 0.70 <= up_ask <= 0.95 and up_depth >= 5.0:
            decision = {
                "direction": "Up",
                "entry_price": up_ask,
                "gap": gap_dollars,
                "rule": f"HF Adaptive Gap >= +${up_safe_gap:.1f} at T-{remaining}s (UP Ask: {up_ask:.2f}¢)"
            }

    # DOWN Condition
    elif gap_dollars <= dn_safe_gap:
        if down_ask and 0.70 <= down_ask <= 0.95 and down_depth >= 5.0:
            decision = {
                "direction": "Down",
                "entry_price": down_ask,
                "gap": gap_dollars,
                "rule": f"HF Adaptive Gap <= -${abs(dn_safe_gap):.1f} at T-{remaining}s (DOWN Ask: {down_ask:.2f}¢)"
            }

    if decision:
        # Dynamic Compounding Sizing: Risk 15% of bankroll (min $3.00, max $10.00)
        stake = round(max(3.00, min(wallet_balance * 0.15, 10.00)), 2)
        stake = min(stake, wallet_balance)
        shares = round(stake / decision["entry_price"], 2)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            cur.execute("""
                INSERT INTO dry_run_trades 
                (cycle_id, session_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds, 
                 spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, 
                 status, rule_triggered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
            """, (
                cycle_id, CURRENT_SESSION, int(time.time()), now_iso, decision["direction"], elapsed, remaining,
                spot_price, strike, gap_dollars, decision["entry_price"], shares, stake,
                decision["rule"]
            ))
            t_id = cur.lastrowid

        rem_min = remaining // 60
        rem_sec = remaining % 60
        rem_str = f"T-{rem_min:02d}:{rem_sec:02d}"

        banner = (
            f"\n{'=' * 82}\n"
            f"⚡ [DRY-RUN CALL ENTERED - HIGH FREQUENCY BOT #4]\n"
            f"Trade ID:         #{t_id:02d}\n"
            f"Cycle ID:         {cycle_id}\n"
            f"Time Remaining:   {remaining} seconds left ({rem_str})\n"
            f"Elapsed Time:     {elapsed} seconds into 5-minute cycle\n"
            f"Strike Price:     ${strike:,.2f} | Current Spot: ${spot_price:,.2f} | Gap: ${gap_dollars:+,.2f}\n"
            f"Prediction:       {decision['direction'].upper()} @ {decision['entry_price']:.2f}¢\n"
            f"Compounded Stake: ${stake:.2f} (Bought {shares} shares | Wallet: ${wallet_balance:.2f})\n"
            f"Trigger Rule:     {decision['rule']}\n"
            f"Status:           ⏳ OPEN (Waiting for settlement)\n"
            f"{'=' * 82}\n"
        )
        print(banner)
        bot_log(banner)


def main():
    init_bot_db()
    conn = get_db()
    print("=" * 82)
    print("⚡ POLYMARKET BTC 5-MINUTE HIGH-FREQUENCY DRY-RUN BOT (BOT B) STARTED")
    print(f"💰 Starting Bankroll: ${STARTING_BANKROLL:.2f} (Session #{CURRENT_SESSION} | Wallet #{WALLET_ID})")
    print(f"🛡️ Adaptive Boundary: +5% Buffer on All-Time Historical Reversals")
    print(f"📁 Database: {DB_PATH}")
    print("=" * 82)

    last_heartbeat = 0
    while True:
        try:
            resolve_settled_trades(conn)
            check_for_trade_entry(conn)

            now = time.time()
            if now - last_heartbeat >= 30:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM dry_run_trades WHERE session_id = ? AND status = 'OPEN'", (CURRENT_SESSION,))
                open_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), COALESCE(SUM(pnl), 0) FROM dry_run_trades WHERE session_id = ? AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
                tot, wins, pnl = cur.fetchone()
                tot = tot or 0
                wins = wins or 0
                pnl = pnl or 0.0
                rate = (wins / tot * 100) if tot > 0 else 0.0
                bal = get_wallet_balance(conn)
                cb_tag = " | 🛡️ HIGH-VOL BLACKOUT ACTIVE" if is_in_blackout_window() else ""
                print(f"[HF Bot #{CURRENT_SESSION} Heartbeat {datetime.datetime.now().strftime('%H:%M:%S')}] Bankroll: ${bal:.2f} | Open: {open_cnt} | Resolved: {tot} ({rate:.1f}% Win Rate) | Net PnL: ${pnl:+,.2f}{cb_tag}")
                last_heartbeat = now

            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n🛑 High-frequency bot stopped by user.")
            break
        except Exception as e:
            bot_log(f"Error in main loop: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
