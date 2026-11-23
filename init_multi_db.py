import sqlite3
import datetime

DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"

def init_multi_db():
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_cycles (
                cycle_id INTEGER,
                asset TEXT,
                slug TEXT UNIQUE,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                strike_price REAL,
                final_price REAL,
                winning_outcome TEXT,
                up_token_id TEXT,
                down_token_id TEXT,
                condition_id TEXT,
                status TEXT DEFAULT 'ACTIVE',
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (cycle_id, asset)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER,
                asset TEXT,
                timestamp INTEGER,
                elapsed_seconds INTEGER,
                remaining_seconds INTEGER,
                spot_price REAL,
                gap_dollars REAL,
                gap_pct REAL,
                up_best_ask REAL,
                up_ask_depth REAL,
                down_best_ask REAL,
                down_ask_depth REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_snap ON multi_snapshots(cycle_id, asset, elapsed_seconds)")
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_wallet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                balance REAL,
                initial_balance REAL,
                updated_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER,
                asset TEXT,
                session_id INTEGER,
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
                resolved_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_trades_sess ON multi_trades(session_id, status)")
        
        # Check wallets
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM multi_wallet")
        if cur.fetchone()[0] == 0:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            # Wallet 1: Bot A (High Security) - Starts at $10.00
            conn.execute("INSERT INTO multi_wallet (id, session_id, balance, initial_balance, updated_at) VALUES (1, 1, 10.00, 10.00, ?)", (now_iso,))
            # Wallet 2: Bot B (High Frequency) - Starts at $10.00
            conn.execute("INSERT INTO multi_wallet (id, session_id, balance, initial_balance, updated_at) VALUES (2, 1, 10.00, 10.00, ?)", (now_iso,))
            print("Initialized Multi-Crypto DB: Wallet 1 (Bot A) = $10.00 | Wallet 2 (Bot B) = $10.00")
        else:
            print("Multi-Crypto DB already initialized.")

if __name__ == '__main__':
    init_multi_db()
