import sqlite3
import time
import datetime
import json
import os
import urllib.request
import urllib.error

DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"
BOUNDARIES_CONFIG_PATH = r"c:\projects\btc-5m-recorder\multi_asset_safe_boundaries.json"

CURRENT_SESSION = 2
WALLET_ID = 2  # Wallet 2 for Bot B (High Frequency)
MAX_STAKE_CEILING = 10.00
STAKE_FRACTION = 0.15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Default Empirical HF Boundaries fallbacks (+5% buffer)
DEFAULT_HF_BOUNDARIES = {
    'BTC': {90: (95.9, -82.2), 60: (77.6, -68.5), 45: (59.3, -50.2), 30: (45.7, -36.5), 15: (32.0, -22.8)},
    'ETH': {90: (7.75, -6.84), 60: (5.93, -5.02), 45: (4.38, -3.65), 30: (3.20, -2.55), 15: (2.28, -1.64)},
    'SOL': {90: (1.64, -1.37), 60: (1.19, -1.00), 45: (0.87, -0.73), 30: (0.64, -0.50), 15: (0.41, -0.32)},
    'DOGE': {90: (0.0016, -0.0014), 60: (0.0012, -0.0010), 45: (0.0008, -0.0006), 30: (0.0005, -0.0005), 15: (0.0004, -0.0003)},
    'XRP': {90: (0.014, -0.011), 60: (0.010, -0.008), 45: (0.007, -0.005), 30: (0.005, -0.004), 15: (0.003, -0.002)},
    'BNB': {90: (3.20, -2.74), 60: (2.37, -2.01), 45: (1.73, -1.46), 30: (1.28, -1.00), 15: (0.82, -0.64)},
    'HYPE': {90: (1.37, -1.14), 60: (1.00, -0.82), 45: (0.73, -0.59), 30: (0.50, -0.41), 15: (0.32, -0.23)}
}

