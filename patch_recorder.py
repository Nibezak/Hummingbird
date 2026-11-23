with open(r'c:\projects\btc-5m-recorder\recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace finalize_cycle with the new official Polymarket-first resolution function
old_finalize = """def finalize_cycle(conn, cycle_ts, strike_price):
    final_spot = get_binance_kline_open(cycle_ts + 300)
    if not final_spot:
        final_spot = get_binance_spot_price()

    winning_outcome = None
    if final_spot and strike_price:
        winning_outcome = "Up" if final_spot >= strike_price else "Down"

    m_info = fetch_polymarket_market(cycle_ts)
    if m_info and m_info.get("closed"):
        prices = m_info.get("outcomePrices")
        if prices:
            try:
                p = json.loads(prices) if isinstance(prices, str) else prices
                if float(p[0]) > 0.9:
                    winning_outcome = "Up"
                elif float(p[1]) > 0.9:
                    winning_outcome = "Down"
            except Exception:
                pass

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with conn:
        conn.execute(\"\"\"
            UPDATE cycles 
            SET final_price = ?, winning_outcome = ?, status = 'RESOLVED', updated_at = ?
            WHERE cycle_id = ?
        \"\"\", (final_spot, winning_outcome, now_iso, cycle_ts))

    diff = (final_spot - strike_price) if (final_spot and strike_price) else 0.0
    res_str = f"🏁 [CYCLE RESOLVED] {cycle_ts} | Strike: ${strike_price:,.2f} | Final: ${final_spot:,.2f} | Diff: ${diff:+,.2f} | Winner: {winning_outcome.upper() if winning_outcome else 'UNKNOWN'}"
    print(f"\\n{res_str}\\n")
    file_log(res_str)

    # ── SELF-IMPROVING ADAPTIVE VOLATILITY RATCHET ──
    update_adaptive_boundaries_for_cycle(conn, cycle_ts)"""

new_finalize = """def check_and_finalize_pending_cycles(conn):
    \"\"\"Checks completed cycles and resolves them using Polymarket's official Chainlink TWAP outcome.\"\"\"
    try:
        cur = conn.cursor()
        now = int(time.time())
        # Check cycles that ended in the last 45 minutes that are not yet RESOLVED
        cur.execute(\"\"\"
            SELECT cycle_id, strike_price, status 
            FROM cycles 
            WHERE status IN ('ACTIVE', 'PENDING_RESOLUTION') AND cycle_id <= ?
            ORDER BY cycle_id ASC
        \"\"\", (now - 300,))
        pending = cur.fetchall()

        for cid, strike, stat in pending:
            elapsed_since_end = now - (cid + 300)
            m_info = fetch_polymarket_market(cid)
            poly_winner = None
            if m_info and m_info.get("closed"):
                prices = m_info.get("outcomePrices")
                if prices:
                    try:
                        p = json.loads(prices) if isinstance(prices, str) else prices
                        if float(p[0]) > 0.9:
                            poly_winner = "Up"
                        elif float(p[1]) > 0.9:
                            poly_winner = "Down"
                    except Exception:
                        pass

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if poly_winner:
                final_spot = get_binance_kline_open(cid + 300) or get_binance_spot_price()
                with conn:
                    conn.execute(\"\"\"
                        UPDATE cycles 
                        SET final_price = ?, winning_outcome = ?, status = 'RESOLVED', updated_at = ?
                        WHERE cycle_id = ?
                    \"\"\", (final_spot, poly_winner, now_iso, cid))
                diff = (final_spot - strike) if (final_spot and strike) else 0.0
                res_str = f"🏁 [OFFICIAL POLYMARKET RESOLUTION] Cycle {cid} | Winner: {poly_winner.upper()} | Spot: ${final_spot:,.2f} (Diff: ${diff:+,.2f})"
                print(f"\\n{res_str}\\n")
                file_log(res_str)
                update_adaptive_boundaries_for_cycle(conn, cid)
            elif elapsed_since_end > 300:
                # If over 5 minutes passed and Polymarket API hasn't updated (fallback)
                final_spot = get_binance_kline_open(cid + 300) or get_binance_spot_price()
                fallback_winner = "Up" if final_spot >= strike else "Down"
                with conn:
                    conn.execute(\"\"\"
                        UPDATE cycles 
                        SET final_price = ?, winning_outcome = ?, status = 'RESOLVED', updated_at = ?
                        WHERE cycle_id = ?
                    \"\"\", (final_spot, fallback_winner, now_iso, cid))
                diff = (final_spot - strike) if (final_spot and strike) else 0.0
                res_str = f"⚠️ [FALLBACK RESOLUTION] Cycle {cid} | Winner: {fallback_winner.upper()} (Polymarket delayed >5m)"
                print(f"\\n{res_str}\\n")
                file_log(res_str)
                update_adaptive_boundaries_for_cycle(conn, cid)
            else:
                if stat != 'PENDING_RESOLUTION':
                    with conn:
                        conn.execute(\"\"\"
                            UPDATE cycles SET status = 'PENDING_RESOLUTION', updated_at = ? WHERE cycle_id = ?
                        \"\"\", (now_iso, cid))
    except Exception as e:
        file_log(f"Error in check_and_finalize_pending_cycles: {e}")"""

# Also replace caller in main loop
old_caller = """            # Check if previous cycle needs resolution
            prev_cycle_ts = cycle_ts - 300
            cur = conn.cursor()
            cur.execute("SELECT strike_price, status FROM cycles WHERE cycle_id = ?", (prev_cycle_ts,))
            prev_row = cur.fetchone()
            if prev_row and prev_row[1] == "ACTIVE":
                finalize_cycle(conn, prev_cycle_ts, prev_row[0])"""

new_caller = """            # Check and resolve any completed cycles officially via Polymarket
            check_and_finalize_pending_cycles(conn)"""

if old_finalize in content and old_caller in content:
    updated = content.replace(old_finalize, new_finalize).replace(old_caller, new_caller)
    with open(r'c:\projects\btc-5m-recorder\recorder.py', 'w', encoding='utf-8') as f:
        f.write(updated)
    print("recorder.py successfully updated with official Polymarket polling!")
else:
    print("Could not find exact strings in recorder.py")
    if old_finalize not in content:
        print("old_finalize mismatch")
    if old_caller not in content:
        print("old_caller mismatch")
