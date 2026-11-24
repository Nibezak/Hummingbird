import urllib.request
import urllib.error
import json
import time
import datetime
import sqlite3
import concurrent.futures

DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

ASSETS = {
    'BTC': 'BTCUSDT',
    'ETH': 'ETHUSDT',
    'SOL': 'SOLUSDT',
    'DOGE': 'DOGEUSDT',
    'XRP': 'XRPUSDT',
    'BNB': 'BNBUSDT',
    'HYPE': 'HYPEUSDT'
}

def http_get_json(url, timeout=3):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

def fetch_all_binance_prices():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = http_get_json(url, timeout=3)
    if not data:
        return {}
    price_map = {}
    for d in data:
        sym = d.get('symbol')
        if sym in ASSETS.values():
            price_map[sym] = float(d['price'])
    return price_map

def fetch_polymarket_market_info(asset, cycle_ts):
    slug = f"{asset.lower()}-updown-5m-{cycle_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    data = http_get_json(url, timeout=4)
    if not data or len(data) == 0:
        return None
    ev = data[0]
    markets = ev.get("markets", [])
    if not markets:
        return None
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
        "title": ev.get("title", f"{asset} Up or Down 5m"),
        "up_token_id": up_token,
        "down_token_id": down_token,
        "condition_id": m.get("conditionId"),
        "closed": m.get("closed", False),
        "outcomePrices": m.get("outcomePrices")
    }

def fetch_orderbook(token_id):
    if not token_id:
        return {"best_bid": None, "best_ask": None, "ask_depth": 0.0, "bid_depth": 0.0}
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    book = http_get_json(url, timeout=2)
    if not book:
        return {"best_bid": None, "best_ask": None, "ask_depth": 0.0, "bid_depth": 0.0}
    bids = book.get("bids", [])
    asks = book.get("asks", [])
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

