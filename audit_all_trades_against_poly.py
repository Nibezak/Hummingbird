import sqlite3
import requests
import json
import time

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get all trades in session 3 and session 4
cursor.execute('''
    SELECT trade_id, session_id, cycle_id, direction, invested_usd, shares, entry_price, pnl, is_winner, winning_outcome, status
    FROM dry_run_trades
    WHERE session_id IN (3, 4)
    ORDER BY trade_id ASC
''')
trades = cursor.fetchall()
print(f"Total trades in Session 3 & 4: {len(trades)}")

mismatches = []
for t in trades:
    tid, sess, cid, direction, inv, shares, entry_p, pnl, is_win, db_winner, status = t
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
            poly_winner = None
            if p and len(p) >= 2:
                if float(p[0]) > 0.9: poly_winner = "Up"
                elif float(p[1]) > 0.9: poly_winner = "Down"
            
            if poly_winner:
                # Check if DB winner matches Polymarket winner
                if db_winner and db_winner.lower() != poly_winner.lower():
                    mismatches.append({
                        'trade_id': tid,
                        'session_id': sess,
                        'cycle_id': cid,
                        'direction': direction,
                        'entry_price': entry_p,
                        'invested': inv,
                        'shares': shares,
                        'db_winner': db_winner,
                        'poly_winner': poly_winner,
                        'db_pnl': pnl,
                        'db_is_winner': is_win
                    })
    except Exception as e:
        print(f"Error on trade {tid}: {e}")
    time.sleep(0.05)

print(f"\nTotal Mismatches Found: {len(mismatches)}")
for m in mismatches:
    print(m)

conn.close()
