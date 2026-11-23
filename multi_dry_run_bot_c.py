import sqlite3
import time
import datetime
import json
import os
import urllib.request
import urllib.error

DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"
BOUNDARIES_CONFIG_PATH = r"c:\projects\btc-5m-recorder\multi_asset_safe_boundaries.json"

CURRENT_SESSION = 3
WALLET_ID = 3  # Wallet 3 for Bot C (Ultra High Frequency - T <= 120s)
MAX_STAKE_CEILING = 10.00
STAKE_FRACTION = 0.15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Default Empirical HF Boundaries fallbacks (+5% buffer)
DEFAULT_HF_BOUNDARIES = {
    'BTC': {120: (110.0, -95.0), 90: (95.9, -82.2), 60: (77.6, -68.5), 45: (59.3, -50.2), 30: (45.7, -36.5), 15: (32.0, -22.8)},
    'ETH': {120: (9.0, -8.0), 90: (7.75, -6.84), 60: (5.93, -5.02), 45: (4.38, -3.65), 30: (3.20, -2.55), 15: (2.28, -1.64)},
    'SOL': {120: (1.9, -1.6), 90: (1.64, -1.37), 60: (1.19, -1.00), 45: (0.87, -0.73), 30: (0.64, -0.50), 15: (0.41, -0.32)},
    'DOGE': {120: (0.0019, -0.0016), 90: (0.0016, -0.0014), 60: (0.0012, -0.0010), 45: (0.0008, -0.0006), 30: (0.0005, -0.0005), 15: (0.0004, -0.0003)},
    'XRP': {120: (0.016, -0.013), 90: (0.014, -0.011), 60: (0.010, -0.008), 45: (0.007, -0.005), 30: (0.005, -0.004), 15: (0.003, -0.002)},
    'BNB': {120: (3.7, -3.2), 90: (3.20, -2.74), 60: (2.37, -2.01), 45: (1.73, -1.46), 30: (1.28, -1.00), 15: (0.82, -0.64)},
    'HYPE': {120: (1.6, -1.3), 90: (1.37, -1.14), 60: (1.00, -0.82), 45: (0.73, -0.59), 30: (0.50, -0.41), 15: (0.32, -0.23)}
}