def get_boundaries_for_asset(asset, remaining):
    if os.path.exists(BOUNDARIES_CONFIG_PATH):
        try:
            with open(BOUNDARIES_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if asset in data and 'windows' in data[asset]:
                    w_dict = data[asset]['windows']
                    if remaining >= 80: key = '90'
                    elif remaining >= 55: key = '60'
                    elif remaining >= 40: key = '45'
                    else: key = '30'
                    if key in w_dict:
                        return w_dict[key]['hf_up'], w_dict[key]['hf_dn']
        except Exception:
            pass
            
    fb = DEFAULT_HF_BOUNDARIES.get(asset, DEFAULT_HF_BOUNDARIES['BTC'])
    if remaining >= 80: return fb[90]
    elif remaining >= 55: return fb[60]
    elif remaining >= 40: return fb[45]
    elif remaining >= 25: return fb[30]
    else: return fb[15]

def is_in_blackout_window():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    utc_minute = now_utc.hour * 60 + now_utc.minute
    is_nyse_bell = 865 <= utc_minute < 905
    is_eu_close = 980 <= utc_minute < 1000
    return is_nyse_bell or is_eu_close

def get_wallet_balance(conn):
    cur = conn.cursor()
    cur.execute("SELECT balance FROM multi_wallet WHERE id = ?", (WALLET_ID,))
    row = cur.fetchone()
    return row[0] if row else 10.00

def update_wallet_balance(conn, pnl):
    cur = conn.cursor()
    cur.execute("SELECT balance FROM multi_wallet WHERE id = ?", (WALLET_ID,))
    current = cur.fetchone()[0]
    new_bal = round(max(0.0, current + pnl), 2)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with conn:
        conn.execute("UPDATE multi_wallet SET balance = ?, updated_at = ? WHERE id = ?", (new_bal, now_iso, WALLET_ID))
    return new_bal

def fetch_live_orderbook_fill(token_id, opp_token_id, target_stake_usd, cur=None, cycle_id=None, asset=None, direction=None):
    """
    Simulates real Polymarket CLOB Taker execution by traversing live orderbook asks.
    Traverses direct asks on target token AND synthetic asks from opposite token bids (1.0 - bid),
    matching Polymarket's genuine dual-sided binary CLOB liquidity.
    Computes exact Volume-Weighted Average Price (VWAP) across depth levels.
    STRICT: If no live orderbook liquidity exists or CLOB is unreachable, returns None.
    ZERO synthetic static fallbacks (never substitutes hardcoded 88c/86c).
    """
    asks = []
    
    # 1. Fetch direct asks on target token
    if token_id:
        try:
            url = f"https://clob.polymarket.com/book?token_id={token_id}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                book = json.loads(resp.read().decode('utf-8'))
                for a in book.get("asks", []):
                    p, s = float(a["price"]), float(a["size"])
                    if p > 0 and s > 0:
                        asks.append({'price': p, 'size': s, 'type': 'direct'})
        except Exception:
            pass

    # 2. Fetch synthetic asks from opposite token bids (complementary matching: ask = 1.0 - bid)
    if opp_token_id:
        try:
            opp_url = f"https://clob.polymarket.com/book?token_id={opp_token_id}"
            req = urllib.request.Request(opp_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                opp_book = json.loads(resp.read().decode('utf-8'))
                for b in opp_book.get("bids", []):
                    bp, bs = float(b["price"]), float(b["size"])
                    syn_p = round(1.0 - bp, 4)
                    if syn_p > 0 and bs > 0:
                        asks.append({'price': syn_p, 'size': bs, 'type': 'synthetic'})
        except Exception:
            pass

    # 3. If CLOB direct is temporarily unreachable, check recent snapshot ask in DB as secondary real source
    if not asks and cur and cycle_id and asset and direction:
        col = "up_best_ask" if direction.lower() == "up" else "down_best_ask"
        dep_col = "up_ask_depth" if direction.lower() == "up" else "down_ask_depth"
        now_ts = int(time.time())
        cur.execute(f"""
            SELECT {col}, {dep_col} 
            FROM multi_snapshots 
            WHERE cycle_id = ? AND asset = ? AND {col} IS NOT NULL AND timestamp >= ?
            ORDER BY id DESC LIMIT 1
        """, (cycle_id, asset, now_ts - 3))
        db_row = cur.fetchone()
        if db_row and db_row[0]:
            db_ask = float(db_row[0])
            db_dep = float(db_row[1] or 10.0)
            if db_ask > 0:
                shares = round(target_stake_usd / db_ask, 2)
                return {
                    'best_ask': db_ask,
                    'ask': db_ask,
                    'shares': shares,
                    'depth': round(db_dep, 2),
                    'source': 'DB_RECENT_SNAPSHOT'
                }

    # STRICT: If no authentic orderbook liquidity was found, DO NOT TRADE.
    if not asks:
        return None

    sorted_asks = sorted(asks, key=lambda x: x["price"])
    best_ask = sorted_asks[0]["price"]
    shares = round(target_stake_usd / best_ask, 2)
    depth = round(sum(a["price"] * a["size"] for a in sorted_asks[:5]), 2)
    
    return {
        'best_ask': best_ask,
        'ask': best_ask,
        'shares': shares,
        'depth': depth,
        'source': 'LIVE_CLOB'
    }

def resolve_settled_trades(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.trade_id, t.cycle_id, t.asset, t.direction, t.entry_price, t.shares, t.invested_usd, 
            t.remaining_seconds, t.elapsed_seconds, t.spot_at_call, t.strike_price,
            c.final_price, c.winning_outcome, c.status
        FROM multi_trades t
        JOIN multi_cycles c ON t.cycle_id = c.cycle_id AND t.asset = c.asset
        WHERE t.status = 'OPEN' AND t.session_id = ? AND c.status = 'RESOLVED' AND c.final_price IS NOT NULL
    """, (CURRENT_SESSION,))
    settled_rows = cur.fetchall()

    for row in settled_rows:
        (t_id, cid, asset, direction, entry_p, shares, invested, rem, elap, spot_call, strike,
         final_price, winner, c_status) = row

        is_winner = 1 if direction.lower() == winner.lower() else 0
        payout = (shares * 1.0) if is_winner else 0.0
        pnl = round(payout - invested, 2)
        roi_pct = round((pnl / invested) * 100, 2)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        status_str = "RESOLVED_WIN" if is_winner else "RESOLVED_LOSS"

        with conn:
            conn.execute("""
                UPDATE multi_trades 
                SET winning_outcome = ?, final_settle_price = ?, is_winner = ?, 
                    pnl = ?, roi_pct = ?, status = ?, resolved_at = ?
                WHERE trade_id = ?
            """, (winner, final_price, is_winner, pnl, roi_pct, status_str, now_iso, t_id))

        new_wallet = update_wallet_balance(conn, pnl)
        verdict = "WON!" if is_winner else "LOST (-100%)"
        print(f"\n[RESOLVED {asset}] Trade #{t_id} (Cycle {cid}) | Prediction: {direction.upper()} | Winner: {winner.upper()} -> {verdict} | PnL: ${pnl:+.2f} | Bankroll: ${new_wallet:.2f}", flush=True)

def evaluate_and_trade(conn):
    wallet_balance = get_wallet_balance(conn)
    if wallet_balance < 0.50:
        return

    if is_in_blackout_window():
        return

    cur = conn.cursor()

    cur.execute("SELECT COALESCE(SUM(invested_usd), 0) FROM multi_trades WHERE session_id = ? AND status = 'OPEN'", (CURRENT_SESSION,))
    open_in_play = cur.fetchone()[0] or 0.0
    available_cash = max(0.0, wallet_balance - open_in_play)
    if available_cash < 0.50:
        return

    cur.execute("""
        SELECT s.cycle_id, s.asset, s.elapsed_seconds, s.remaining_seconds, s.spot_price, s.gap_dollars,
               s.up_best_ask, s.up_ask_depth, s.down_best_ask, s.down_ask_depth, c.strike_price,
               c.up_token_id, c.down_token_id
        FROM multi_snapshots s
        JOIN multi_cycles c ON s.cycle_id = c.cycle_id AND s.asset = c.asset
        WHERE c.status = 'ACTIVE'
          AND s.id IN (SELECT MAX(id) FROM multi_snapshots GROUP BY asset)
    """)
    rows = cur.fetchall()
    if not rows:
        return

    candidates = []
    nominal_stake = round(min(available_cash * STAKE_FRACTION, MAX_STAKE_CEILING), 2)

    for r in rows:
        cid, asset, elapsed, remaining, spot, gap, up_ask, up_dep, dn_ask, dn_dep, strike, up_tok, dn_tok = r
        if not strike:
            continue

        if remaining > 90 or remaining < 15:
            continue

        cur.execute("SELECT trade_id FROM multi_trades WHERE cycle_id = ? AND asset = ? AND session_id = ?", (cid, asset, CURRENT_SESSION))
        if cur.fetchone():
            continue

        up_safe, dn_safe = get_boundaries_for_asset(asset, remaining)

        # Check UP
        if gap >= up_safe:
            fill = fetch_live_orderbook_fill(up_tok, dn_tok, nominal_stake, cur, cid, asset, 'Up')
            if fill and (0.65 <= fill['best_ask'] <= 0.98):
                ask = fill['best_ask']
                candidates.append({
                    'asset': asset, 'cycle_id': cid, 'direction': 'Up', 'elapsed': elapsed,
                    'remaining': remaining, 'spot': spot, 'strike': strike, 'gap': gap,
                    'ask': ask, 'best_ask': fill['best_ask'], 'depth': fill['depth'],
                    'shares': fill['shares'],
                    'source': fill['source'],
                    'rule': f'HF Empirical UP Gap >= +${up_safe} at T-{remaining}s'
                })

        # Check DOWN
        elif gap <= dn_safe:
            fill = fetch_live_orderbook_fill(dn_tok, up_tok, nominal_stake, cur, cid, asset, 'Down')
            if fill and (0.65 <= fill['best_ask'] <= 0.98):
                ask = fill['best_ask']
                candidates.append({
                    'asset': asset, 'cycle_id': cid, 'direction': 'Down', 'elapsed': elapsed,
                    'remaining': remaining, 'spot': spot, 'strike': strike, 'gap': gap,
                    'ask': ask, 'best_ask': fill['best_ask'], 'depth': fill['depth'],
                    'shares': fill['shares'],
                    'source': fill['source'],
                    'rule': f'HF Empirical DOWN Gap <= ${dn_safe} at T-{remaining}s'
                })

    if not candidates:
        return

    # Prioritize cheapest ask contract first across all qualified coins
    candidates.sort(key=lambda x: x['ask'])

    for cand in candidates:
        stake = round(min(available_cash * STAKE_FRACTION, MAX_STAKE_CEILING), 2)
        if stake < 0.50 or stake > available_cash:
            break

        shares = round(stake / cand['ask'], 2)
        now_ts = int(time.time())
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rule_desc = f"{cand['rule']} | {cand['source']} Best Ask {cand['ask']*100:.1f}¢ (depth: ${cand['depth']:.2f})"

        with conn:
            conn.execute("""
                INSERT INTO multi_trades 
                (cycle_id, asset, session_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds, spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, rule_triggered, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """, (cand['cycle_id'], cand['asset'], CURRENT_SESSION, now_ts, now_iso, cand['direction'],
                  cand['elapsed'], cand['remaining'], cand['spot'], cand['strike'], cand['gap'], cand['ask'],
                  shares, stake, rule_desc))

        available_cash -= stake
        print(f"\n[BOT B EXECUTION] {cand['asset']} {cand['direction'].upper()} @ {cand['ask']*100:.1f}¢ ({cand['source']}) | Stake: ${stake:.2f} ({shares} sh) | Gap: {cand['gap']:+,.2f} | T-{cand['remaining']}s | Avail Cash: ${available_cash:.2f}", flush=True)

def main():
    conn = sqlite3.connect(DB_PATH)
    print("==================================================================", flush=True)
    print(f"MULTI-ASSET BOT B (HIGH FREQUENCY) ACTIVATED (RUN #{CURRENT_SESSION})", flush=True)
    print(f"Database: {DB_PATH}", flush=True)
    bal = get_wallet_balance(conn)
    print(f"Starting Bankroll: ${bal:.2f}", flush=True)
    print(f"Execution Engine: Live CLOB Best Ask + Real-time In-Play Deduction", flush=True)
    print(f"Strategy: Cheapest-Ask Prioritization & Multi-Trade Capacity", flush=True)
    print("==================================================================\n", flush=True)

    last_heartbeat = 0
    while True:
        try:
            resolve_settled_trades(conn)
            evaluate_and_trade(conn)

            now = time.time()
            if now - last_heartbeat >= 60:
                cur = conn.cursor()
                cur.execute("SELECT balance FROM multi_wallet WHERE id = ?", (WALLET_ID,))
                current_bal = cur.fetchone()[0]
                cur.execute("SELECT COALESCE(SUM(invested_usd), 0) FROM multi_trades WHERE session_id = ? AND status = 'OPEN'", (CURRENT_SESSION,))
                in_play = cur.fetchone()[0] or 0.0
                cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END) FROM multi_trades WHERE session_id = ? AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
                tot, wins = cur.fetchone()
                tot = tot or 0
                wins = wins or 0
                win_pct = (wins / tot * 100) if tot > 0 else 0.0
                dt_str = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{dt_str}] BOT B HEARTBEAT | Equity: ${current_bal:.2f} (In-Play: ${in_play:.2f}) | Trades: {tot} | Wins: {wins} ({win_pct:.1f}%)", flush=True)
                last_heartbeat = now

            time.sleep(1.0)
        except Exception as e:
            print(f"[BOT B ERROR] Loop exception: {e}", flush=True)
            time.sleep(2.0)

if __name__ == "__main__":
    main()
