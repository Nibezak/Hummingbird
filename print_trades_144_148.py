import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# Get trades 144 to 148
c.execute('''
    SELECT trade_id, session_id, cycle_id, call_time, remaining_seconds, direction, entry_price, 
           shares, invested_usd, spot_at_call, strike_price, gap_at_call, final_settle_price, 
           winning_outcome, is_winner, pnl, roi_pct, rule_triggered
    FROM dry_run_trades 
    WHERE trade_id >= 144
    ORDER BY trade_id ASC
''')
trades = c.fetchall()

print(f"{'Trade':<6} | {'Bot':<18} | {'Cycle':<10} | {'Time (UTC)':<16} | {'Rem':<4} | {'Dir':<4} | {'Price':<6} | {'Stake':<6} | {'Gap':<8} | {'Strike':<9} | {'Final':<9} | {'PnL':<8} | {'ROI':<7}")
print("-" * 125)

for r in trades:
    bot_label = "Bot A (Security)" if r[1] == 3 else "Bot B (Frequency)"
    t_str = r[3].replace("T", " ")[11:19]
    print(f"#{r[0]:<5} | {bot_label:<18} | {r[2]:<10} | {t_str:<16} | T-{r[4]:02d}s | {r[5]:<4} | {r[6]:.2f}¢ | ${r[8]:.2f} | ${r[11]:+6.1f} | ${r[10]:.1f} | ${r[12]:.1f} | ${r[15]:+5.2f} | {r[16]:+5.1f}%")

c.execute('SELECT count(*) FROM cycles')
tot_cycles = c.fetchone()[0]
c.execute('SELECT count(*) FROM snapshots')
tot_snaps = c.fetchone()[0]
print(f"\nTotal Cycles: {tot_cycles} | Total Snapshots: {tot_snaps}")

conn.close()
