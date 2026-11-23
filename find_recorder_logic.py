# Let's inspect recorder.py around where cycles are fetched and resolved
with open(r'c:\projects\btc-5m-recorder\recorder.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'strike_price' in l or 'winning_outcome' in l or 'final_price' in l or 'resolve' in l.lower():
        print(f"Line {i+1}: {l.strip()}")
