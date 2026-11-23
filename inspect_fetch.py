with open(r'c:\projects\btc-5m-recorder\recorder.py', 'r', encoding='utf-8') as f:
    code = f.read()

# find def fetch_polymarket_market
idx = code.find('def fetch_polymarket_market')
if idx != -1:
    print(code[idx:idx+1200])
