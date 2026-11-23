with open(r'c:\projects\btc-5m-recorder\dry_run_bot.py', 'r', encoding='utf-8') as f:
    code = f.read()

idx = code.find('def resolve_settled_trades')
if idx != -1:
    print(code[idx:idx+1500])
