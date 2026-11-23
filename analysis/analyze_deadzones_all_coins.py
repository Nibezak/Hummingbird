import sqlite3
import datetime
import numpy as np

DB_PATH = r"c:\projects\btc-5m-recorder\historical_200h_1s.db"

def analyze_coin_deadzones(symbol):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, close FROM klines_1s WHERE symbol = ? ORDER BY timestamp ASC", (symbol,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return None
        
    latest_price = rows[-1][1]
    
    # Organize into 5-minute cycles: cid -> {sec: price}
    cycles = {}
    for ts, c in rows:
        cid = (ts // 300_000) * 300_000
        sec = (ts - cid) // 1000
        if cid not in cycles:
            cycles[cid] = {}
        cycles[cid][sec] = c
        
    # Group by UTC hour: hour (0..23) -> list of 60s reversals (in %)
    hourly_reversals_pct = {h: [] for h in range(24)}
    
    for cid, sec_dict in cycles.items():
        if 240 not in sec_dict or 299 not in sec_dict:
            continue
        p_call = sec_dict[240] # T-60s price
        rem_prices = [sec_dict[s] for s in range(240, 300) if s in sec_dict]
        if not rem_prices or p_call <= 0:
            continue
            
        max_rem = max(rem_prices)
        min_rem = min(rem_prices)
        
        # Max move against a position in the final 60s (as % of price)
        max_move = max(max_rem - p_call, p_call - min_rem)
        max_move_pct = (max_move / p_call) * 100
        
        utc_hour = (cid // 3600_000) % 24
        hourly_reversals_pct[utc_hour].append(max_move_pct)
        
    # Compute stats per hour
    hour_stats = {}
    for h in range(24):
        vals = hourly_reversals_pct[h]
        if not vals:
            continue
        eat_hour = (h + 3) % 24
        p95 = np.percentile(vals, 95)
        p99 = np.percentile(vals, 99)
        avg = np.mean(vals)
        extreme_cnt = sum(1 for v in vals if v >= 0.25)
        extreme_pct = (extreme_cnt / len(vals)) * 100
        
        hour_stats[h] = {
            'utc_hour': h,
            'eat_hour': eat_hour,
            'sample_count': len(vals),
            'avg_pct': avg,
            'p95_pct': p95,
            'p99_pct': p99,
            'extreme_rate_pct': extreme_pct
        }
        
    return symbol, latest_price, len(cycles), hour_stats

def main():
    symbols = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
    print(f"==================================================================", flush=True)
    print(f"🔍 200-HOUR HOURLY DEADZONE & VOLATILITY SPIKE ANALYSIS", flush=True)
    print(f"==================================================================\n", flush=True)
    
    danger_hours_all = {}
    
    for sym in symbols:
        res = analyze_coin_deadzones(sym)
        if not res:
            continue
        sym, price, total_c, stats = res
        print(f"--- {sym} (Price: ${price:,.4f} | Analyzed {total_c:,} Cycles) ---", flush=True)
        
        # Sort hours by 99th percentile volatility spike
        sorted_by_spike = sorted(stats.values(), key=lambda x: x['p99_pct'], reverse=True)
        top_danger = sorted_by_spike[:3]
        danger_hours_all[sym] = [x['utc_hour'] for x in top_danger]
        
        print("  Top 3 Most Dangerous Volatile Hours:")
        for rank, d in enumerate(top_danger, 1):
            h_utc = f"{d['utc_hour']:02d}:00 UTC"
            h_eat = f"{d['eat_hour']:02d}:00 EAT"
            print(f"    #{rank} {h_utc} ({h_eat}) -> 99th Pct Spike: {d['p99_pct']:.3f}% | Avg: {d['avg_pct']:.3f}% | Extreme Spikes: {d['extreme_rate_pct']:.1f}%", flush=True)
        
        # Safest hours
        safest = sorted(stats.values(), key=lambda x: x['p99_pct'])[:2]
        print("  Top 2 Safest Hours (Lowest Volatility Runway):")
        for rank, s in enumerate(safest, 1):
            h_utc = f"{s['utc_hour']:02d}:00 UTC"
            h_eat = f"{s['eat_hour']:02d}:00 EAT"
            print(f"    #{rank} {h_utc} ({h_eat}) -> 99th Pct Spike: {s['p99_pct']:.3f}%", flush=True)
        print("", flush=True)

if __name__ == '__main__':
    main()
