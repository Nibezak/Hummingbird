import sqlite3
import datetime

conn = sqlite3.connect(r"c:\projects\btc-5m-recorder\btc_5m_data.db")
cur = conn.cursor()

# Create table if not exists
cur.execute("""
    CREATE TABLE IF NOT EXISTS dry_run_trades (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_id INTEGER UNIQUE,
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
        FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
    );
""")
conn.commit()

# Get all resolved cycles
cur.execute("""
    SELECT cycle_id, strike_price, final_price, winning_outcome 
    FROM cycles 
    WHERE status = 'RESOLVED' AND winning_outcome IS NOT NULL
    ORDER BY cycle_id
""")
cycles = cur.fetchall()

print(f"Testing Dry-Run Bot Logic on {len(cycles)} Historical Cycles...\n")

trades = []

for c in cycles:
    cid, strike, final_p, winner = c
    # Get snapshots for this cycle in chronological order
    cur.execute("""
        SELECT elapsed_seconds, remaining_seconds, spot_price, gap_dollars, up_best_ask, down_best_ask, up_ask_depth, down_ask_depth
        FROM snapshots
        WHERE cycle_id = ?
        ORDER BY elapsed_seconds ASC
    """, (cid,))
    snaps = cur.fetchall()

    for s in snaps:
        elapsed, rem, spot, gap, up_ask, dn_ask, up_dep, dn_dep = s
        if elapsed < 90 or rem < 15:
            continue

        # Dynamic Thresholds
        if rem >= 120:
            up_safe_gap = 90.0
            dn_safe_gap = -150.0  # Asymmetric protection against short squeezes
        elif rem >= 60:
            up_safe_gap = 40.0
            dn_safe_gap = -60.0
        elif rem >= 30:
            up_safe_gap = 18.0
            dn_safe_gap = -25.0
        else:
            up_safe_gap = 12.0
            dn_safe_gap = -15.0

        decision = None
        if gap >= up_safe_gap and up_ask and 0.20 <= up_ask <= 0.95 and up_dep >= 5.0:
            decision = {"direction": "Up", "ask": up_ask, "gap": gap, "rem": rem}
        elif gap <= dn_safe_gap and dn_ask and 0.20 <= dn_ask <= 0.95 and dn_dep >= 5.0:
            decision = {"direction": "Down", "ask": dn_ask, "gap": gap, "rem": rem}

        if decision:
            is_win = 1 if decision["direction"] == winner else 0
            bet = 100.0
            shares = round(bet / decision["ask"], 2)
            pnl = round((shares * 1.0 - bet), 2) if is_win else -bet
            roi = round((pnl / bet) * 100, 1)

            trades.append({
                "cycle_id": cid,
                "direction": decision["direction"],
                "ask": decision["ask"],
                "gap": decision["gap"],
                "rem": decision["rem"],
                "winner": winner,
                "is_win": is_win,
                "pnl": pnl,
                "roi": roi
            })
            break  # Max 1 trade per cycle

wins = sum(1 for t in trades if t["is_win"] == 1)
losses = sum(1 for t in trades if t["is_win"] == 0)
total_pnl = sum(t["pnl"] for t in trades)
win_rate = (wins / len(trades) * 100) if trades else 0

print("=" * 75)
print("🎯 HISTORICAL DRY-RUN SIMULATION RESULTS")
print("=" * 75)
print(f"Total Qualified Trade Calls: {len(trades)}")
print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
print(f"Total Virtual Profit/Loss: ${total_pnl:+,.2f} on $100 bets")
print(f"Average Return per Trade:  ${total_pnl / len(trades) if trades else 0:+,.2f}")
print("=" * 75)

for i, t in enumerate(trades[:10], 1):
    status = "✅ WIN" if t["is_win"] else "❌ LOSS"
    print(f"Trade #{i:02d} | Cycle {t['cycle_id']} | Call: {t['direction'].upper()} @ {t['ask']:.2f}¢ | Gap: ${t['gap']:+,.2f} (T-{t['rem']}s) -> Result: {t['winner'].upper()} | {status} | PnL: ${t['pnl']:+.2f}")

conn.close()
