# HUMMINGBIRD 7-CRYPTO AUTONOMOUS MAINTENANCE & STRATEGY RECALIBRATION SYSTEM PROMPT

> **How to Use:** Whenever you want to re-audit the strategy, update safe boundaries, check token price drift, or incorporate new weekly data, copy and paste the prompt in the box below into chat with Antigravity.

```markdown
<USER_REQUEST>
Execute the Hummingbird Strategy Recalibration Protocol. Perform a complete multi-crypto market audit across all 7 assets (BTC, ETH, SOL, DOGE, XRP, BNB, HYPE). Check nominal price drift, re-assess rolling percentiles, verify institutional deadzones, audit Bot A and Bot B performance, apply the 3% frequency regime filter, update multi_asset_safe_boundaries.json if warranted, and commit all changes to the Hummingbird repository.
</USER_REQUEST>
```

---

## AGENT INSTRUCTION & EXECUTION PROTOCOL

When the user gives the instruction above, the AI Agent (**Antigravity**) MUST strictly follow this 6-phase procedure:

```
[Phase 1: Daemon Health] ───► [Phase 2: Price Drift] ───► [Phase 3: Rolling 7D %iles]
                                                                   │
                                                                   ▼
[Phase 6: Commit & Push] ◄─── [Phase 5: Bankroll Audit] ◄─── [Phase 4: Deadzones & 3% Filter]
```

### PHASE 1: SYSTEM & DAEMON HEALTH CHECK
1. Verify that all 5 Hummingbird background daemons are active:
   - `multi_asset_recorder.py`: Live 1-second WebSocket/REST stream across all 7 assets.
   - `multi_dry_run_bot.py`: Bot A (Session 1, High Security, 99th-percentile golden boundaries).
   - `multi_dry_run_bot_frequency.py`: Bot B (Session 2, High Frequency, 98th-percentile boundaries).
   - `multi_adaptive_learner.py`: Autonomous 3% frequency regime shift monitor.
   - `dashboard_server.py`: Real-time HTTP dashboard API server on port 8899.
2. If any daemon is stopped, report the status and revive it.

### PHASE 2: NOMINAL TOKEN PRICE & DRIFT AUDIT
Cryptocurrency prices fluctuate over time. A 20¢ price movement on SOL at $70 is 0.28%, but at $140, a 20¢ move is only 0.14%. To preserve an invariant statistical edge:
1. Fetch live spot prices for all 7 assets (`BTC`, `ETH`, `SOL`, `DOGE`, `XRP`, `BNB`, `HYPE`) from Binance / Chainlink.
2. Calculate the **Nominal Drift Factor**:
   $$\text{Drift Factor} = \frac{\text{Current Asset Price}}{\text{Baseline Asset Price}}$$
3. If price has drifted by $\ge 10\%$, proportionally scale nominal boundaries in `multi_asset_safe_boundaries.json` so the relative percentage safety margin remains constant.

### PHASE 3: ROLLING 7-DAY STATISTICAL PERCENTILE RE-ASSESSMENT
1. Analyze all 5-minute cycles over the past 7 days (or 2,016 cycles) recorded in `multi_crypto_data.db`.
2. For each asset and sniper window (90s, 60s, 45s, 30s):
   - Compute empirical 95th, 98th, and 99th percentile maximum adverse squeezes (breakdown traps) and dumps (breakout traps).
   - Compare the past week's 98th/99th percentiles to current `multi_asset_safe_boundaries.json`.

### PHASE 4: THE 3.0% FREQUENCY REGIME SHIFT FILTER
To prevent the bot from becoming overly strict from a single fluke:
- **Isolated Fluke ($< 3.0\%$ Frequency):** If an adverse reversal happened only once or twice ($< 3\%$ of recent cycles), classify it as `OUTLIER_IGNORED`. **DO NOT widen boundaries.** Keep baseline empirical thresholds to protect high trading frequency.
- **Genuine Regime Shift ($\ge 3.0\%$ Frequency):** Only if adverse moves of that magnitude occur $\ge 3.0\%$ of the time in the rolling window, classify as `REGIME_SHIFT_ADJUSTMENT`. Widen the boundary by +10% to accommodate the new macro volatility.

### PHASE 5: INSTITUTIONAL DEADZONES & BANKROLL AUDIT
1. **Deadzone Verification:** Audit the hourly distribution of adverse volatility spikes:
   - NYSE Opening Bell: `14:25 - 15:05 UTC` (05:25 - 06:05 PM EAT)
   - European Market Close (London Fix): `16:20 - 16:40 UTC` (07:20 - 07:40 PM EAT)
   - Asian Midday Fix: `03:50 - 04:30 UTC` (06:50 - 07:30 AM EAT)
   Verify whether daylight savings or macro cycles shifted peak volatility hours.
2. **Bankroll & Stake Sizing:**
   - Audit Bot A and Bot B wallet balances in `multi_wallet`.
   - Ensure the 15% Kelly stake fraction and $10.00 stake ceiling match account growth safely.

### PHASE 6: SCORECARD, CHANGELOG, & GIT PRESERVATION
1. Execute `python recalibrate_strategy.py` to write updates to `multi_asset_safe_boundaries.json` and log the audit to `multi_learning_log`.
2. Present the user with a standardized Markdown audit scorecard:
   - Price Drift Table (Baseline vs Current vs Drift %)
   - Safe Boundaries Table (Before vs After)
   - Bankroll Scorecard (Balances, Win Rates, Streaks)
3. Stage all modified and untracked files, create a detailed Git commit, and push to GitHub:
   ```powershell
   git add .
   git commit -m "feat(strategy): execute weekly multi-crypto strategy recalibration [TIMESTAMP]"
   git push origin main
   ```

---

## AUTOMATED EXECUTION COMMAND

Antigravity can perform Phases 1 through 5 in a single command by running:
```powershell
python c:\projects\btc-5m-recorder\recalibrate_strategy.py
```
After running this script, Antigravity inspects the output, displays the scorecard, and commits/pushes to Git.
