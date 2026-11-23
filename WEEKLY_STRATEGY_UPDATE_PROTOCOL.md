# HUMMINGBIRD 7-CRYPTO AUTONOMOUS TRADING ENGINE
## Comprehensive Strategy, Architecture, & Maintenance Protocol

---

### 1. SYSTEM OVERVIEW
Hummingbird is an autonomous high-frequency late-candle statistical arbitrage trading engine designed for Polymarket 5-minute Up/Down crypto binary options. It continuously monitors 7 cryptocurrencies:
- **Bitcoin (`BTC`)**
- **Ethereum (`ETH`)**
- **Solana (`SOL`)**
- **Dogecoin (`DOGE`)**
- **XRP (`XRP`)**
- **Binance Coin (`BNB`)**
- **Hyperliquid (`HYPE`)**

### 2. CORE TRADING MECHANICS

#### A. Late-Candle Sniper Window (T-90s to T-15s)
Cryptocurrency prices follow continuous Brownian motion during the first 3.5 minutes of a 5-minute candle. Between $T-90\text{s}$ and $T-15\text{s}$, the probability of an adverse reversal exceeding empirical bounds drops below $1.0\%-2.0\%$ under normal market conditions.

#### B. Dual-Bot Architecture
1. **Bot A (High Security — Session 1, Wallet 1):**
   - Trades strictly when the spot price gap exceeds the **99th-percentile empirical adverse move (`golden_up` / `golden_dn`)** plus institutional safety buffers.
   - Entry target: 88¢ or better.
2. **Bot B (High Frequency — Session 2, Wallet 2):**
   - Trades when the spot price gap exceeds the **98th-percentile empirical adverse move (`hf_up` / `hf_dn`)** plus safety buffers.
   - Entry target: 86¢ or better.

#### C. Cheapest-Ask Contract Prioritization
When multiple cryptocurrencies trigger statistical arbitrage in the exact same 1-second cycle, Hummingbird sorts all qualified assets by lowest contract price (e.g. 86¢ before 88¢ before 90¢). Taking 86¢ contracts yields $+16.3\%$ profit per trade versus $+13.6\%$ at 88¢, accelerating bankroll compounding.

#### D. Multi-Trade Capacity ("Afford Both")
If available cash allows, Hummingbird enters multiple qualified coins in the same cycle rather than sitting dormant.

---

### 3. THE 3.0% FREQUENCY REGIME SHIFT RULE
In financial markets, single isolated black-swan wicks occur (e.g. 1 out of 2,400 cycles = $0.04\%$). Over-reacting to a single loss by ratcheting boundaries permanently chokes trade frequency.

Hummingbird enforces a **3.0% Frequency Filter**:
- **Isolated Outlier ($< 3.0\%$):** If an adverse move happened only once or twice, the engine classifies it as `OUTLIER_IGNORED`. Safe boundaries are preserved to maintain high trading volume.
- **Genuine Regime Shift ($\ge 3.0\%$):** If adverse moves of that size occur $\ge 3.0\%$ of the time in a rolling 100-cycle window, the engine classifies it as `REGIME_SHIFT_ADJUSTMENT` and widens thresholds by $+10\%$.

---

### 4. INSTITUTIONAL BLACKOUT WINDOWS (DEADZONES)
Empirical analysis of 5,040,000 ticks proved all 7 altcoins suffer extreme volatility spikes during institutional liquidity handoffs:
1. **NYSE Opening Bell (14:25 – 15:05 UTC / 05:25 – 06:05 PM EAT):** Spikes surge to 12%–20% of candle range. Active circuit breaker blocks new entries.
2. **European Market Close / London 4:00 PM Fix (16:20 – 16:40 UTC / 07:20 – 07:40 PM EAT):** Global institutional rebalancing. Active circuit breaker blocks new entries.
3. **Asian Midday Settlement (03:50 – 04:30 UTC / 06:50 – 07:30 AM EAT):** High-volatility settlement window.

---

### 5. ON-CHAIN POLYGON & CLOB ARCHITECTURE
- **Chainlink TWAP 60s Oracle:** Polymarket 5m markets resolve against Chainlink's 60-second time-weighted average price.
- **Polygon Conditional Tokens (CTF):** Contract `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` mints ERC-1155 outcome tokens.
- **Direct Proof Verification:**
  - `https://polygonscan.com/token/0x4D97DCd97eC945f40cF65F87097ACe5EA0476045?a={token_id}`
  - `https://clob.polymarket.com/book?token_id={token_id}`
  - `https://polymarket.com/event/{slug}`

---

### 6. PERIODIC RECALIBRATION CHECKLIST
Run weekly or after major macro volatility events:
```powershell
python c:\projects\btc-5m-recorder\recalibrate_strategy.py
```
This script audits:
1. Nominal price drift across BTC, ETH, SOL, DOGE, XRP, BNB, HYPE.
2. Rolling 7-day percentiles (95th, 98th, 99th).
3. 3.0% frequency regime shift verification.
4. Institutional deadzone drift.
5. Kelly stake sizing and bankroll balance verification.
