import requests
import json
import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Missing cycles: 1795427400 through 1795434000 in steps of 300
missing_cids = list(range(1795427400, 1795434300, 300))
print(f"Total missing cycles to check: {len(missing_cids)}")

# Active boundaries
cursor.execute("SELECT * FROM adaptive_safe_boundaries")
boundaries = cursor.fetchall()
print("Current active safe boundaries:")
for b in boundaries:
    print(b)

# Fetch Binance 5m klines for this period
# start_time = 1795427400 * 1000, end_time = 1795434300 * 1000
url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={missing_cids[0]*1000}&endTime={missing_cids[-1]*1000 + 300000}&limit=50"
try:
    resp = requests.get(url, timeout=10)
    klines = resp.json()
except Exception as e:
    print("Error fetching Binance klines:", e)
    klines = []

print(f"Fetched {len(klines)} klines from Binance")

# Map klines by timestamp (open_time in s)
kline_map = {}
for k in klines:
    k_ts = k[0] // 1000
    kline_map[k_ts] = {
        'open': float(k[1]),
        'high': float(k[2]),
        'low': float(k[3]),
        'close': float(k[4]),
        'volume': float(k[5])
    }

# For each missing cycle, query Polymarket API
downtime_analysis = []

for cid in missing_cids:
    slug = f"btc-updown-5m-{cid}"
    p_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    poly_winner = None
    poly_closed = False
    m_data = {}
    try:
        p_resp = requests.get(p_url, timeout=5)
        p_json = p_resp.json()
        if p_json and len(p_json) > 0:
            m = p_json[0].get("markets", [])[0]
            poly_closed = m.get("closed", False)
            prices = m.get("outcomePrices")
            p = json.loads(prices) if isinstance(prices, str) else prices
            if p and len(p) >= 2:
                if float(p[0]) > 0.9: poly_winner = "Up"
                elif float(p[1]) > 0.9: poly_winner = "Down"
            m_data = m
    except Exception as e:
        print(f"Error fetching Polymarket for {cid}: {e}")
    
    k = kline_map.get(cid, {})
    k_open = k.get('open')
    k_close = k.get('close')
    k_high = k.get('high')
    k_low = k.get('low')
    
    max_pos = (k_high - k_open) if (k_high and k_open) else 0.0
    max_neg = (k_low - k_open) if (k_low and k_open) else 0.0
    net_move = (k_close - k_open) if (k_close and k_open) else 0.0
    
    dt = datetime.datetime.fromtimestamp(cid, tz=datetime.timezone.utc)
    dt_eat = dt + datetime.timedelta(hours=3)
    
    downtime_analysis.append({
        'cid': cid,
        'time_eat': dt_eat.strftime('%H:%M'),
        'open': k_open,
        'high': k_high,
        'low': k_low,
        'close': k_close,
        'max_pos': max_pos,
        'max_neg': max_neg,
        'net_move': net_move,
        'poly_winner': poly_winner
    })

print("\n--- DOWNTIME CYCLES AUDIT ---")
print("CID        | Time EAT | Open ($)   | Max +Gap | Max -Gap | Net Move | Poly Winner | Eligible Trade?")
qualifying_trades = []
for d in downtime_analysis:
    # Check if max gap exceeded minimum trigger threshold (Bot B min threshold is ~$59 at T-60s, ~$45 at T-45s, ~$32 at T-30s)
    # Let's see if the candle had significant directional move
    is_qualifying = False
    qual_reason = "No gap threshold met (Dead zone chop)"
    direction = None
    
    # In European lunch lull, let's see how big the moves were:
    if d['max_pos'] >= 95.9 or d['max_neg'] <= -82.2:
        is_qualifying = True
        direction = "Up" if d['max_pos'] >= 95.9 else "Down"
        qual_reason = f"High volatility move ({direction})"
    elif d['max_pos'] >= 77.6 or d['max_neg'] <= -68.5:
        is_qualifying = True
        direction = "Up" if d['max_pos'] >= 77.6 else "Down"
        qual_reason = f"Moderate move ({direction})"
        
    print(f"{d['cid']} | {d['time_eat']}    | ${d['open'] or 0:,.2f} | +${d['max_pos']:<6.1f} | -${abs(d['max_neg']):<6.1f} | ${d['net_move']:<+7.1f} | {d['poly_winner'] or 'N/A':<11} | {'YES - ' + direction if is_qualifying else 'NO (Dead Zone)'}")
    
    if is_qualifying:
        qualifying_trades.append((d, direction))

print(f"\nTotal Qualifying Candles during downtime: {len(qualifying_trades)}")
for q, d in qualifying_trades:
    print(f"Cycle {q['cid']} ({q['time_eat']} EAT): Direction={d}, Poly Winner={q['poly_winner']}, Match? {d.lower() == (q['poly_winner'] or '').lower()}")

conn.close()
