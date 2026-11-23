import sqlite3
import statistics

conn = sqlite3.connect(r"c:\projects\btc-5m-recorder\btc_5m_data.db")
cur = conn.cursor()

# 1. Total overview
cur.execute("SELECT COUNT(*) FROM cycles")
tot_cycles = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM cycles WHERE status = 'RESOLVED'")
res_cycles = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM snapshots")
tot_snaps = cur.fetchone()[0]

print(f"Dataset Size: {tot_cycles} cycles ({res_cycles} resolved), {tot_snaps} snapshots recorded.\n")

# 2. Asymmetry Analysis: UP vs DOWN behavior
cur.execute("""
    SELECT 
        c.cycle_id, 
        c.winning_outcome, 
        c.max_positive_gap, 
        c.max_negative_gap, 
        c.final_price - c.strike_price
    FROM cycles c
    WHERE c.status = 'RESOLVED' AND c.strike_price IS NOT NULL AND c.final_price IS NOT NULL
""")
resolved = cur.fetchall()

up_moves = [r[4] for r in resolved if r[1] == 'Up']
down_moves = [abs(r[4]) for r in resolved if r[1] == 'Down']

print(f"=== 1. DIRECTIONAL ASYMMETRY (UP vs DOWN) ===")
print(f"Average Winning UP margin:   ${statistics.mean(up_moves):.2f} (Median: ${statistics.median(up_moves):.2f})")
print(f"Average Winning DOWN margin: ${statistics.mean(down_moves):.2f} (Median: ${statistics.median(down_moves):.2f})")

# 3. False Breakout / Trap Analysis:
# When price was ahead by $X, how often did it end up losing?
print("\n=== 2. THE 'FALSE BREAKOUT' COLLAPSE TRAP ===")
traps_up = [r for r in resolved if r[2] >= 50 and r[1] == 'Down']
traps_down = [r for r in resolved if abs(r[3]) >= 50 and r[1] == 'Up']
print(f"Rounds where BTC reached >= +$50 UP, but ended up LOSING (flipped DOWN): {len(traps_up)}")
for t in traps_up[:3]:
    print(f"   Cycle {t[0]}: Reached +${t[2]:.2f}, but finished at ${t[4]:.2f} (Winner: DOWN)")

print(f"Rounds where BTC reached >= -$50 DOWN, but ended up LOSING (flipped UP): {len(traps_down)}")
for t in traps_down[:3]:
    print(f"   Cycle {t[0]}: Reached -${abs(t[3]):.2f}, but finished at +${t[4]:.2f} (Winner: UP)")

# 4. Mispricing Duration (How long does a cheap price actually sit on the book?)
print("\n=== 3. HOW LONG DO MISPRICED ORDERS LAST? (SHELF-LIFE) ===")
cur.execute("""
    SELECT s.cycle_id, s.remaining_seconds, s.gap_dollars, s.up_best_ask, s.down_best_ask, c.winning_outcome, s.up_ask_depth, s.down_ask_depth
    FROM snapshots s
    JOIN cycles c ON s.cycle_id = c.cycle_id
    WHERE c.status = 'RESOLVED'
    ORDER BY s.cycle_id, s.timestamp
""")
snaps = cur.fetchall()

# Measure consecutive seconds where winning token was <= 95c while gap was >= $30 (safe)
streak_durations = []
current_streak = 0
current_cycle = None
depths_at_discount = []

for s in snaps:
    cid, rem, gap, up_ask, dn_ask, winner, up_dep, dn_dep = s
    is_safe_winning_discount = False
    depth = 0
    if winner == 'Up' and gap >= 30 and up_ask is not None and up_ask <= 0.95:
        is_safe_winning_discount = True
        depth = up_dep
    elif winner == 'Down' and gap <= -30 and dn_ask is not None and dn_ask <= 0.95:
        is_safe_winning_discount = True
        depth = dn_dep

    if is_safe_winning_discount:
        if current_cycle == cid:
            current_streak += 1
        else:
            if current_streak > 0:
                streak_durations.append(current_streak)
            current_cycle = cid
            current_streak = 1
        if depth > 0:
            depths_at_discount.append(depth)
    else:
        if current_streak > 0:
            streak_durations.append(current_streak)
            current_streak = 0

if current_streak > 0:
    streak_durations.append(current_streak)

if streak_durations:
    print(f"Average Duration Cheap Shares (<=95c) Stay on Book: {statistics.mean(streak_durations):.1f} seconds")
    print(f"Median Duration: {statistics.median(streak_durations):.1f} seconds")
    print(f"Longest Recorded Window to Buy: {max(streak_durations)} seconds")
else:
    print("No qualifying streaks found.")

if depths_at_discount:
    print(f"Average Available Liquidity Depth at <=95c: ${statistics.mean(depths_at_discount):,.2f}")
    print(f"Median Available Liquidity Depth at <=95c:  ${statistics.median(depths_at_discount):,.2f}")
    print(f"Max Single-Order Liquidity at <=95c:       ${max(depths_at_discount):,.2f}")

# 5. Overpricing vs Underpricing (Do humans overpay for UP or DOWN?)
print("\n=== 4. CROWD PSYCHOLOGY: THE 'UP BIAS' ON POLYMARKET ===")
cur.execute("""
    SELECT AVG(up_best_ask), AVG(down_best_ask)
    FROM snapshots
    WHERE remaining_seconds BETWEEN 270 AND 290
""")
row = cur.fetchone()
print(f"Average UP token Ask in first 30 seconds of round:   {row[0]:.3f} ({row[0]*100:.1f}%)")
print(f"Average DOWN token Ask in first 30 seconds of round: {row[1]:.3f} ({row[1]*100:.1f}%)")

conn.close()
