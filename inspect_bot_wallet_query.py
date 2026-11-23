with open(r'c:\projects\btc-5m-recorder\dry_run_bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'SELECT balance FROM wallet' in l or 'wallet_balance' in l:
        print(f"dry_run_bot Line {i+1}: {l.strip()}")

with open(r'c:\projects\btc-5m-recorder\dry_run_bot_frequency.py', 'r', encoding='utf-8') as f:
    lines_b = f.readlines()

for i, l in enumerate(lines_b):
    if 'SELECT balance FROM wallet' in l or 'wallet_balance' in l:
        print(f"dry_run_bot_frequency Line {i+1}: {l.strip()}")
