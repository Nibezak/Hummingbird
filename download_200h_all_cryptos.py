import urllib.request
import json
import time
import datetime
import sqlite3
import os
import sys
import numpy as np

DB_PATH = r"c:\projects\btc-5m-recorder\historical_200h_1s.db"
JSON_OUT_PATH = r"c:\projects\btc-5m-recorder\multi_asset_safe_boundaries.json"

SYMBOLS = {
    'BTC': 'BTCUSDT',
    'ETH': 'ETHUSDT',
    'SOL': 'SOLUSDT',
    'DOGE': 'DOGEUSDT',
    'XRP': 'XRPUSDT',
    'BNB': 'BNBUSDT',
    'HYPE': 'HYPEUSDT'
}

HEADERS = {'User-Agent': 'Mozilla/5.0'}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS klines_1s (
                symbol TEXT,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sym_ts ON klines_1s(symbol, timestamp)")
    return conn

def get_latest_stored_ts(conn, symbol):
    cur = conn.cursor()
    cur.execute("SELECT MAX(timestamp) FROM klines_1s WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    return row[0] if row and row[0] else None

def download_200h_for_symbol(conn, symbol, sym_code, total_hours=200):
    now_ms = int(time.time() * 1000)
    target_start_ms = now_ms - (total_hours * 3600 * 1000)
    
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM klines_1s WHERE symbol = ?", (symbol,))
    existing_count, min_ts, max_ts = cur.fetchone()
    
    expected_rows = total_hours * 3600
    if existing_count >= expected_rows * 0.95:
        print(f"[{symbol}] Already have {existing_count:,} 1s rows in database. Skipping download.", flush=True)
        return
    
    curr = target_start_ms
    batch = []
    fetched = 0
    start_t = time.time()
    
    print(f"[{symbol}] Starting 200-hour download ({expected_rows:,} candles) from {datetime.datetime.fromtimestamp(target_start_ms/1000, datetime.timezone.utc)}...", flush=True)
    
    while curr < now_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym_code}&interval=1s&limit=1000&startTime={curr}&endTime={now_ms}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                used_weight = int(resp.headers.get('x-mbx-used-weight-1m', '100'))
                data = json.loads(resp.read().decode('utf-8'))
                
                if not data:
                    break
                    
                for k in data:
                    ts = int(k[0])
                    o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
                    batch.append((symbol, ts, o, h, l, c))
                    fetched += 1
                
                curr = int(data[-1][0]) + 1000
                
                if len(batch) >= 10000:
                    with conn:
                        conn.executemany("INSERT OR IGNORE INTO klines_1s VALUES (?, ?, ?, ?, ?, ?)", batch)
                    batch = []
                    pct = (fetched / expected_rows) * 100
                    el = time.time() - start_t
                    rate = fetched / el if el > 0 else 0
                    print(f"  [{symbol}] {fetched:,} / {expected_rows:,} ({pct:.1f}%) | Speed: {rate:,.0f} ticks/s | Binance Weight: {used_weight}/1200", flush=True)
                
                # Dynamic rate limiter
                if used_weight > 1000:
                    time.sleep(2.0)
                else:
                    time.sleep(0.05)
                    
        except Exception as e:
            time.sleep(2.0)
            
    if batch:
        with conn:
            conn.executemany("INSERT OR IGNORE INTO klines_1s VALUES (?, ?, ?, ?, ?, ?)", batch)
            
    total_time = time.time() - start_t
    print(f"[{symbol}] Finished download: {fetched:,} rows saved in {total_time:.1f}s.\n", flush=True)

def compute_boundaries(conn, symbol):
    cur = conn.cursor()
    cur.execute("SELECT timestamp, close FROM klines_1s WHERE symbol = ? ORDER BY timestamp ASC", (symbol,))
    rows = cur.fetchall()
    
    if not rows:
        return None
        
    latest_price = rows[-1][1]
    
    # Organize into 5m cycles (300 seconds)
    cycles = {}
    for ts, c in rows:
        cid = (ts // 300_000) * 300_000
        sec = (ts - cid) // 1000
        if cid not in cycles:
            cycles[cid] = {}
        cycles[cid][sec] = c
        
    windows = [90, 60, 45, 30]
    rev_data = {w: {'up_revs': [], 'dn_revs': []} for w in windows}
    
    for cid, sec_dict in cycles.items():
        if 299 not in sec_dict or 0 not in sec_dict:
            continue
        p0 = sec_dict[0]
        
        for w in windows:
            sec = 300 - w
            if sec not in sec_dict:
                continue
            p_call = sec_dict[sec]
            
            rem_prices = [sec_dict[s] for s in range(sec, 300) if s in sec_dict]
            if not rem_prices:
                continue
                
            drop = p_call - min(rem_prices)
            surge = max(rem_prices) - p_call
            
            rev_data[w]['up_revs'].append(drop)
            rev_data[w]['dn_revs'].append(surge)
            
    stats = {}
    is_small_coin = latest_price < 10.0
    decimals = 4 if is_small_coin else 2
    
    for w in windows:
        if not rev_data[w]['up_revs']:
            continue
        up_98 = float(np.percentile(rev_data[w]['up_revs'], 98))
        up_99 = float(np.percentile(rev_data[w]['up_revs'], 99))
        dn_98 = float(np.percentile(rev_data[w]['dn_revs'], 98))
        dn_99 = float(np.percentile(rev_data[w]['dn_revs'], 99))
        
        # Golden boundary (+15% safety buffer for Bot A)
        golden_up = round(up_99 * 1.15, decimals)
        golden_dn = round(-dn_99 * 1.15, decimals)
        
        # Empirical HF boundary (+5% safety buffer for Bot B)
        hf_up = round(up_99 * 1.05, decimals)
        hf_dn = round(-dn_99 * 1.05, decimals)
        
        stats[w] = {
            'p98_up': round(up_98, decimals),
            'p99_up': round(up_99, decimals),
            'p98_dn': round(-dn_98, decimals),
            'p99_dn': round(-dn_99, decimals),
            'golden_up': golden_up,
            'golden_dn': golden_dn,
            'hf_up': hf_up,
            'hf_dn': hf_dn
        }
        
    return {
        'symbol': symbol,
        'current_price': latest_price,
        'total_cycles_analyzed': len(cycles),
        'total_ticks': len(rows),
        'windows': stats
    }

def main():
    print(f"==================================================================", flush=True)
    print(f"🚀 MULTI-ASSET 200-HOUR 1-SECOND HISTORICAL REPLAY & CALIBRATION", flush=True)
    print(f"📁 Target SQLite DB: {DB_PATH}", flush=True)
    print(f"🪙 Assets: {', '.join(SYMBOLS.keys())}", flush=True)
    print(f"==================================================================\n", flush=True)
    
    conn = init_db()
    
    for sym, sym_code in SYMBOLS.items():
        download_200h_for_symbol(conn, sym, sym_code, total_hours=200)
        
    print("\n" + "=" * 66, flush=True)
    print("📊 COMPUTING 200-HOUR EMPIRICAL SAFE BOUNDARIES FOR ALL 7 ASSETS...", flush=True)
    print("=" * 66 + "\n", flush=True)
    
    final_config = {}
    for sym in SYMBOLS.keys():
        res = compute_boundaries(conn, sym)
        if res:
            final_config[sym] = res
            w60 = res['windows'].get(60, {})
            w30 = res['windows'].get(30, {})
            print(f"[{sym}] (Price: ${res['current_price']:,.4f} | {res['total_cycles_analyzed']:,} Cycles | {res['total_ticks']:,} Ticks):", flush=True)
            print(f"  T-60s Safe Boundaries -> Bot A (Golden): +${w60.get('golden_up')} / {w60.get('golden_dn')} | Bot B (HF): +${w60.get('hf_up')} / {w60.get('hf_dn')}", flush=True)
            print(f"  T-30s Safe Boundaries -> Bot A (Golden): +${w30.get('golden_up')} / {w30.get('golden_dn')} | Bot B (HF): +${w30.get('hf_up')} / {w30.get('hf_dn')}\n", flush=True)
            
    with open(JSON_OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_config, f, indent=2)
        
    print(f"✅ Calibration complete! Multi-asset safe boundaries saved to: {JSON_OUT_PATH}", flush=True)
    conn.close()

if __name__ == '__main__':
    main()
