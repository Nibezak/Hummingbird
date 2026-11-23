"""
Polymarket BTC 5-Minute Data Recorder
=====================================
Dedicated high-frequency data recorder:
- Logs real-time Bitcoin spot prices (Binance)
- Tracks 5-minute cycle strikes (price to beat)
- Records Polymarket UP & DOWN order books (best ask/bid, liquidity depth)
- Resolves completed cycles with official final settlement prices
- Writes to local SQLite database (btc_5m_data.db) in WAL mode
"""

import os
import sys
import time
import json
import sqlite3
import datetime
import urllib.request
import urllib.error
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder.log")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TICK_INTERVAL_SECONDS = 1.0


def file_log(msg):
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] {msg}\n")
    except Exception:
        pass


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cycles (
                cycle_id INTEGER PRIMARY KEY,
                slug TEXT UNIQUE,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                strike_price REAL,
                final_price REAL,
                winning_outcome TEXT,
                up_token_id TEXT,
                down_token_id TEXT,
                condition_id TEXT,
                max_positive_gap REAL DEFAULT 0,
                max_negative_gap REAL DEFAULT 0,
                status TEXT DEFAULT 'ACTIVE',
                created_at TEXT,
                updated_at TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER,
                timestamp INTEGER,
                elapsed_seconds INTEGER,
                remaining_seconds INTEGER,
                spot_price REAL,
                gap_dollars REAL,
                gap_bps REAL,
                up_best_ask REAL,
                up_best_bid REAL,
                up_ask_depth REAL,
                down_best_ask REAL,
                down_best_bid REAL,
                down_ask_depth REAL,
                recorded_at TEXT,
                FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_cycle ON snapshots(cycle_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_remaining ON snapshots(remaining_seconds);")
    conn.close()


def http_get_json(url, timeout=4):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_binance_spot_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        data = http_get_json(url, timeout=3)
        return float(data["price"])
    except Exception:
        return None


def get_binance_kline_open(cycle_ts):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={cycle_ts * 1000}&limit=1"
        data = http_get_json(url, timeout=4)
        if data and len(data) > 0:
            return float(data[0][1])  # Open price of minute
    except Exception:
        pass
    return None


def fetch_polymarket_market(cycle_ts):
    slug = f"btc-updown-5m-{cycle_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        events = http_get_json(url, timeout=5)
        if isinstance(events, list) and len(events) > 0:
            ev = events[0]
            markets = ev.get("markets", [])
            if markets:
                m = markets[0]
                clob_tokens = m.get("clobTokenIds")
                if isinstance(clob_tokens, str):
                    try:
                        clob_tokens = json.loads(clob_tokens)
                    except Exception:
                        clob_tokens = []
                up_token = clob_tokens[0] if len(clob_tokens) > 0 else None
                down_token = clob_tokens[1] if len(clob_tokens) > 1 else None
                return {
                    "slug": slug,
                    "title": ev.get("title", ""),
                    "up_token_id": up_token,
                    "down_token_id": down_token,
                    "condition_id": m.get("conditionId"),
                    "closed": m.get("closed", False),
                    "outcomePrices": m.get("outcomePrices")
                }
    except Exception:
        pass
    return None


def fetch_orderbook(token_id):
    if not token_id:
        return {"best_bid": None, "best_ask": None, "ask_depth": 0.0, "bid_depth": 0.0}

    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        book = http_get_json(url, timeout=3)
        bids = book.get("bids", [])
        asks = book.get("asks", [])

        # Polymarket CLOB lists asks descending (0.99 -> 0.10) and bids ascending (0.01 -> 0.90)
        # Lowest ask is the true best ask you can buy; highest bid is the true best bid you can sell into.
        best_bid = max(float(b["price"]) for b in bids) if bids else None
        best_ask = min(float(a["price"]) for a in asks) if asks else None

        sorted_asks = sorted(asks, key=lambda x: float(x["price"])) if asks else []
        sorted_bids = sorted(bids, key=lambda x: float(x["price"]), reverse=True) if bids else []

        ask_depth = sum(float(a["size"]) * float(a["price"]) for a in sorted_asks[:3]) if sorted_asks else 0.0
        bid_depth = sum(float(b["size"]) * float(b["price"]) for b in sorted_bids[:3]) if sorted_bids else 0.0

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "ask_depth": round(ask_depth, 2),
            "bid_depth": round(bid_depth, 2)
        }
    except Exception:
        return {"best_bid": None, "best_ask": None, "ask_depth": 0.0, "bid_depth": 0.0}


def get_or_create_cycle(conn, cycle_ts):
    cur = conn.cursor()
    cur.execute("SELECT cycle_id, strike_price, up_token_id, down_token_id, status FROM cycles WHERE cycle_id = ?", (cycle_ts,))
    row = cur.fetchone()

    if row:
        return {
            "cycle_id": row[0],
            "strike_price": row[1],
            "up_token_id": row[2],
            "down_token_id": row[3],
            "status": row[4]
        }

    # Discover and peg strike
    strike_price = get_binance_kline_open(cycle_ts)
    if not strike_price:
        strike_price = get_binance_spot_price()

    m_info = fetch_polymarket_market(cycle_ts)
    slug = m_info.get("slug") if m_info else f"btc-updown-5m-{cycle_ts}"
    title = m_info.get("title") if m_info else f"Bitcoin Up or Down 5m ({cycle_ts})"
    up_token = m_info.get("up_token_id") if m_info else None
    down_token = m_info.get("down_token_id") if m_info else None
    cond_id = m_info.get("condition_id") if m_info else None

    start_iso = datetime.datetime.fromtimestamp(cycle_ts, tz=datetime.timezone.utc).isoformat()
    end_iso = datetime.datetime.fromtimestamp(cycle_ts + 300, tz=datetime.timezone.utc).isoformat()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with conn:
        conn.execute("""
            INSERT OR IGNORE INTO cycles 
            (cycle_id, slug, title, start_time, end_time, strike_price, up_token_id, down_token_id, condition_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cycle_ts, slug, title, start_iso, end_iso, strike_price, up_token, down_token, cond_id, now_iso, now_iso))

    return {
        "cycle_id": cycle_ts,
        "strike_price": strike_price,
        "up_token_id": up_token,
        "down_token_id": down_token,
        "status": "ACTIVE"
    }


def check_and_finalize_pending_cycles(conn):
    """Checks completed cycles and resolves them using Polymarket's official Chainlink TWAP outcome."""
    try:
        cur = conn.cursor()
        now = int(time.time())
        # Check cycles that ended in the last 45 minutes that are not yet RESOLVED
        cur.execute("""
            SELECT cycle_id, strike_price, status 
            FROM cycles 
            WHERE status IN ('ACTIVE', 'PENDING_RESOLUTION') AND cycle_id <= ?
            ORDER BY cycle_id ASC
        """, (now - 300,))
        pending = cur.fetchall()

        for cid, strike, stat in pending:
            elapsed_since_end = now - (cid + 300)
            m_info = fetch_polymarket_market(cid)
            poly_winner = None
            if m_info:
                prices = m_info.get("outcomePrices")
                if prices:
                    try:
                        p = json.loads(prices) if isinstance(prices, str) else prices
                        if float(p[0]) > 0.9:
                            poly_winner = "Up"
                        elif float(p[1]) > 0.9:
                            poly_winner = "Down"
                    except Exception:
                        pass

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if poly_winner:
                final_spot = get_binance_kline_open(cid + 300) or get_binance_spot_price()
                with conn:
                    conn.execute("""
                        UPDATE cycles 
                        SET final_price = ?, winning_outcome = ?, status = 'RESOLVED', updated_at = ?
                        WHERE cycle_id = ?
                    """, (final_spot, poly_winner, now_iso, cid))
                diff = (final_spot - strike) if (final_spot and strike) else 0.0
                res_str = f"🏁 [OFFICIAL POLYMARKET RESOLUTION] Cycle {cid} | Winner: {poly_winner.upper()} | Spot: ${final_spot:,.2f} (Diff: ${diff:+,.2f})"
                print(f"\n{res_str}\n")
                file_log(res_str)
                update_adaptive_boundaries_for_cycle(conn, cid)
            elif elapsed_since_end > 300:
                # If over 5 minutes passed and Polymarket API hasn't updated (fallback)
                final_spot = get_binance_kline_open(cid + 300) or get_binance_spot_price()
                fallback_winner = "Up" if final_spot >= strike else "Down"
                with conn:
                    conn.execute("""
                        UPDATE cycles 
                        SET final_price = ?, winning_outcome = ?, status = 'RESOLVED', updated_at = ?
                        WHERE cycle_id = ?
                    """, (final_spot, fallback_winner, now_iso, cid))
                diff = (final_spot - strike) if (final_spot and strike) else 0.0
                res_str = f"⚠️ [FALLBACK RESOLUTION] Cycle {cid} | Winner: {fallback_winner.upper()} (Polymarket delayed >5m)"
                print(f"\n{res_str}\n")
                file_log(res_str)
                update_adaptive_boundaries_for_cycle(conn, cid)
            else:
                if stat != 'PENDING_RESOLUTION':
                    with conn:
                        conn.execute("""
                            UPDATE cycles SET status = 'PENDING_RESOLUTION', updated_at = ? WHERE cycle_id = ?
                        """, (now_iso, cid))
    except Exception as e:
        file_log(f"Error in check_and_finalize_pending_cycles: {e}")


def update_adaptive_boundaries_for_cycle(conn, cycle_id):
    try:
        cur = conn.cursor()
        cur.execute("SELECT strike_price, final_price FROM cycles WHERE cycle_id = ?", (cycle_id,))
        row = cur.fetchone()
        if not row or not row[0] or not row[1]:
            return
        strike, final = row[0], row[1]

        cur.execute("""
            SELECT remaining_seconds, spot_price, gap_dollars
            FROM snapshots
            WHERE cycle_id = ? AND remaining_seconds BETWEEN 15 AND 120
        """, (cycle_id,))
        snaps = cur.fetchall()
        if not snaps:
            return

        has_reversal = False
        reversal_details = []
        for rem, spot, gap in snaps:
            if gap is not None:
                if gap < 0 and final > strike:
                    has_reversal = True
                    reversal_details.append(("UP_SQUEEZE", abs(gap), rem))
                elif gap > 0 and final < strike:
                    has_reversal = True
                    reversal_details.append(("DOWN_DUMP", gap, rem))

        if not has_reversal:
            return

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Check if an actual live trade was taken in this cycle and suffered a loss
        cur.execute("""
            SELECT trade_id, session_id, direction, is_winner, remaining_seconds, gap_at_call
            FROM dry_run_trades 
            WHERE cycle_id = ? AND is_winner = 0
        """, (cycle_id,))
        lost_trades = cur.fetchall()

        if lost_trades:
            for t_id, sess_id, direction, is_win, rem_at_call, gap_call in lost_trades:
                # Find bracket for this trade
                cur.execute("""
                    SELECT bracket, safe_up_gap, safe_down_gap, record_up_squeeze, record_down_dump, buffer_pct
                    FROM adaptive_safe_boundaries
                    WHERE ? BETWEEN min_remaining AND max_remaining
                """, (rem_at_call,))
                b_row = cur.fetchone()
                if b_row:
                    b_name, s_up, s_dn, r_sq, r_dp, buf = b_row
                    # Ratchet up defensively by 10% on the losing side
                    if direction.lower() == 'up':
                        new_dp = round(max(r_dp, abs(gap_call)) * 1.10, 1)
                        new_safe_up = round(new_dp * (1.0 + buf), 1)
                        cur.execute("UPDATE adaptive_safe_boundaries SET record_down_dump = ?, safe_up_gap = ?, updated_at = ? WHERE bracket = ?",
                                    (new_dp, new_safe_up, now_iso, b_name))
                    else:
                        new_sq = round(max(r_sq, abs(gap_call)) * 1.10, 1)
                        new_safe_dn = round(new_sq * (1.0 + buf), 1)
                        cur.execute("UPDATE adaptive_safe_boundaries SET record_up_squeeze = ?, safe_down_gap = ?, updated_at = ?",
                                    (new_sq, -new_safe_dn, now_iso, b_name))
                    conn.commit()
                    log_msg = f"🛡️ [ADAPTIVE LOSS RATCHET] Trade #{t_id} lost in Cycle {cycle_id}! {b_name} boundary ratcheted defensively."
                    print(log_msg)
                    file_log(log_msg)
        else:
            # Cycle had adverse reversal but our bots safely avoided taking a losing trade!
            # Log lesson to learning_log
            max_rev = max(r[1] for r in reversal_details)
            rev_type = reversal_details[0][0]
            cur.execute("""
                INSERT INTO learning_log (timestamp, event_type, cycle_id, bracket, old_safe_gap, new_safe_gap, reversal_observed, lesson)
                VALUES (?, 'AVOIDED_ADVERSE_REVERSAL', ?, 'ALL', 0, 0, ?, ?)
            """, (now_iso, cycle_id, round(max_rev, 2), f"Cycle {cycle_id} had {rev_type} of ${max_rev:.2f}. Safe boundaries protected capital; 0 losses taken."))
            conn.commit()
    except Exception as e:
        file_log(f"Error in update_adaptive_boundaries_for_cycle: {e}")



def record_loop():
    init_db()
    conn = sqlite3.connect(DB_PATH)

    print("=" * 80)
    print("📡 POLYMARKET BTC 5-MINUTE DATA RECORDER RUNNING")
    print(f"📁 Database: {DB_PATH}")
    print(f"⏱️ Frequency: Every {TICK_INTERVAL_SECONDS}s")
    print("=" * 80)

    while True:
        try:
            now = int(time.time())
            cycle_ts = now - (now % 300)
            elapsed = now - cycle_ts
            remaining = 300 - elapsed

            cycle_data = get_or_create_cycle(conn, cycle_ts)
            strike = cycle_data.get("strike_price")

            # Check and resolve any completed cycles officially via Polymarket
            check_and_finalize_pending_cycles(conn)

            spot_price = get_binance_spot_price()
            if not spot_price:
                time.sleep(1)
                continue

            if not strike:
                strike = spot_price
                with conn:
                    conn.execute("UPDATE cycles SET strike_price = ? WHERE cycle_id = ?", (strike, cycle_ts))
                cycle_data["strike_price"] = strike

            gap_dollars = spot_price - strike
            gap_bps = (gap_dollars / strike) * 10000.0 if strike else 0.0

            up_book = fetch_orderbook(cycle_data.get("up_token_id"))
            down_book = fetch_orderbook(cycle_data.get("down_token_id"))

            with conn:
                if gap_dollars > 0:
                    conn.execute("UPDATE cycles SET max_positive_gap = MAX(max_positive_gap, ?) WHERE cycle_id = ?", (gap_dollars, cycle_ts))
                else:
                    conn.execute("UPDATE cycles SET max_negative_gap = MIN(max_negative_gap, ?) WHERE cycle_id = ?", (gap_dollars, cycle_ts))

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with conn:
                conn.execute("""
                    INSERT INTO snapshots 
                    (cycle_id, timestamp, elapsed_seconds, remaining_seconds, spot_price, gap_dollars, gap_bps, 
                     up_best_ask, up_best_bid, up_ask_depth, down_best_ask, down_best_bid, down_ask_depth, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cycle_ts, now, elapsed, remaining, spot_price, gap_dollars, gap_bps,
                    up_book["best_ask"], up_book["best_bid"], up_book["ask_depth"],
                    down_book["best_ask"], down_book["best_bid"], down_book["ask_depth"],
                    now_iso
                ))

            up_ask_str = f"{up_book['best_ask']:.2f}¢" if up_book['best_ask'] else "N/A"
            dn_ask_str = f"{down_book['best_ask']:.2f}¢" if down_book['best_ask'] else "N/A"
            mins_left = remaining // 60
            secs_left = remaining % 60
            sign = "+" if gap_dollars >= 0 else ""

            status_line = (
                f"[Cycle {cycle_ts} | T-{mins_left:02d}:{secs_left:02d}] "
                f"BTC: ${spot_price:,.2f} | Strike: ${strike:,.2f} | Gap: {sign}${gap_dollars:,.2f} ({sign}{gap_bps:.1f} bps) | "
                f"UP Ask: {up_ask_str} | DOWN Ask: {dn_ask_str}"
            )

            sys.stdout.write(f"\r{status_line}")
            sys.stdout.flush()

            if remaining % 30 == 0:
                file_log(status_line)

            time.sleep(TICK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n🛑 Recorder stopped by user.")
            break
        except Exception:
            time.sleep(2)


if __name__ == "__main__":
    record_loop()
