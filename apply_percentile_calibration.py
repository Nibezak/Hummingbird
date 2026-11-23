import sqlite3
import datetime
import numpy as np

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# 1. Fetch all resolved cycles
c.execute('''
    SELECT cycle_id, strike_price, final_price 
    FROM cycles 
    WHERE status = 'RESOLVED' AND strike_price IS NOT NULL AND final_price IS NOT NULL
''')
cycles = c.fetchall()
print(f"Total resolved cycles analyzed: {len(cycles)}")

brackets = [
    ('15-30s', 15, 30),
    ('31-45s', 31, 45),
    ('46-60s', 46, 60),
    ('61-90s', 61, 90),
    ('91-120s', 91, 120)
]

now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

print("\n=== RECALIBRATING ADAPTIVE SAFE BOUNDARIES (98th PERCENTILE ROBUST MODEL) ===")

for b_name, min_r, max_r in brackets:
    squeezes = []
    dumps = []
    for cid, strike, final in cycles:
        c.execute('SELECT gap_dollars FROM snapshots WHERE cycle_id = ? AND remaining_seconds BETWEEN ? AND ?', (cid, min_r, max_r))
        snaps = c.fetchall()
        for (gap,) in snaps:
            if gap is None: continue
            if gap < 0 and final > strike: squeezes.append(abs(gap))
            elif gap > 0 and final < strike: dumps.append(gap)
            
    p98_sq = round(float(np.percentile(squeezes, 98)), 2)
    p98_dp = round(float(np.percentile(dumps, 98)), 2)
    
    # Bot A defaults (+15%)
    safe_up_A = round(p98_dp * 1.15, 1)
    safe_dn_A = round(p98_sq * 1.15, 1)
    
    # Bot B (+5%)
    safe_up_B = round(p98_dp * 1.05, 1)
    safe_dn_B = round(p98_sq * 1.05, 1)
    
    # Update adaptive_safe_boundaries
    c.execute('''
        UPDATE adaptive_safe_boundaries
        SET record_up_squeeze = ?, record_down_dump = ?, safe_up_gap = ?, safe_down_gap = ?, updated_at = ?
        WHERE bracket = ?
    ''', (p98_sq, p98_dp, safe_up_A, -safe_dn_A, now_iso, b_name))
    
    # Log to learning_log
    c.execute('''
        INSERT INTO learning_log (timestamp, event_type, cycle_id, bracket, old_safe_gap, new_safe_gap, reversal_observed, lesson)
        VALUES (?, 'PERCENTILE_RECALIBRATION_98TH', 0, ?, ?, ?, ?, ?)
    ''', (
        now_iso, b_name, 0, safe_up_A, p98_dp,
        f"Recalibrated {b_name} to 98th percentile empirical reference: Squeeze ${p98_sq:.2f}, Dump ${p98_dp:.2f}. Eliminates freak flash-crash distortion while filtering 98% of all historical adverse reversals."
    ))
    
    print(f"[{b_name}] Baseline: Squeeze ${p98_sq:.2f} | Dump ${p98_dp:.2f}")
    print(f"   -> Bot A (Security +15%): UP >= +${safe_up_A:.1f} | DOWN <= -${safe_dn_A:.1f}")
    print(f"   -> Bot B (Frequency +5%): UP >= +${safe_up_B:.1f} | DOWN <= -${safe_dn_B:.1f}")

conn.commit()
conn.close()
print("\n[SUCCESS] adaptive_safe_boundaries updated in btc_5m_data.db.")
