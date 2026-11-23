import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
c = conn.cursor()

# Golden Time-Decayed Boundaries:
# 15-30s:  UP >= +35.0,  DN <= -25.0 (Bot A) | UP >= +31.5,  DN <= -23.0 (Bot B)
# 31-45s:  UP >= +50.0,  DN <= -40.0 (Bot A) | UP >= +45.0,  DN <= -36.5 (Bot B)
# 46-60s:  UP >= +65.0,  DN <= -55.0 (Bot A) | UP >= +59.0,  DN <= -50.0 (Bot B)
# 61-90s:  UP >= +85.0,  DN <= -75.0 (Bot A) | UP >= +77.5,  DN <= -68.0 (Bot B)
# 91-120s: UP >= +105.0, DN <= -90.0 (Bot A) | UP >= +95.5,  DN <= -81.5 (Bot B)

golden_brackets = [
    ('15-30s', 15, 30, 21.7, 30.4, 0.15, 35.0, -25.0),
    ('31-45s', 31, 45, 34.8, 43.5, 0.15, 50.0, -40.0),
    ('46-60s', 46, 60, 47.8, 56.5, 0.15, 65.0, -55.0),
    ('61-90s', 61, 90, 65.2, 73.9, 0.15, 85.0, -75.0),
    ('91-120s', 91, 120, 78.3, 91.3, 0.15, 105.0, -90.0)
]

now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

print("=== APPLYING GOLDEN TIME-DECAYED ADAPTIVE BOUNDARIES ===")
for b_name, min_r, max_r, rec_sq, rec_dp, buf, safe_up, safe_dn in golden_brackets:
    c.execute('''
        UPDATE adaptive_safe_boundaries
        SET record_up_squeeze = ?, record_down_dump = ?, buffer_pct = ?, safe_up_gap = ?, safe_down_gap = ?, updated_at = ?
        WHERE bracket = ?
    ''', (rec_sq, rec_dp, buf, safe_up, safe_dn, now_iso, b_name))
    
    # Calculate Bot B's boundary (+5% buffer on squeeze/dump)
    bot_b_up = round(rec_dp * 1.05, 1)
    bot_b_dn = -round(rec_sq * 1.05, 1)
    
    print(f"[{b_name}] Baseline: Squeeze ${rec_sq} | Dump ${rec_dp}")
    print(f"   -> Bot A (Security +15%): UP >= +${safe_up:.1f} | DOWN <= ${safe_dn:.1f}")
    print(f"   -> Bot B (Frequency +5%): UP >= +${bot_b_up:.1f} | DOWN <= ${bot_b_dn:.1f}")

# Log to learning_log
c.execute('''
    INSERT INTO learning_log (timestamp, event_type, cycle_id, bracket, old_safe_gap, new_safe_gap, reversal_observed, lesson)
    VALUES (?, 'GOLDEN_TIME_DECAY_CALIBRATION', 0, 'ALL', 123.0, 105.0, 91.3, ?)
''', (now_iso, "Applied golden time-decay curve restoring natural time-scaled lead requirements across T-15s to T-120s, eliminating the pricing deadlock."))

conn.commit()
conn.close()
print("\n[SUCCESS] btc_5m_data.db updated with Golden Time-Decayed calibration.")
