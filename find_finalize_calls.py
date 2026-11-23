with open(r'c:\projects\btc-5m-recorder\recorder.py', 'r', encoding='utf-8') as f:
    code = f.read()

idx = code.find('finalize_cycle')
while idx != -1:
    print(f"Match at {idx}: {code[idx:idx+200]}")
    idx = code.find('finalize_cycle', idx+1)
