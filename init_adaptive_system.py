import sqlite3
import datetime

DB_PATH = "c:/projects/btc-5m-recorder/btc_5m_data.db"

def init_adaptive_system():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Create adaptive_safe_boundaries table
    c.execute("""
        CREATE TABLE IF NOT EXISTS adaptive_safe_boundaries (
            bracket TEXT PRIMARY KEY,
            min_remaining INTEGER,
            max_remaining INTEGER,
            record_up_squeeze REAL,
            record_down_dump REAL,
            buffer_pct REAL,
            safe_up_gap REAL,
            safe_down_gap REAL,
            worst_cycle_up INTEGER,
            worst_cycle_down INTEGER,
            updated_at TEXT
        )
    """)
    
    # 2. Create learning_log table for automated post-mortems
    c.execute("""
        CREATE TABLE IF NOT EXISTS learning_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            cycle_id INTEGER,
            trade_id INTEGER,
            bracket TEXT,
            old_safe_gap REAL,
            new_safe_gap REAL,
            reversal_observed REAL,
            lesson TEXT
        )
    """)
    
    # 3. Calculate all-time worst-case adverse reversals from all resolved cycles
    c.execute("""
        SELECT s.remaining_seconds, s.spot_price, s.gap_dollars, c.strike_price, c.final_price, s.cycle_id
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.final_price IS NOT NULL AND s.remaining_seconds BETWEEN 15 AND 120
    """)
    rows = c.fetchall()
    
    brackets_def = [
        ('15-30s', 15, 30, 0.15),   # 15% buffer
        ('31-45s', 31, 45, 0.15),
        ('46-60s', 46, 60, 0.15),
        ('61-90s', 61, 90, 0.15),
        ('91-120s', 91, 120, 0.15),
    ]
    
    results = {}
    for name, min_r, max_r, buf in brackets_def:
        results[name] = {
            'min_r': min_r, 'max_r': max_r, 'buf': buf,
            'max_up_squeeze': 0.0, 'worst_cid_up': None,
            'max_down_dump': 0.0, 'worst_cid_down': None
        }
        
    for rem, spot, gap, strike, final, cid in rows:
        for name, data in results.items():
            if data['min_r'] <= rem <= data['max_r']:
                # Adverse UP squeeze: spot was below strike (gap < 0), but final ended above strike (final > strike)
                if gap < 0 and final > strike:
                    deficit = abs(gap)
                    if deficit > data['max_up_squeeze']:
                        data['max_up_squeeze'] = deficit
                        data['worst_cid_up'] = cid
                # Adverse DOWN dump: spot was above strike (gap > 0), but final ended below strike (final < strike)
                if gap > 0 and final < strike:
                    deficit = gap
                    if deficit > data['max_down_dump']:
                        data['max_down_dump'] = deficit
                        data['worst_cid_down'] = cid
                break
                
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for name, data in results.items():
        buf = data['buf']
        # Apply buffer (+15% or at least +$5 cushion above all-time historical record)
        safe_up = round(max(data['max_down_dump'] * (1.0 + buf), data['max_down_dump'] + 5.0), 1)
        safe_down = round(max(data['max_up_squeeze'] * (1.0 + buf), data['max_up_squeeze'] + 5.0), 1)
        
        c.execute("""
            INSERT OR REPLACE INTO adaptive_safe_boundaries
            (bracket, min_remaining, max_remaining, record_up_squeeze, record_down_dump, buffer_pct, safe_up_gap, safe_down_gap, worst_cycle_up, worst_cycle_down, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, data['min_r'], data['max_r'], round(data['max_up_squeeze'], 2), round(data['max_down_dump'], 2),
              buf, safe_up, -safe_down, data['worst_cid_up'], data['worst_cid_down'], now_iso))
        
    conn.commit()
    
    print("=== ADAPTIVE SAFE BOUNDARIES INITIALIZED ===")
    c.execute("SELECT bracket, record_down_dump, safe_up_gap, record_up_squeeze, safe_down_gap FROM adaptive_safe_boundaries ORDER BY min_remaining ASC")
    for r in c.fetchall():
        print(f"Bracket [{r[0]}]: Dump Record ${r[1]:.2f} -> Safe UP: +${r[2]:.1f} | Squeeze Record ${r[3]:.2f} -> Safe DOWN: -${abs(r[4]):.1f}")
    
    conn.close()

if __name__ == "__main__":
    init_adaptive_system()
