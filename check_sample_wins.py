import sqlite3
import requests
import json
import random

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT trade_id, session_id, cycle_id, direction, pnl, winning_outcome
    FROM dry_run_trades
    WHERE session_id IN (3, 4) AND is_winner = 1
    ORDER BY RANDOM()
    LIMIT 10
''')
sample_wins = cursor.fetchall()

print("Auditing sample of wins:")
for w in sample_wins:
    tid, sess, cid, direction, pnl, db_winner = w
    slug = f"btc-updown-5m-{cid}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        resp = requests.get(url, timeout=5)
        events = resp.json()
        if events and len(events) > 0:
            m = events[0].get("markets", [])[0]
            prices = m.get("outcomePrices")
            p = json.loads(prices) if isinstance(prices, str) else prices
            poly_winner = "Up" if float(p[0]) > 0.9 else ("Down" if float(p[1]) > 0.9 else "UNKNOWN")
            match = (direction.lower() == poly_winner.lower())
            print(f"Win Trade #{tid:03d} (Cycle {cid}): Bet={direction} | DB={db_winner} | Poly={poly_winner} | Legit Win? {match}")
    except Exception as e:
        print(f"Error {tid}: {e}")

conn.close()
