import http.server
import socketserver
import json
import sqlite3
import datetime
import os

PORT = 8899
DB_PATH = r"c:\projects\btc-5m-recorder\multi_crypto_data.db"

def get_dashboard_data():
    if not os.path.exists(DB_PATH):
        return {"error": "DB not found"}
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 1. Wallets & Open Position Stakes
    cur.execute("SELECT id, session_id, balance, initial_balance FROM multi_wallet")
    wallets = {r[0]: {'balance': r[2], 'initial': r[3]} for r in cur.fetchall()}

    # Calculate active stakes in play currently OPEN
    cur.execute("""
        SELECT session_id, COALESCE(SUM(invested_usd), 0), COUNT(*)
        FROM multi_trades
        WHERE status = 'OPEN'
        GROUP BY session_id
    """)
    open_stats = {r[0]: {'open_stake': r[1], 'open_count': r[2]} for r in cur.fetchall()}
    
    # 2. Bot A Stats (session_id = 1)
    cur.execute("""
        SELECT COUNT(*), 
               SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), 
               SUM(CASE WHEN is_winner=0 THEN 1 ELSE 0 END),
               COALESCE(SUM(pnl), 0)
        FROM multi_trades 
        WHERE session_id = 1 AND status LIKE 'RESOLVED%'
    """)
    tot_a, wins_a, loss_a, pnl_a = cur.fetchone()
    tot_a = tot_a or 0
    wins_a = wins_a or 0
    loss_a = loss_a or 0
    pnl_a = pnl_a or 0.0
    rate_a = (wins_a / tot_a * 100) if tot_a > 0 else 0.0
    
    cur.execute("SELECT is_winner FROM multi_trades WHERE session_id = 1 AND status LIKE 'RESOLVED%' ORDER BY trade_id DESC")
    streak_a = 0
    for row in cur.fetchall():
        if row[0] == 1: streak_a += 1
        else: break

    # 3. Bot B Stats (session_id = 2)
    cur.execute("""
        SELECT COUNT(*), 
               SUM(CASE WHEN is_winner=1 THEN 1 ELSE 0 END), 
               SUM(CASE WHEN is_winner=0 THEN 1 ELSE 0 END),
               COALESCE(SUM(pnl), 0)
        FROM multi_trades 
        WHERE session_id = 2 AND status LIKE 'RESOLVED%'
    """)
    tot_b, wins_b, loss_b, pnl_b = cur.fetchone()
    tot_b = tot_b or 0
    wins_b = wins_b or 0
    loss_b = loss_b or 0
    pnl_b = pnl_b or 0.0
    rate_b = (wins_b / tot_b * 100) if tot_b > 0 else 0.0
    
    cur.execute("SELECT is_winner FROM multi_trades WHERE session_id = 2 AND status LIKE 'RESOLVED%' ORDER BY trade_id DESC")
    streak_b = 0
    for row in cur.fetchall():
        if row[0] == 1: streak_b += 1
        else: break

    # 4. Trades (fetch all recent trades with on-chain token IDs, remaining time, and Polymarket links)
    cur.execute("""
        SELECT t.trade_id, t.asset, t.session_id, t.direction, t.entry_price, t.invested_usd, 
               t.pnl, t.status, t.call_time, t.cycle_id, t.remaining_seconds, t.spot_at_call,
               t.strike_price, t.gap_at_call, t.shares, t.rule_triggered,
               c.slug, c.condition_id, c.up_token_id, c.down_token_id
        FROM multi_trades t
        LEFT JOIN multi_cycles c ON t.cycle_id = c.cycle_id AND t.asset = c.asset
        ORDER BY t.trade_id DESC 
        LIMIT 250
    """)
    trades = []
    for r in cur.fetchall():
        (t_id, asset, sess_id, direction, entry_p, stake, pnl, status, call_time, 
         cycle_id, rem, spot, strike, gap, shares, rule, slug, cond_id, up_token, down_token) = r
        
        t_time = call_time[11:19] if call_time and len(call_time) >= 19 else "--:--:--"
        bot_label = "BOT A" if sess_id == 1 else "BOT B"
        outcome_label = "WIN" if status == "RESOLVED_WIN" else ("LOSS" if status == "RESOLVED_LOSS" else "OPEN")
        
        dir_str = (direction or "").upper()
        token_id = up_token if dir_str == "UP" else down_token
        poly_slug = slug if slug else f"{asset.lower()}-updown-5m-{cycle_id}"
        poly_url = f"https://polymarket.com/event/{poly_slug}"
        polygonscan_url = f"https://polygonscan.com/token/0x4D97DCd97eC945f40cF65F87097ACe5EA0476045?a={token_id}" if token_id else ""
        clob_url = f"https://clob.polymarket.com/book?token_id={token_id}" if token_id else ""

        trades.append({
            "id": t_id,
            "cycle_id": cycle_id,
            "asset": asset,
            "bot": bot_label,
            "direction": dir_str,
            "entry": f"{entry_p:.2f}¢" if entry_p else "--",
            "stake": f"${stake:.2f}" if stake else "--",
            "shares": f"{shares:.2f}" if shares else "--",
            "pnl": f"{pnl:+.2f}" if pnl is not None else "--",
            "outcome": outcome_label,
            "time": t_time,
            "remaining": rem if rem is not None else "--",
            "spot": f"${spot:.4f}" if spot else "--",
            "strike": f"${strike:.4f}" if strike else "--",
            "gap": f"{gap:+.4f}" if gap is not None else "--",
            "rule": rule or "--",
            "url": poly_url,
            "slug": poly_slug,
            "token_id": token_id or "",
            "polygonscan_url": polygonscan_url,
            "clob_url": clob_url,
            "condition_id": cond_id or ""
        })

    conn.close()

    raw_bal_a = wallets.get(1, {}).get('balance', 10.0)
    open_stake_a = open_stats.get(1, {}).get('open_stake', 0.0)
    open_count_a = open_stats.get(1, {}).get('open_count', 0)
    # Available balance reflecting placed stakes until settled
    active_bal_a = max(0.0, raw_bal_a - open_stake_a)

    raw_bal_b = wallets.get(2, {}).get('balance', 10.0)
    open_stake_b = open_stats.get(2, {}).get('open_stake', 0.0)
    open_count_b = open_stats.get(2, {}).get('open_count', 0)
    # Available balance reflecting placed stakes until settled
    active_bal_b = max(0.0, raw_bal_b - open_stake_b)

    return {
        "bot_a": {
            "balance": f"${active_bal_a:.2f}",
            "settled_balance": f"${raw_bal_a:.2f}",
            "open_stake": round(open_stake_a, 2),
            "open_count": open_count_a,
            "wins": wins_a,
            "losses": loss_a,
            "rate": f"{rate_a:.1f}%",
            "streak": streak_a,
            "pnl": f"{pnl_a:+.2f}"
        },
        "bot_b": {
            "balance": f"${active_bal_b:.2f}",
            "settled_balance": f"${raw_bal_b:.2f}",
            "open_stake": round(open_stake_b, 2),
            "open_count": open_count_b,
            "wins": wins_b,
            "losses": loss_b,
            "rate": f"{rate_b:.1f}%",
            "streak": streak_b,
            "pnl": f"{pnl_b:+.2f}"
        },
        "trades": trades,
        "server_time": datetime.datetime.now().strftime("%H:%M:%S")
    }

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/data' or self.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            data = get_dashboard_data()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            # Serve the dashboard page
            artifact_html_path = r"C:\Users\HP\.gemini\antigravity\brain\b05cdb08-be6f-4717-bde2-070a831b2e45\typewriter_dashboard.html"
            if os.path.exists(artifact_html_path):
                with open(artifact_html_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"<h1>Dashboard initializing...</h1>")

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        print(f"[DASHBOARD SERVER] Serving on http://127.0.0.1:{PORT}...", flush=True)
        httpd.serve_forever()

if __name__ == '__main__':
    run_server()
