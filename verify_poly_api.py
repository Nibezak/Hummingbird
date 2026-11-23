import requests
import json

cycle_ts = 1795350300
slug = f"btc-updown-5m-{cycle_ts}"
url = f"https://gamma-api.polymarket.com/events?slug={slug}"

print(f"Fetching {url}...")
try:
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if data and len(data) > 0:
        event = data[0]
        print("Event title:", event.get("title"))
        markets = event.get("markets", [])
        for m in markets:
            print("Market question:", m.get("question"))
            print("Closed:", m.get("closed"))
            print("Outcome prices:", m.get("outcomePrices"))
            print("Clob token ids:", m.get("clobTokenIds"))
            print("Resolution source:", m.get("resolutionSource"))
            print("Winning outcome:", m.get("winner"))
            print("Raw market keys:", list(m.keys()))
    else:
        print("No event found by slug, trying market slug directly...")
        url2 = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        resp2 = requests.get(url2, timeout=10)
        data2 = resp2.json()
        print("Market data:", data2)
except Exception as e:
    print("Error:", e)
