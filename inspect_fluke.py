import sqlite3

conn = sqlite3.connect(r"c:\projects\btc-5m-recorder\btc_5m_data.db")
cur = conn.cursor()

cur.execute("""
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
    FROM snapshots 
    WHERE cycle_id = 1795048800 
    ORDER BY gap_dollars ASC 
    LIMIT 10
""")
print("=== LOWEST GAPS IN CYCLE 1795048800 ===")
for r in cur.fetchall():
    print(f"Elapsed: {r[0]}s (Rem: {r[1]}s) | Spot: ${r[2]:,.2f} | Gap: ${r[3]:+,.2f} | UP Ask: {r[4]} | DOWN Ask: {r[5]}")

print("\n=== TIMELINE OF THE $180 RECOVERY ===")
cur.execute("""
    SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask
    FROM snapshots 
    WHERE cycle_id = 1795048800 AND elapsed_seconds IN (0, 30, 60, 90, 115, 121, 140, 160, 180, 200, 240, 280, 299)
    ORDER BY elapsed_seconds
""")
for r in cur.fetchall():
    print(f"T+{r[0]:03d}s (Rem {r[1]:03d}s) | Spot: ${r[2]:,.2f} | Gap: ${r[3]:+,.2f} | UP: {r[4]} | DOWN: {r[5]}")

conn.close()
