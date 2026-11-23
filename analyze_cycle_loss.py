import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get details of cycle 1795444500
cursor.execute('''
    SELECT cycle_id, title, start_time, end_time, strike_price, final_price, winning_outcome, max_positive_gap, max_negative_gap, status
    FROM cycles
    WHERE cycle_id = 1795444500
''')
cycle_info = cursor.fetchone()
print("Cycle 1795444500:")
print(cycle_info)

# Get snapshots of cycle 1795444500 around final 2 minutes
cursor.execute('''
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, recorded_at
    FROM snapshots
    WHERE cycle_id = 1795444500 AND remaining_seconds BETWEEN 10 AND 130
    ORDER BY elapsed_seconds ASC
''')
snaps = cursor.fetchall()
print(f"\nSnapshots in final 2 minutes: {len(snaps)}")
for s in snaps[::2]: # print every 2nd snapshot
    print(s)

# Inspect exact streak lengths prior to trade #190 / #191
# Bot A trades up to #189
cursor.execute('''
    SELECT trade_id, is_winner, pnl, call_time
    FROM dry_run_trades
    WHERE session_id = 3 AND trade_id <= 189
    ORDER BY trade_id ASC
''')
a_prev_trades = cursor.fetchall()
a_prev_streak = 0
for t in reversed(a_prev_trades):
    if t[1] == 1 or (t[2] is not None and t[2] > 0):
        a_prev_streak += 1
    else:
        break

# Bot B trades up to #188
cursor.execute('''
    SELECT trade_id, is_winner, pnl, call_time
    FROM dry_run_trades
    WHERE session_id = 4 AND trade_id <= 188
    ORDER BY trade_id ASC
''')
b_prev_trades = cursor.fetchall()
b_prev_streak = 0
for t in reversed(b_prev_trades):
    if t[1] == 1 or (t[2] is not None and t[2] > 0):
        b_prev_streak += 1
    else:
        break

print(f"\n=== PREVIOUS WINNING STREAKS BEFORE LOSS ===")
print(f"Bot A Winning Streak Before Loss: {a_prev_streak} Consecutive Wins!")
print(f"Bot B Winning Streak Before Loss: {b_prev_streak} Consecutive Wins!")

# Check learning_log for cycle 1795444500
cursor.execute('''
    SELECT id, timestamp, event_type, cycle_id, trade_id, bracket, old_safe_gap, new_safe_gap, reversal_observed, lesson
    FROM learning_log
    WHERE cycle_id = 1795444500
''')
learning = cursor.fetchall()
print(f"\nLearning Log Entries for Cycle 1795444500: {len(learning)}")
for l in learning:
    print(l)

# Check active streak right now
cursor.execute("SELECT is_winner, pnl FROM dry_run_trades WHERE session_id = 3 ORDER BY trade_id ASC")
a_all = cursor.fetchall()
a_cur_streak = 0
for r in reversed(a_all):
    if r[0] == 1 or (r[1] and r[1] > 0): a_cur_streak += 1
    else: break

cursor.execute("SELECT is_winner, pnl FROM dry_run_trades WHERE session_id = 4 ORDER BY trade_id ASC")
b_all = cursor.fetchall()
b_cur_streak = 0
for r in reversed(b_all):
    if r[0] == 1 or (r[1] and r[1] > 0): b_cur_streak += 1
    else: break

print(f"\n=== CURRENT ACTIVE REBOUND STREAKS ===")
print(f"Bot A Rebound Streak: {a_cur_streak} Consecutive Wins")
print(f"Bot B Rebound Streak: {b_cur_streak} Consecutive Wins")

conn.close()
