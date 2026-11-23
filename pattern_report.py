import sqlite3

conn = sqlite3.connect(r"c:\projects\btc-5m-recorder\btc_5m_data.db")
cur = conn.cursor()

# 1. Total cycles & win distribution
cur.execute("""
    SELECT final_price - strike_price, winning_outcome, max_positive_gap, max_negative_gap 
    FROM cycles 
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
""")
cycles = cur.fetchall()

diffs = [c[0] for c in cycles]
up_wins = sum(1 for c in cycles if c[1] == 'Up')
down_wins = sum(1 for c in cycles if c[1] == 'Down')
abs_diffs = sorted([abs(d) for d in diffs])
median_diff = abs_diffs[len(abs_diffs)//2] if abs_diffs else 0
max_diff = max(abs_diffs) if abs_diffs else 0
min_diff = min(abs_diffs) if abs_diffs else 0

print(f"=== 1. GENERAL OUTCOME PATTERN ===")
print(f"Total Resolved Rounds: {len(cycles)}")
print(f"UP Wins: {up_wins} ({up_wins/len(cycles)*100:.1f}%) | DOWN Wins: {down_wins} ({down_wins/len(cycles)*100:.1f}%)")
print(f"Final Open-to-Close Move: Median = ${median_diff:.2f}, Min = ${min_diff:.2f}, Max = ${max_diff:.2f}\n")

# 2. Check gap thresholds at each remaining time
intervals = [
    ("4 min left (240s)", 240, [30, 50, 75, 100]),
    ("3 min left (180s)", 180, [50, 75, 100, 130]),
    ("2 min left (120s)", 120, [30, 60, 90, 100]),
    ("1 min left (60s)", 60, [15, 25, 30, 50]),
    ("30 sec left (30s)", 30, [10, 15, 20, 30]),
    ("10 sec left (10s)", 10, [5, 10, 15, 20])
]

print("=== 2. SAFE BOUNDARY & WIN-RATE BY GAP ===")
for label, target_rem, test_gaps in intervals:
    print(f"\n--- {label} ---")
    query = """
        WITH ranked AS (
            SELECT 
                s.cycle_id,
                s.remaining_seconds,
                s.gap_dollars,
                s.up_best_ask,
                s.down_best_ask,
                c.winning_outcome,
                ROW_NUMBER() OVER (PARTITION BY s.cycle_id ORDER BY ABS(s.remaining_seconds - ?)) as rn
            FROM snapshots s
            JOIN cycles c ON s.cycle_id = c.cycle_id
            WHERE c.status = 'RESOLVED' AND c.winning_outcome IS NOT NULL
              AND ABS(s.remaining_seconds - ?) <= 8
        )
        SELECT cycle_id, gap_dollars, winning_outcome, up_best_ask, down_best_ask
        FROM ranked WHERE rn = 1
    """
    cur.execute(query, (target_rem, target_rem))
    rows = cur.fetchall()

    for g in test_gaps:
        # Check positive gap -> resolved Up
        pos_total = [r for r in rows if r[1] >= g]
        pos_won = [r for r in pos_total if r[2] == 'Up']

        # Check negative gap -> resolved Down
        neg_total = [r for r in rows if r[1] <= -g]
        neg_won = [r for r in neg_total if r[2] == 'Down']

        total_tested = len(pos_total) + len(neg_total)
        total_won = len(pos_won) + len(neg_won)
        win_rate = (total_won / total_tested * 100) if total_tested > 0 else 0

        # Mispricings: when gap was >= g, was winning token ask <= 0.95?
        mispriced_95 = [r for r in pos_total if r[2] == 'Up' and r[3] is not None and r[3] <= 0.95] + \
                       [r for r in neg_total if r[2] == 'Down' and r[4] is not None and r[4] <= 0.95]
        
        mispriced_85 = [r for r in pos_total if r[2] == 'Up' and r[3] is not None and r[3] <= 0.85] + \
                       [r for r in neg_total if r[2] == 'Down' and r[4] is not None and r[4] <= 0.85]

        status = "✅ 100.0% SAFE" if win_rate == 100.0 and total_tested >= 5 else f"{win_rate:.1f}%"
        print(f"  Gap >= ${g:>3}: {total_won:>2}/{total_tested:<2} won ({status}) | Mispriced <=95c: {len(mispriced_95)} rounds | <=85c: {len(mispriced_85)} rounds")

conn.close()