def get_boundaries_for_asset(asset, remaining):
    if os.path.exists(BOUNDARIES_CONFIG_PATH):
        try:
            with open(BOUNDARIES_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if asset in data and 'windows' in data[asset]:
                    w_dict = data[asset]['windows']
                    if remaining >= 105: key = '120'
                    elif remaining >= 80: key = '90'
                    elif remaining >= 55: key = '60'
                    elif remaining >= 40: key = '45'
                    else: key = '30'
                    if key in w_dict:
                        return w_dict[key]['hf_up'], w_dict[key]['hf_dn']
        except Exception:
            pass
            
    fb = DEFAULT_HF_BOUNDARIES.get(asset, DEFAULT_HF_BOUNDARIES['BTC'])
    if remaining >= 105: return fb[120]
    elif remaining >= 80: return fb[90]
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

def fetch_live_orderbook_fill(token_id, target_stake_usd, fallback_price, cur, cycle_id, asset, direction):
    """
    Simulates real Polymarket CLOB Taker execution by traversing live orderbook asks.
    Computes exact Volume-Weighted Average Price (VWAP) across depth levels,
    measuring true market slippage rather than assuming fixed price execution.
    """
    if token_id:
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                book = json.loads(resp.read().decode('utf-8'))
                asks = book.get("asks", [])
                if asks:
                    sorted_asks = sorted(asks, key=lambda x: float(x["price"]))
                    best_ask = float(sorted_asks[0]["price"])
                    
                    remaining_stake = target_stake_usd
                    total_shares = 0.0
                    total_cost = 0.0
                    
                    for level in sorted_asks:
                        lvl_p = float(level["price"])
                        lvl_s = float(level["size"])
                        lvl_cap = lvl_p * lvl_s
                        
                        if remaining_stake <= 0:
                            break
                        if lvl_cap >= remaining_stake:
                            bought = remaining_stake / lvl_p
                            total_shares += bought
                            total_cost += remaining_stake
                            remaining_stake = 0.0
                            break
                        else:
                            total_shares += lvl_s
                            total_cost += lvl_cap
                            remaining_stake -= lvl_cap
                            
                    if remaining_stake > 0 and total_shares > 0:
                        deepest_p = float(sorted_asks[-1]["price"])
                        added_sh = remaining_stake / deepest_p
                        total_shares += added_sh
                        total_cost += remaining_stake

                    vwap = total_cost / total_shares if total_shares > 0 else best_ask
                    vwap = round(vwap, 4)
                    slippage_pct = round(((vwap - best_ask) / best_ask) * 100, 2) if best_ask > 0 else 0.0
                    depth = sum(float(a["size"]) * float(a["price"]) for a in sorted_asks[:3])
                    
                    return {
                        'best_ask': best_ask,
                        'vwap_ask': vwap,
                        'shares': round(total_shares, 2),
                        'depth': round(depth, 2),
                        'slippage_pct': slippage_pct,
                        'source': 'LIVE_CLOB'
                    }
        except Exception:
            pass

    # Fallback 1: Query most recent snapshot ask in DB for this cycle & asset
    col = "up_best_ask" if direction.lower() == "up" else "down_best_ask"
    dep_col = "up_ask_depth" if direction.lower() == "up" else "down_ask_depth"
    cur.execute(f"""
        SELECT {col}, {dep_col} 
        FROM multi_snapshots 
        WHERE cycle_id = ? AND asset = ? AND {col} IS NOT NULL 
        ORDER BY id DESC LIMIT 1
    """, (cycle_id, asset))
    db_row = cur.fetchone()
    if db_row and db_row[0]:
        db_ask = float(db_row[0])
        db_dep = float(db_row[1] or 10.0)
        shares = round(target_stake_usd / db_ask, 2)
        return {
            'best_ask': db_ask,
            'vwap_ask': db_ask,
            'shares': shares,
            'depth': round(db_dep, 2),
            'slippage_pct': 0.0,
            'source': 'DB_RECENT_SNAPSHOT'
        }

    # Fallback 2: Default empirical baseline
    shares = round(target_stake_usd / fallback_price, 2)
    return {
        'best_ask': fallback_price,
        'vwap_ask': fallback_price,
        'shares': shares,
        'depth': 10.0,
        'slippage_pct': 0.0,
        'source': 'DEFAULT_FALLBACK'
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

    # Deduct open active positions in real time so balance accounts for placed stakes
    cur.execute("SELECT COALESCE(SUM(invested_usd), 0) FROM multi_trades WHERE session_id = ? AND status = 'OPEN'", (CURRENT_SESSION,))
    open_in_play = cur.fetchone()[0] or 0.0
    available_cash = max(0.0, wallet_balance - open_in_play)
    if available_cash < 0.50:
        return

    # Query latest snapshot for each asset with cycle tokens
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

        # Bot C Rule: can trade even with 120 seconds left! (T-120s down to T-15s)
        if remaining > 120 or remaining < 15:
            continue

        cur.execute("SELECT trade_id FROM multi_trades WHERE cycle_id = ? AND asset = ? AND session_id = ?", (cid, asset, CURRENT_SESSION))
        if cur.fetchone():
            continue

        up_safe, dn_safe = get_boundaries_for_asset(asset, remaining)

        # Check UP
        if gap >= up_safe:
            fill = fetch_live_orderbook_fill(up_tok, nominal_stake, 0.86, cur, cid, asset, 'Up')
            ask = fill['vwap_ask']
            if 0.65 <= ask <= 0.95:
                candidates.append({
                    'asset': asset, 'cycle_id': cid, 'direction': 'Up', 'elapsed': elapsed,
                    'remaining': remaining, 'spot': spot, 'strike': strike, 'gap': gap,
                    'ask': ask, 'best_ask': fill['best_ask'], 'depth': fill['depth'],
                    'slippage_pct': fill['slippage_pct'], 'shares': fill['shares'],
                    'source': fill['source'],
                    'rule': f'Bot C Ultra HF UP Gap >= +${up_safe} at T-{remaining}s'
                })

        # Check DOWN
        elif gap <= dn_safe:
            fill = fetch_live_orderbook_fill(dn_tok, nominal_stake, 0.86, cur, cid, asset, 'Down')
            ask = fill['vwap_ask']
            if 0.65 <= ask <= 0.95:
                candidates.append({
                    'asset': asset, 'cycle_id': cid, 'direction': 'Down', 'elapsed': elapsed,
                    'remaining': remaining, 'spot': spot, 'strike': strike, 'gap': gap,
                    'ask': ask, 'best_ask': fill['best_ask'], 'depth': fill['depth'],
                    'slippage_pct': fill['slippage_pct'], 'shares': fill['shares'],
                    'source': fill['source'],
                    'rule': f'Bot C Ultra HF DOWN Gap <= ${dn_safe} at T-{remaining}s'
                })

    if not candidates:
        return

    # Prioritize cheapest ask contract first
    candidates.sort(key=lambda x: x['ask'])

    for cand in candidates:
        stake = round(min(available_cash * STAKE_FRACTION, MAX_STAKE_CEILING), 2)
        if stake < 0.50 or stake > available_cash:
            break

        shares = round(stake / cand['ask'], 2)
        now_ts = int(time.time())
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rule_desc = f"{cand['rule']} | {cand['source']} VWAP {cand['ask']:.2f}c (slip: +{cand['slippage_pct']}%, depth: ${cand['depth']:.2f})"

        with conn:
            conn.execute("""
                INSERT INTO multi_trades 
                (cycle_id, asset, session_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds, spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, rule_triggered, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """, (cand['cycle_id'], cand['asset'], CURRENT_SESSION, now_ts, now_iso, cand['direction'],
                  cand['elapsed'], cand['remaining'], cand['spot'], cand['strike'], cand['gap'], cand['ask'],
                  shares, stake, rule_desc))

        available_cash -= stake
        print(f"\n🚀 [BOT C EXECUTION] {cand['asset']} {cand['direction'].upper()} @ {cand['ask']:.2f}c ({cand['source']} VWAP, slip: +{cand['slippage_pct']}%) | Stake: ${stake:.2f} ({shares} sh) | Gap: {cand['gap']:+,.2f} | T-{cand['remaining']}s | Avail Cash: ${available_cash:.2f}", flush=True)

def main():
    conn = sqlite3.connect(DB_PATH)
    print("==================================================================", flush=True)
    print(f"🚀 MULTI-ASSET BOT C (ULTRA HIGH FREQUENCY - T <= 120s) ACTIVATED (RUN #{CURRENT_SESSION})", flush=True)
    print(f"Database: {DB_PATH}", flush=True)
    bal = get_wallet_balance(conn)
    print(f"Starting Bankroll: ${bal:.2f}", flush=True)
    print(f"Execution Engine: Live CLOB VWAP Depth Slippage + Real-time In-Play Deduction", flush=True)
    print(f"Strategy: High-Frequency Empirical with Extended 120s Window & Cheapest-Ask Priority", flush=True)
    print("==================================================================\n", flush=True)

    last_hb = time.time()

    while True:
        try:
            resolve_settled_trades(conn)
            evaluate_and_trade(conn)

            if time.time() - last_hb > 60:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END) FROM multi_trades WHERE session_id = ? AND status LIKE 'RESOLVED%'", (CURRENT_SESSION,))
                row = cur.fetchone()
                total = row[0] or 0
                wins = row[1] or 0
                rate = (wins / total * 100) if total > 0 else 0
                bal = get_wallet_balance(conn)
                cur.execute("SELECT COALESCE(SUM(invested_usd), 0) FROM multi_trades WHERE session_id = ? AND status = 'OPEN'", (CURRENT_SESSION,))
                open_stake = cur.fetchone()[0] or 0.0
                dt_str = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{dt_str}] BOT C HEARTBEAT | Equity: ${bal:.2f} (In-Play: ${open_stake:.2f}) | Trades: {total} | Wins: {wins} ({rate:.1f}%)", flush=True)
                last_hb = time.time()

            time.sleep(1)

        except Exception as e:
            print(f"[BOT C ERROR] {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    main()
