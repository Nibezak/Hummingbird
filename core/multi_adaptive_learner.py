import sqlite3
import datetime
import json
import os
import time

DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"
BOUNDARIES_CONFIG_PATH = r"c:\projects\btc-5m-recorder\multi_asset_safe_boundaries.json"

WINDOWS = [
    (90, 80, 95),
    (60, 55, 75),
    (45, 40, 54),
    (30, 25, 39)
]

# Minimum frequency threshold for a valid regime shift adjustment (3.0%)
REGIME_SHIFT_MIN_FREQ = 0.03

def init_learning_db(conn):
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                asset TEXT,
                cycle_id INTEGER,
                window_seconds INTEGER,
                observed_reversal REAL,
                threshold_before REAL,
                threshold_after REAL,
                lesson TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_cycle ON multi_learning_log(cycle_id, asset)")

def load_boundaries():
    if os.path.exists(BOUNDARIES_CONFIG_PATH):
        try:
            with open(BOUNDARIES_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[LEARNER] Error loading boundaries config: {e}")
    return {}

def save_boundaries(boundaries):
    try:
        with open(BOUNDARIES_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(boundaries, f, indent=2)
        print(f"[LEARNER] Updated and saved {BOUNDARIES_CONFIG_PATH} successfully.", flush=True)
    except Exception as e:
        print(f"[LEARNER] Error saving boundaries: {e}", flush=True)

def check_reversal_frequency(cur, asset, min_rem, max_rem, adverse_mag, reversal_type):
    """
    Checks how frequently an adverse move >= adverse_mag has occurred over the last 100 resolved cycles.
    Returns: freq (0.0 to 1.0), count, total_cycles
    """
    cur.execute("""
        SELECT cycle_id, strike_price, final_price, winning_outcome
        FROM multi_cycles
        WHERE asset = ? AND status = 'RESOLVED' AND strike_price IS NOT NULL
        ORDER BY cycle_id DESC
        LIMIT 100
    """, (asset,))
    recent_cycles = cur.fetchall()
    if not recent_cycles or len(recent_cycles) < 10:
        return 0.0, 0, len(recent_cycles)

    count = 0
    for cid, strike, final, winner in recent_cycles:
        is_up = winner and winner.lower() == 'up'
        is_down = winner and winner.lower() == 'down'
        cur.execute("""
            SELECT gap_dollars FROM multi_snapshots
            WHERE cycle_id = ? AND asset = ? AND remaining_seconds BETWEEN ? AND ?
        """, (cid, asset, min_rem, max_rem))
        snaps = cur.fetchall()
        for (gap,) in snaps:
            if gap is None:
                continue
            if reversal_type == "UP_SQUEEZE" and gap < 0 and is_up:
                if abs(gap) >= adverse_mag:
                    count += 1
                    break
            elif reversal_type == "DOWN_DUMP" and gap > 0 and is_down:
                if gap >= adverse_mag:
                    count += 1
                    break

    freq = count / len(recent_cycles)
    return freq, count, len(recent_cycles)

def process_resolved_cycles(conn, boundaries):
    cur = conn.cursor()
    cur.execute("""
        SELECT c.cycle_id, c.asset, c.strike_price, c.final_price, c.winning_outcome
        FROM multi_cycles c
        WHERE c.status = 'RESOLVED' AND c.strike_price IS NOT NULL AND c.final_price IS NOT NULL
        ORDER BY c.cycle_id ASC
    """)
    resolved_cycles = cur.fetchall()
    
    updates_made = False
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for cid, asset, strike, final, winner in resolved_cycles:
        cur.execute("SELECT COUNT(*) FROM multi_learning_log WHERE cycle_id = ? AND asset = ?", (cid, asset))
        if cur.fetchone()[0] > 0:
            continue

        if asset not in boundaries or 'windows' not in boundaries[asset]:
            continue

        for win_sec, min_rem, max_rem in WINDOWS:
            win_key = str(win_sec)
            cur.execute("""
                SELECT gap_dollars 
                FROM multi_snapshots 
                WHERE cycle_id = ? AND asset = ? AND remaining_seconds BETWEEN ? AND ?
            """, (cid, asset, min_rem, max_rem))
            snaps = cur.fetchall()
            if not snaps:
                continue

            max_adverse = 0.0
            reversal_type = None

            is_resolved_up = winner and winner.lower() == 'up'
            is_resolved_down = winner and winner.lower() == 'down'

            for (gap,) in snaps:
                if gap is None:
                    continue
                # Down breakout (gap < 0), but market resolved UP (squeeze)
                if gap < 0 and is_resolved_up:
                    squeeze = abs(gap)
                    if squeeze > max_adverse:
                        max_adverse = squeeze
                        reversal_type = "UP_SQUEEZE"
                # Up breakout (gap > 0), but market resolved DOWN (dump)
                elif gap > 0 and is_resolved_down:
                    dump = gap
                    if dump > max_adverse:
                        max_adverse = dump
                        reversal_type = "DOWN_DUMP"

            if reversal_type and max_adverse > 0:
                win_data = boundaries[asset]['windows'].get(win_key, {})
                golden_up = win_data.get('golden_up', 0.0)
                golden_dn = abs(win_data.get('golden_dn', 0.0))
                thresh = golden_up if reversal_type == "DOWN_DUMP" else golden_dn

                if max_adverse >= thresh:
                    # Statistical Frequency Test: Is this happening frequently (>= 3.0%)?
                    freq, count, total_win_cycles = check_reversal_frequency(
                        cur, asset, min_rem, max_rem, max_adverse, reversal_type
                    )

                    if freq >= REGIME_SHIFT_MIN_FREQ:
                        # Genuine regime shift: adjust boundary to accommodate new volatility
                        new_thresh = round(max_adverse * 1.10, 4)
                        if reversal_type == "DOWN_DUMP":
                            win_data['golden_up'] = new_thresh
                            win_data['hf_up'] = round(max_adverse * 1.05, 4)
                        else:
                            win_data['golden_dn'] = -new_thresh
                            win_data['hf_dn'] = -round(max_adverse * 1.05, 4)

                        boundaries[asset]['windows'][win_key] = win_data
                        updates_made = True

                        lesson = f"VALID REGIME SHIFT: Cycle {cid} [{asset} @ {win_sec}s] {reversal_type} of ${max_adverse:.4f} occurred with {freq*100:.1f}% frequency ({count}/{total_win_cycles} >= 3% threshold). Adjusted boundary to ${new_thresh:.4f}."
                        with conn:
                            conn.execute("""
                                INSERT INTO multi_learning_log (timestamp, event_type, asset, cycle_id, window_seconds, observed_reversal, threshold_before, threshold_after, lesson)
                                VALUES (?, 'REGIME_SHIFT_ADJUSTMENT', ?, ?, ?, ?, ?, ?, ?)
                            """, (now_iso, asset, cid, win_sec, max_adverse, thresh, new_thresh, lesson))
                        print(f"[LEARNER - REGIME ADJUSTMENT] {lesson}", flush=True)

                    else:
                        # Isolated outlier / black swan noise (< 3% frequency) -> DO NOT choke the bot!
                        lesson = f"ISOLATED OUTLIER IGNORED: Cycle {cid} [{asset} @ {win_sec}s] had {reversal_type} of ${max_adverse:.4f}, but observed frequency is {freq*100:.1f}% ({count}/{total_win_cycles} < 3% threshold). Preserved normal empirical boundary (${thresh:.4f}) to maintain high trading frequency."
                        with conn:
                            conn.execute("""
                                INSERT INTO multi_learning_log (timestamp, event_type, asset, cycle_id, window_seconds, observed_reversal, threshold_before, threshold_after, lesson)
                                VALUES (?, 'OUTLIER_IGNORED', ?, ?, ?, ?, ?, ?, ?)
                            """, (now_iso, asset, cid, win_sec, max_adverse, thresh, thresh, lesson))
                        print(f"[LEARNER - OUTLIER IGNORED] {lesson}", flush=True)

                else:
                    # Boundary safely shielded capital
                    lesson = f"Cycle {cid} [{asset} @ {win_sec}s] had {reversal_type} of ${max_adverse:.4f}. Safe boundary (${thresh:.4f}) successfully avoided false entry; 0 losses taken."
                    with conn:
                        conn.execute("""
                            INSERT INTO multi_learning_log (timestamp, event_type, asset, cycle_id, window_seconds, observed_reversal, threshold_before, threshold_after, lesson)
                            VALUES (?, 'AVOIDED_ADVERSE_REVERSAL', ?, ?, ?, ?, ?, ?, ?)
                        """, (now_iso, asset, cid, win_sec, max_adverse, thresh, thresh, lesson))
                    print(f"[LEARNER - SHIELD] {lesson}", flush=True)

    if updates_made:
        save_boundaries(boundaries)

def main():
    print("[MULTI ADAPTIVE LEARNER] Initializing 7-Crypto Self-Improvement Engine (3% Frequency Regime Filter Active)...", flush=True)
    if not os.path.exists(DB_PATH):
        print(f"[LEARNER ERROR] Database not found at {DB_PATH}", flush=True)
        return

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    init_learning_db(conn)
    print("[MULTI ADAPTIVE LEARNER] Connected to database and verified multi_learning_log table.", flush=True)

    boundaries = load_boundaries()
    print(f"[MULTI ADAPTIVE LEARNER] Loaded boundaries for {len(boundaries)} assets.", flush=True)

    # Process all historical resolved cycles right away
    process_resolved_cycles(conn, boundaries)

    print("[MULTI ADAPTIVE LEARNER] Live monitoring loop active. Inspecting cycles every 15s...", flush=True)

    while True:
        try:
            boundaries = load_boundaries()
            process_resolved_cycles(conn, boundaries)
            time.sleep(15)
        except Exception as e:
            print(f"[LEARNER EXCEPTION] {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    main()
