import requests
import json
import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

missing_cids = list(range(1795427400, 1795434300, 300))
print(f"Backfilling {len(missing_cids)} cycles into cycles table...")

url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={missing_cids[0]*1000}&endTime={missing_cids[-1]*1000 + 300000}&limit=50"
klines = requests.get(url, timeout=10).json()
kline_map = {k[0]//1000: {'open': float(k[1]), 'high': float(k[2]), 'low': float(k[3]), 'close': float(k[4])} for k in klines}

backfilled_count = 0
for cid in missing_cids:
    # check if already exists
    cursor.execute("SELECT cycle_id FROM cycles WHERE cycle_id = ?", (cid,))
    if cursor.fetchone():
        continue
    
    slug = f"btc-updown-5m-{cid}"
    p_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    poly_winner = None
    up_token, down_token, cond_id = None, None, None
    title = f"Bitcoin Up or Down 5m ({cid})"
    try:
        p_resp = requests.get(p_url, timeout=5)
        p_json = p_resp.json()
        if p_json and len(p_json) > 0:
            ev = p_json[0]
            title = ev.get("title", title)
            m = ev.get("markets", [])[0]
            cond_id = m.get("conditionId")
            clob_tokens = m.get("clobTokenIds")
            if isinstance(clob_tokens, str):
                clob_tokens = json.loads(clob_tokens)
            up_token = clob_tokens[0] if len(clob_tokens) > 0 else None
            down_token = clob_tokens[1] if len(clob_tokens) > 1 else None
            prices = m.get("outcomePrices")
            p = json.loads(prices) if isinstance(prices, str) else prices
            if p and len(p) >= 2:
                if float(p[0]) > 0.9: poly_winner = "Up"
                elif float(p[1]) > 0.9: poly_winner = "Down"
    except Exception as e:
        print(f"Error fetching Polymarket for {cid}: {e}")

    k = kline_map.get(cid, {})
    strike = k.get('open')
    final_p = k.get('close')
    max_pos = (k.get('high') - strike) if (k.get('high') and strike) else 0.0
    max_neg = (k.get('low') - strike) if (k.get('low') and strike) else 0.0
    
    start_iso = datetime.datetime.fromtimestamp(cid, tz=datetime.timezone.utc).isoformat()
    end_iso = datetime.datetime.fromtimestamp(cid + 300, tz=datetime.timezone.utc).isoformat()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO cycles 
        (cycle_id, slug, title, start_time, end_time, strike_price, final_price, winning_outcome, 
         up_token_id, down_token_id, condition_id, max_positive_gap, max_negative_gap, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESOLVED', ?, ?)
    """, (cid, slug, title, start_iso, end_iso, strike, final_p, poly_winner,
          up_token, down_token, cond_id, max_pos, max_neg, now_iso, now_iso))
    backfilled_count += 1

conn.commit()
print(f"Successfully backfilled {backfilled_count} missing cycles into cycles table!")

cursor.execute("SELECT COUNT(*) FROM cycles")
print(f"Total cycles in DB now: {cursor.fetchone()[0]}")

conn.close()
