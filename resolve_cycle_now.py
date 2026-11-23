import sqlite3
import requests
import json
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Trigger resolution on cycle 1795442400
cid = 1795442400
cursor.execute("SELECT strike_price FROM cycles WHERE cycle_id = ?", (cid,))
strike = cursor.fetchone()[0]

# Check Polymarket
slug = f"btc-updown-5m-{cid}"
p_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
resp = requests.get(p_url, timeout=5).json()
prices = resp[0]['markets'][0]['outcomePrices']
p = json.loads(prices) if isinstance(prices, str) else prices
print("Polymarket outcome prices:", p)

winner = "Down" if float(p[1]) > 0.9 else ("Up" if float(p[0]) > 0.9 else None)
print("Detected Winner:", winner)

now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
if winner:
    cursor.execute("""
        UPDATE cycles
        SET winning_outcome = ?, status = 'RESOLVED', updated_at = ?
        WHERE cycle_id = ?
    """, (winner, now_iso, cid))
    conn.commit()
    print(f"Cycle {cid} set to RESOLVED with winner {winner}!")

conn.close()