def get_or_create_cycle(conn, asset, cycle_ts, current_spot):
    cur = conn.cursor()
    cur.execute("SELECT strike_price, up_token_id, down_token_id, status FROM multi_cycles WHERE cycle_id = ? AND asset = ?", (cycle_ts, asset))
    row = cur.fetchone()
    if row and row[1] and row[2]:
        return row[0], row[1], row[2], row[3]
        
    m_info = fetch_polymarket_market_info(asset, cycle_ts)
    slug = m_info.get("slug") if m_info else f"{asset.lower()}-updown-5m-{cycle_ts}"
    title = m_info.get("title") if m_info else f"{asset} Up or Down 5m"
    up_token = m_info.get("up_token_id") if m_info else (row[1] if row else None)
    down_token = m_info.get("down_token_id") if m_info else (row[2] if row else None)
    cond_id = m_info.get("condition_id") if m_info else None
    
    start_iso = datetime.datetime.fromtimestamp(cycle_ts, datetime.timezone.utc).isoformat()
    end_iso = datetime.datetime.fromtimestamp(cycle_ts + 300, datetime.timezone.utc).isoformat()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    strike_price = row[0] if (row and row[0]) else current_spot
    
    with conn:
        conn.execute("""
            INSERT OR IGNORE INTO multi_cycles 
            (cycle_id, asset, slug, title, start_time, end_time, strike_price, up_token_id, down_token_id, condition_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cycle_ts, asset, slug, title, start_iso, end_iso, strike_price, up_token, down_token, cond_id, now_iso, now_iso))
        if row and (up_token or down_token):
            conn.execute("""
                UPDATE multi_cycles 
                SET up_token_id = COALESCE(up_token_id, ?),
                    down_token_id = COALESCE(down_token_id, ?),
                    condition_id = COALESCE(condition_id, ?),
                    updated_at = ?
                WHERE cycle_id = ? AND asset = ?
            """, (up_token, down_token, cond_id, now_iso, cycle_ts, asset))
        
    return strike_price, up_token, down_token, "ACTIVE"

def check_and_finalize_pending_cycles(conn):
    now_ts = int(time.time())
    cur = conn.cursor()
    cur.execute("""
        SELECT cycle_id, asset, slug, strike_price
        FROM multi_cycles
        WHERE status = 'ACTIVE' AND ? >= (cycle_id + 300)
    """, (now_ts,))
    pending = cur.fetchall()
    
    for cid, asset, slug, strike in pending:
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        data = http_get_json(url, timeout=3)
        if not data or len(data) == 0:
            continue
        m = data[0].get("markets", [{}])[0]
        is_closed = m.get("closed", False)
        res_status = m.get("resolutionStatus")
        outcome_prices = m.get("outcomePrices")
        
        # Strictly require official market resolution (closed=True or resolutionStatus='resolved')
        if (is_closed or res_status == 'resolved') and outcome_prices:
            try:
                if isinstance(outcome_prices, str):
                    outcome_prices = json.loads(outcome_prices)
                p_up = float(outcome_prices[0])
                p_down = float(outcome_prices[1])
                winner = None
                if p_up >= 0.95:
                    winner = "Up"
                elif p_down >= 0.95:
                    winner = "Down"
                    
                if winner:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    cur.execute("SELECT spot_price FROM multi_snapshots WHERE cycle_id = ? AND asset = ? ORDER BY id DESC LIMIT 1", (cid, asset))
                    last_snap = cur.fetchone()
                    final_spot = last_snap[0] if last_snap else strike
                    
                    with conn:
                        conn.execute("""
                            UPDATE multi_cycles
                            SET status = 'RESOLVED', winning_outcome = ?, final_price = ?, updated_at = ?
                            WHERE cycle_id = ? AND asset = ?
                        """, (winner, final_spot, now_iso, cid, asset))
                    print(f"🏁 [CYCLE RESOLVED] {asset} Cycle {cid} -> Settled {winner} (Strike: ${strike:,.2f})", flush=True)
            except Exception:
                pass

def record_multi_loop():
    conn = sqlite3.connect(DB_PATH)
    print("==================================================================", flush=True)
    print("🌐 MULTI-ASSET 7-CRYPTO POLYMARKET RECORDER ACTIVATED", flush=True)
    print(f"📁 Database: {DB_PATH}", flush=True)
    print(f"🪙 Assets: {', '.join(ASSETS.keys())}", flush=True)
    print("==================================================================", flush=True)
    
    last_sec = -1
    cycle_token_cache = {}
    
    while True:
        try:
            now_t = time.time()
            now_int = int(now_t)
            
            if now_int == last_sec:
                time.sleep(0.1)
                continue
            last_sec = now_int
            
            cycle_ts = (now_int // 300) * 300
            elapsed = now_int - cycle_ts
            remaining = 300 - elapsed
            
            # 1. Fetch all Binance spot prices in 1 single API call
            price_map = fetch_all_binance_prices()
            if not price_map:
                time.sleep(0.5)
                continue
                
            # 2. Process each of the 7 assets
            snap_batch = []
            
            for asset, sym_code in ASSETS.items():
                spot = price_map.get(sym_code)
                if not spot:
                    continue
                    
                cache_key = (asset, cycle_ts)
                if cache_key not in cycle_token_cache:
                    strike, up_tok, dn_tok, st = get_or_create_cycle(conn, asset, cycle_ts, spot)
                    cycle_token_cache[cache_key] = (strike, up_tok, dn_tok)
                else:
                    strike, up_tok, dn_tok = cycle_token_cache[cache_key]
                    
                gap = round(spot - strike, 4 if spot < 10 else 2)
                gap_pct = round((gap / strike) * 100, 3) if strike > 0 else 0.0
                
                up_ask, up_dep, dn_ask, dn_dep = None, 0.0, None, 0.0
                
                # Fetch books during critical trading window (T-120s to T-15s)
                if 15 <= remaining <= 120 and (elapsed % 3 == 0):
                    if gap > 0 and up_tok:
                        bk = fetch_orderbook(up_tok)
                        up_ask = bk["best_ask"]
                        up_dep = bk["ask_depth"]
                    elif gap < 0 and dn_tok:
                        bk = fetch_orderbook(dn_tok)
                        dn_ask = bk["best_ask"]
                        dn_dep = bk["ask_depth"]
                        
                snap_batch.append((
                    cycle_ts, asset, now_int, elapsed, remaining, spot, gap, gap_pct,
                    up_ask, up_dep, dn_ask, dn_dep
                ))
                
            if snap_batch:
                with conn:
                    conn.executemany("""
                        INSERT INTO multi_snapshots 
                        (cycle_id, asset, timestamp, elapsed_seconds, remaining_seconds, spot_price, gap_dollars, gap_pct, up_best_ask, up_ask_depth, down_best_ask, down_ask_depth)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, snap_batch)
                    
            # Heartbeat print every 30 seconds
            if elapsed % 30 == 0:
                dt_str = datetime.datetime.now().strftime("%H:%M:%S")
                sample_btc = price_map.get('BTCUSDT', 0)
                sample_eth = price_map.get('ETHUSDT', 0)
                sample_sol = price_map.get('SOLUSDT', 0)
                print(f"[RECORDER {dt_str} | T-{remaining}s] Recorded 7 Assets | BTC: ${sample_btc:,.0f} | ETH: ${sample_eth:,.1f} | SOL: ${sample_sol:,.2f}", flush=True)
                
            # Check for cycle settlements every 15 seconds
            if elapsed % 15 == 0:
                check_and_finalize_pending_cycles(conn)
                
        except Exception as e:
            time.sleep(1)

if __name__ == '__main__':
    record_multi_loop()
