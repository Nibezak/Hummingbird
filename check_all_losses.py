import sqlite3
import requests
import json
import time

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get all trades marked as loss or pnl < 0
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, direction, entry_price, invested_usd, pnl, winning_outcome
    FROM dry_run_trades
    WHERE is_winner = 0 OR pnl < 0
    ORDER BY trade_id ASC
''')
losses = cursor.fetchall()
print(f"Total recorded losses in DB: {len(losses)}")

for l in losses:
    tid, sess, cid, ct, direction, entry_p, inv, pnl, recorded_winner = l
    slug = f"btc-updown-5m-{cid}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        resp = requests.get(url, timeout=10)
        events = resp.json()
        if events and len(events) > 0:
            m = events[0].get("markets", [])[0]
            closed = m.get("closed")
            prices = m.get("outcomePrices")
            p = json.loads(prices) if isinstance(prices, str) else prices
            poly_winner = "UNKNOWN"
            if p and len(p) >= 2:
                if float(p[0]) > 0.9: poly_winner = "Up"
                elif float(p[1]) > 0.9: poly_winner = "Down"
            
            # Did our direction match Polymarket official winner?
            actually_won = (direction.lower() == poly_winner.lower())
            print(f"Trade #{tid:03d} (Sess {sess}, Cycle {cid}): Bot Bet={direction.upper()} | DB Winner={recorded_winner} | Poly Winner={poly_winner} | Actually Won on Poly? {actually_won} | PnL in DB: ${pnl}")
        else:
            print(f"Trade #{tid:03d} (Cycle {cid}): No event found on Polymarket")
    except Exception as e:
        print(f"Trade #{tid:03d} Error: {e}")
    time.sleep(0.2)

conn.close()
