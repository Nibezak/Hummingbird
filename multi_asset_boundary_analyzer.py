import urllib.request
import json
import time
import datetime
import numpy as np

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

def fetch_1s_klines(symbol, start_ms, end_ms):
    klines = []
    curr = start_ms
    while curr < end_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1s&limit=1000&startTime={curr}&endTime={end_ms}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data:
                    break
                for k in data:
                    # ts, open, high, low, close
                    klines.append((k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4])))
                last_ts = data[-1][0]
                if last_ts <= curr:
                    break
                curr = last_ts + 1000
                time.sleep(0.04) # 25 req/sec well within Binance 1200 weight/min limit
        except Exception as e:
            time.sleep(1)
    return klines

def analyze_reversals(symbol_name, klines):
    # Group klines into 5-minute candles (300 seconds)
    # Each 5-minute block starts at ts % 300_000 == 0
    cycle_map = {}
    for ts, o, h, l, c in klines:
        cid = (ts // 300_000) * 300_000
        sec = (ts - cid) // 1000
        if cid not in cycle_map:
            cycle_map[cid] = {}
        cycle_map[cid][sec] = c

    # Windows to analyze: T-90s (sec 210), T-60s (sec 240), T-45s (sec 255), T-30s (sec 270)
    windows = [90, 60, 45, 30]
    results = {w: {'up_revs': [], 'dn_revs': [], 'up_revs_pct': [], 'dn_revs_pct': []} for w in windows}

    for cid, sec_dict in cycle_map.items():
        if 299 not in sec_dict or 0 not in sec_dict:
            continue
        p0 = sec_dict[0]
        p_final = sec_dict[299]
        
        for w in windows:
            sec = 300 - w
            if sec not in sec_dict:
                continue
            p_call = sec_dict[sec]
            
            # Reversal against an UP lead:
            # If lead was UP (p_call > p0), reversal to loss means p_final <= p0
            # How much did price drop from call to final?
            # Reversal size = p_call - min(p in remaining window)
            rem_prices = [sec_dict[s] for s in range(sec, 300) if s in sec_dict]
            if not rem_prices:
                continue
            min_rem = min(rem_prices)
            max_rem = max(rem_prices)
            
            drop = p_call - min_rem
            surge = max_rem - p_call
            
            results[w]['up_revs'].append(drop)
            results[w]['dn_revs'].append(surge)
            results[w]['up_revs_pct'].append((drop / p_call) * 100)
            results[w]['dn_revs_pct'].append((surge / p_call) * 100)

    stats = {}
    sample_price = klines[-1][4]
    for w in windows:
        up_98 = np.percentile(results[w]['up_revs'], 98)
        up_99 = np.percentile(results[w]['up_revs'], 99)
        dn_98 = np.percentile(results[w]['dn_revs'], 98)
        dn_99 = np.percentile(results[w]['dn_revs'], 99)
        
        up_pct_99 = np.percentile(results[w]['up_revs_pct'], 99)
        dn_pct_99 = np.percentile(results[w]['dn_revs_pct'], 99)
        
        # Golden boundary (+15% safety buffer)
        golden_up = round(up_99 * 1.15, 4 if sample_price < 10 else 2)
        golden_dn = round(-dn_99 * 1.15, 4 if sample_price < 10 else 2)
        
        # Empirical HF boundary (+5% safety buffer)
        hf_up = round(up_99 * 1.05, 4 if sample_price < 10 else 2)
        hf_dn = round(-dn_99 * 1.05, 4 if sample_price < 10 else 2)

        stats[w] = {
            'p99_up': up_99,
            'p99_dn': dn_99,
            'p99_up_pct': up_pct_99,
            'p99_dn_pct': dn_pct_99,
            'golden_up': golden_up,
            'golden_dn': golden_dn,
            'hf_up': hf_up,
            'hf_dn': hf_dn,
        }
    return stats, len(cycle_map), sample_price

def main():
    end_ms = int(time.time() * 1000)
    # Pull 3 full days (72 hours) of 1-second candles
    start_ms = end_ms - (72 * 3600 * 1000)
    
    print(f"Starting 72-Hour Multi-Asset 1-Second Analysis from {datetime.datetime.fromtimestamp(start_ms/1000, datetime.timezone.utc)} to {datetime.datetime.fromtimestamp(end_ms/1000, datetime.timezone.utc)}...\n")
    
    all_summary = {}

    for name, sym in SYMBOLS.items():
        print(f"Fetching 1s klines for {name} ({sym})...")
        t0 = time.time()
        klines = fetch_1s_klines(sym, start_ms, end_ms)
        elapsed = time.time() - t0
        print(f"  Downloaded {len(klines):,} 1s candles for {name} in {elapsed:.1f}s.")
        
        if len(klines) < 1000:
            print(f"  Warning: insufficient data for {name}")
            continue
            
        stats, cycles, price = analyze_reversals(name, klines)
        all_summary[name] = {'price': price, 'cycles': cycles, 'stats': stats}
        print(f"  Analyzed {cycles} cycles. Current price: ${price:,.4f}")
        print(f"  T-60s Safe Boundaries -> Golden (Bot A): +${stats[60]['golden_up']} / {stats[60]['golden_dn']} | HF (Bot B): +${stats[60]['hf_up']} / {stats[60]['hf_dn']}")
        print(f"  T-30s Safe Boundaries -> Golden (Bot A): +${stats[30]['golden_up']} / {stats[30]['golden_dn']} | HF (Bot B): +${stats[30]['hf_up']} / {stats[30]['hf_dn']}\n")

    # Save to JSON config file
    out_path = r"c:\projects\btc-5m-recorder\multi_asset_safe_boundaries.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_summary, f, indent=2)
    print(f"\nSaved multi-asset boundaries to: {out_path}")

if __name__ == '__main__':
    main()
