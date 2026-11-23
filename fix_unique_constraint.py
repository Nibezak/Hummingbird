import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db', timeout=30)
c = conn.cursor()

print("=== MIGRATING dry_run_trades: UNIQUE(cycle_id, session_id) ===")

c.execute("PRAGMA foreign_keys = OFF;")

c.execute("""
CREATE TABLE dry_run_trades_new (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    timestamp INTEGER,
    call_time TEXT,
    direction TEXT,
    elapsed_seconds INTEGER,
    remaining_seconds INTEGER,
    spot_at_call REAL,
    strike_price REAL,
    gap_at_call REAL,
    entry_price REAL,
    shares REAL,
    invested_usd REAL,
    winning_outcome TEXT,
    is_winner INTEGER,
    pnl REAL,
    roi_pct REAL,
    status TEXT DEFAULT 'OPEN',
    rule_triggered TEXT,
    final_settle_price REAL,
    resolved_at TEXT,
    session_id INTEGER DEFAULT 1,
    FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id),
    UNIQUE(cycle_id, session_id)
);
""")

c.execute("""
INSERT INTO dry_run_trades_new (
    trade_id, cycle_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds,
    spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, winning_outcome,
    is_winner, pnl, roi_pct, status, rule_triggered, final_settle_price, resolved_at, session_id
)
SELECT 
    trade_id, cycle_id, timestamp, call_time, direction, elapsed_seconds, remaining_seconds,
    spot_at_call, strike_price, gap_at_call, entry_price, shares, invested_usd, winning_outcome,
    is_winner, pnl, roi_pct, status, rule_triggered, final_settle_price, resolved_at, session_id
FROM dry_run_trades;
""")

c.execute("DROP TABLE dry_run_trades;")
c.execute("ALTER TABLE dry_run_trades_new RENAME TO dry_run_trades;")

c.execute("PRAGMA foreign_keys = ON;")
conn.commit()

c.execute("SELECT count(*) FROM dry_run_trades;")
cnt = c.fetchone()[0]
print(f"Migration completed successfully. Total trades preserved: {cnt}")

conn.close()
