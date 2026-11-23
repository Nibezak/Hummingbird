"""
Polymarket BTC 5-Minute Safe-Boundary & Mispricing Analyzer
==========================================================
Analyzes the local SQLite database (btc_5m_data.db) to find:
1. The empirical maximum reversal distance (in dollars and bps) at each minute.
2. The 100% Safe Boundary Threshold (where no reversal has ever occurred).
3. The frequency and depth of mispriced contracts on Polymarket.

Run anytime with: python analyzer.py
"""

import os
import sqlite3
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_5m_data.db")


def run_analysis():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}. Run recorder.py first to collect data.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM cycles")
    total_cycles = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM cycles WHERE status = 'RESOLVED'")
    resolved_cycles = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM snapshots")
    total_snapshots = cur.fetchone()[0]

    print("=" * 80)
    print("📊 POLYMARKET BTC 5-MINUTE HISTORICAL EMPIRICAL ANALYSIS")
    print(f"📁 Database: {DB_PATH}")
    print(f"📈 Total Cycles Tracked: {total_cycles} (Resolved: {resolved_cycles})")
    print(f"⏱️ Total Price Snapshots: {total_snapshots:,}")
    print("=" * 80)

    if resolved_cycles < 2:
        print("\n⏳ Only a few cycles resolved so far. Keep recorder.py running to collect more rounds!")
        print("   Once at least a few dozen cycles are recorded, full statistical breakdown will appear here.\n")
        conn.close()
        return

    # Checkpoints to analyze (remaining seconds)
    checkpoints = [
        {"label": "4 min left", "target_rem": 240},
        {"label": "3 min left", "target_rem": 180},
        {"label": "2 min left", "target_rem": 120},
        {"label": "1 min left", "target_rem": 60},
        {"label": "30 sec left", "target_rem": 30},
        {"label": "10 sec left", "target_rem": 10},
    ]

    print("\n" + "-" * 95)
    print(f"{'Time Remaining':<15} | {'Cycles':<7} | {'Max Reversal ($)':<18} | {'Max Reversal (bps)':<19} | {'100% Safe Threshold':<20}")
    print("-" * 95)

    for cp in checkpoints:
        target = cp["target_rem"]
        # Find closest snapshot per resolved cycle within ±5s of target
        query = """
            WITH ranked AS (
                SELECT 
                    s.cycle_id,
                    s.remaining_seconds,
                    s.spot_price,
                    s.gap_dollars,
                    s.gap_bps,
                    s.up_best_ask,
                    s.down_best_ask,
                    c.winning_outcome,
                    c.strike_price,
                    c.final_price,
                    ROW_NUMBER() OVER (PARTITION BY s.cycle_id ORDER BY ABS(s.remaining_seconds - ?)) as rn
                FROM snapshots s
                JOIN cycles c ON s.cycle_id = c.cycle_id
                WHERE c.status = 'RESOLVED' AND c.winning_outcome IS NOT NULL
                  AND ABS(s.remaining_seconds - ?) <= 10
            )
            SELECT cycle_id, gap_dollars, gap_bps, winning_outcome, up_best_ask, down_best_ask
            FROM ranked
            WHERE rn = 1
        """
        cur.execute(query, (target, target))
        rows = cur.fetchall()

        if not rows:
            print(f"{cp['label']:<15} | {'0':<7} | {'No data yet':<18} | {'No data yet':<19} | {'N/A':<20}")
            continue

        reversals = []
        max_rev_dollars = 0.0
        max_rev_bps = 0.0

        for r in rows:
            cycle_id, gap, bps, winner, up_ask, dn_ask = r
            if gap > 0 and winner == "Down":
                # Price was higher, but ended down!
                reversals.append({"cycle_id": cycle_id, "gap": abs(gap), "bps": abs(bps)})
                if abs(gap) > max_rev_dollars:
                    max_rev_dollars = abs(gap)
                    max_rev_bps = abs(bps)
            elif gap < 0 and winner == "Up":
                # Price was lower, but ended up!
                reversals.append({"cycle_id": cycle_id, "gap": abs(gap), "bps": abs(bps)})
                if abs(gap) > max_rev_dollars:
                    max_rev_dollars = abs(gap)
                    max_rev_bps = abs(bps)

        safe_threshold_dollars = max_rev_dollars * 1.15 if max_rev_dollars > 0 else 25.0
        safe_threshold_bps = max_rev_bps * 1.15 if max_rev_bps > 0 else 4.0

        rev_dollars_str = f"${max_rev_dollars:,.2f}" if max_rev_dollars > 0 else "$0.00 (0 flips)"
        rev_bps_str = f"{max_rev_bps:.1f} bps" if max_rev_bps > 0 else "0.0 bps"
        safe_str = f"> ${safe_threshold_dollars:,.2f} ({safe_threshold_bps:.1f} bps)"

        print(f"{cp['label']:<15} | {len(rows):<7} | {rev_dollars_str:<18} | {rev_bps_str:<19} | {safe_str:<20}")

    print("-" * 95)

    # Mispricing statistics
    print("\n🔍 MISPRICING SCANNER (Cheap winning contracts on Polymarket):")
    cur.execute("""
        SELECT COUNT(*)
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED'
          AND ((c.winning_outcome = 'Up' AND s.up_best_ask <= 0.95)
            OR (c.winning_outcome = 'Down' AND s.down_best_ask <= 0.95))
    """)
    discount_95 = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM snapshots s
        JOIN cycles c ON s.cycle_id = c.cycle_id
        WHERE c.status = 'RESOLVED'
          AND ((c.winning_outcome = 'Up' AND s.up_best_ask <= 0.90)
            OR (c.winning_outcome = 'Down' AND s.down_best_ask <= 0.90))
    """)
    discount_90 = cur.fetchone()[0]

    print(f"   • Snapshots where winning token was selling at <= 95¢ (+5.3% ROI): {discount_95:,}")
    print(f"   • Snapshots where winning token was selling at <= 90¢ (+11.1% ROI): {discount_90:,}")
    print("=" * 80 + "\n")

    conn.close()


if __name__ == "__main__":
    run_analysis()
