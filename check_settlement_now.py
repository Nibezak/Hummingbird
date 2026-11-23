import requests
import json
import sqlite3

cycle_ts = 1795446600
slug = f"btc-updown-5m-{cycle_ts}"
url = f"https://gamma-api.polymarket.com/events?slug={slug}"

try:
    resp = requests.get(url, timeout=5)
    data = resp.json()
    if data and len(data) > 0:
        m = data[0].get("markets", [])[0]
        print("Market Question:", m.get("question"))
        print("Closed:", m.get("closed"))
        print("Outcome Prices:", m.get("outcomePrices"))
        prices = m.get("outcomePrices")
        p = json.loads(prices) if isinstance(prices, str) else prices
        if p and len(p) >= 2:
            if float(p[0]) > 0.9: print("Official Winner: UP")
            elif float(p[1]) > 0.9: print("Official Winner: DOWN")
            else: print("Still finalizing... prices:", p)
except Exception as e:
    print("Error:", e)

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()
cursor.execute("SELECT cycle_id, winning_outcome, status, final_price FROM cycles WHERE cycle_id = ?", (cycle_ts,))
print("DB Cycle status:", cursor.fetchone())

cursor.execute("SELECT trade_id, session_id, direction, pnl, is_winner, status FROM dry_run_trades WHERE cycle_id = ?", (cycle_ts,))
print("DB Trades status:", cursor.fetchall())

cursor.execute("SELECT id, session_id, balance FROM wallet")
print("Wallets:", cursor.fetchall())
conn.close()
