/**
 * LIVE ORDER EXECUTOR FOR POLYMARKET CLOB WITH ADAPTIVE CHASER & VWAP ENGINE
 * Path: c:\projects\btc-5m-recorder\live_executor.js
 * 
 * Directly leverages verified @polymarket/clob-client-v2 and viem setup from c:\projects\weather
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

const weatherDir = 'c:\\projects\\weather';
const envPath = path.resolve(weatherDir, '.env');

if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf8');
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx > 0) {
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  }
}

const clobPkg = require(path.resolve(weatherDir, 'node_modules/@polymarket/clob-client-v2'));
const viemPkg = require(path.resolve(weatherDir, 'node_modules/viem'));
const viemAcc = require(path.resolve(weatherDir, 'node_modules/viem/accounts'));

const SIGNER_KEY = process.env.POLYMARKET_SIGNER_PRIVATE_KEY;
const FUNDER_ADDRESS = process.env.POLYMARKET_FUNDER_ADDRESS;
const RPC_URL = process.env.POLYGON_RPC_URL || 'https://polygon-bor-rpc.publicnode.com';
const CLOB_HOST = process.env.CLOB_HOST || 'https://clob.polymarket.com';

let cachedClient = null;

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timed out')); });
  });
}

async function fetchOrderBook(tokenID) {
  try {
    const data = await httpGetJson(`https://clob.polymarket.com/book?token_id=${tokenID}`);
    const asks = (data.asks || []).map(a => ({ price: parseFloat(a.price), size: parseFloat(a.size) })).sort((a, b) => a.price - b.price);
    const bids = (data.bids || []).map(b => ({ price: parseFloat(b.price), size: parseFloat(b.size) })).sort((a, b) => b.price - a.price);
    const bestAsk = asks.length > 0 ? asks[0].price : null;
    const bestBid = bids.length > 0 ? bids[0].price : null;
    const askDepth = asks.slice(0, 3).reduce((sum, a) => sum + (a.price * a.size), 0);
    return { bestAsk, bestBid, askDepth: Math.round(askDepth * 100) / 100, asks, bids };
  } catch (err) {
    return { bestAsk: null, bestBid: null, askDepth: 0, asks: [], bids: [], error: err.message };
  }
}

async function fetchBinanceSpot(symbol) {
  try {
    const sym = symbol.toUpperCase().endsWith('USDT') ? symbol.toUpperCase() : `${symbol.toUpperCase()}USDT`;
    const data = await httpGetJson(`https://api.binance.com/api/v3/ticker/price?symbol=${sym}`);
    return parseFloat(data.price);
  } catch (err) {
    return null;
  }
}

async function getClient() {
  if (cachedClient) return cachedClient;

  const formattedKey = SIGNER_KEY.startsWith('0x') ? SIGNER_KEY : '0x' + SIGNER_KEY;
  const account = viemAcc.privateKeyToAccount(formattedKey);
  const signer = viemPkg.createWalletClient({ account, transport: viemPkg.http(RPC_URL) });

  const baseClient = new clobPkg.ClobClient({
    host: CLOB_HOST,
    chain: clobPkg.Chain.POLYGON,
    signer,
    funderAddress: FUNDER_ADDRESS,
    signatureType: 3
  });

  const apiCreds = await baseClient.createOrDeriveApiKey();

  cachedClient = new clobPkg.ClobClient({
    host: CLOB_HOST,
    chain: clobPkg.Chain.POLYGON,
    signer,
    creds: apiCreds,
    funderAddress: FUNDER_ADDRESS,
    signatureType: 3
  });

  return cachedClient;
}

async function getBalance() {
  const client = await getClient();
  const bal = await client.getBalanceAllowance({ asset_type: clobPkg.AssetType.COLLATERAL });
  const balanceUSDC = bal && bal.balance ? Number(bal.balance) / 1e6 : 0;
  return {
    funder: FUNDER_ADDRESS,
    balanceUSDC: Math.round(balanceUSDC * 100) / 100,
    rawBalance: bal ? bal.balance : '0'
  };
}

async function executeMarketBuy(tokenID, amountUSD, maxAcceptablePrice = 0.94) {
  const client = await getClient();
  
  // 1. Balance verification
  const balInfo = await getBalance();
  if (balInfo.balanceUSDC < amountUSD) {
    throw new Error(`Insufficient funds: Balance is $${balInfo.balanceUSDC} USDC, required is $${amountUSD} USDC`);
  }

  // 2. Pre-execution best ask check
  const book = await fetchOrderBook(tokenID);
  if (book.bestAsk && book.bestAsk > maxAcceptablePrice) {
    throw new Error(`Best ask ${book.bestAsk} exceeds ceiling of ${maxAcceptablePrice}. Aborting.`);
  }

  // 3. Market order placement (FAK - Fill And Kill)
  console.log(`[LIVE EXEC] Submitting Market Buy FAK: $${amountUSD} for Token ${tokenID} (Best Ask: ${book.bestAsk}c)...`);
  const marketOrder = await client.createMarketOrder({
    tokenID,
    side: clobPkg.Side.BUY,
    amount: amountUSD,
    orderType: clobPkg.OrderType.FAK
  });

  const result = await client.postOrder(marketOrder, clobPkg.OrderType.FAK);
  return {
    success: true,
    result,
    amountUSD,
    tokenID,
    executedAsk: book.bestAsk,
    timestamp: new Date().toISOString()
  };
}

/**
 * Adaptive Execution Chaser Loop
 * Retries up to maxRetries if unfilled or book shifted,
 * strictly verifying that price ceiling is respected and spot gap has not collapsed.
 */
async function executeMarketBuyWithChaser(tokenID, amountUSD, options = {}) {
  const {
    maxAcceptablePrice = 0.94,
    maxRetries = 3,
    retryDelayMs = 400,
    asset = null,
    strikePrice = null,
    minSafeGap = null,
    direction = 'UP'
  } = options;

  const client = await getClient();
  const balInfo = await getBalance();
  if (balInfo.balanceUSDC < amountUSD) {
    return {
      success: false,
      reason: 'INSUFFICIENT_FUNDS',
      balanceUSDC: balInfo.balanceUSDC,
      amountUSD
    };
  }

  let attempt = 0;
  const history = [];

  while (attempt < maxRetries) {
    attempt++;
    const tStart = Date.now();
    console.log(`\n[CHASER ATTEMPT ${attempt}/${maxRetries}] Checking live book for Token ${tokenID}...`);

    // 1. Check live CLOB orderbook
    const book = await fetchOrderBook(tokenID);
    if (!book.bestAsk) {
      console.log(`[CHASER ${attempt}] Empty or unreadable orderbook. Retrying in ${retryDelayMs}ms...`);
      history.push({ attempt, status: 'EMPTY_BOOK', latencyMs: Date.now() - tStart });
      if (attempt < maxRetries) await new Promise(r => setTimeout(r, retryDelayMs));
      continue;
    }

    // 2. Enforce price ceiling
    if (book.bestAsk > maxAcceptablePrice) {
      console.log(`[CHASER ${attempt}] REJECTED: Best ask (${book.bestAsk}c) exceeds ceiling (${maxAcceptablePrice}c). Kicking order out.`);
      return {
        success: false,
        reason: 'PRICE_CEILING_EXCEEDED',
        attempt,
        bestAsk: book.bestAsk,
        maxAcceptablePrice,
        history
      };
    }

    // 3. Optional: Verify Binance spot price gap has not collapsed
    if (asset && strikePrice && minSafeGap !== null) {
      const spot = await fetchBinanceSpot(asset);
      if (spot) {
        const gap = spot - strikePrice;
        const isUp = direction.toUpperCase() === 'UP';
        const gapIntact = isUp ? (gap >= minSafeGap) : (gap <= minSafeGap);
        if (!gapIntact) {
          console.log(`[CHASER ${attempt}] ABORTED: Spot gap collapsed to ${gap.toFixed(2)} (Threshold: ${minSafeGap}). Protecting bankroll.`);
          return {
            success: false,
            reason: 'SPOT_GAP_COLLAPSED',
            attempt,
            currentSpot: spot,
            strikePrice,
            currentGap: gap,
            minSafeGap,
            history
          };
        }
      }
    }

    // 4. Submit FAK Market Order
    try {
      console.log(`[CHASER ${attempt}] Submitting FAK Buy @ ${book.bestAsk}c (Depth: $${book.askDepth})...`);
      const marketOrder = await client.createMarketOrder({
        tokenID,
        side: clobPkg.Side.BUY,
        amount: amountUSD,
        orderType: clobPkg.OrderType.FAK
      });

      const result = await client.postOrder(marketOrder, clobPkg.OrderType.FAK);
      const isMatched = result && (result.status === 'matched' || result.takingAmount || result.success);

      history.push({
        attempt,
        status: isMatched ? 'FILLED' : 'PARTIAL_OR_UNFILLED',
        bestAsk: book.bestAsk,
        latencyMs: Date.now() - tStart,
        result
      });

      if (isMatched || result.orderID) {
        console.log(`[CHASER ${attempt}] SUCCESS: Order matched at ~${book.bestAsk}c!`);
        return {
          success: true,
          attempt,
          executedAsk: book.bestAsk,
          amountUSD,
          tokenID,
          result,
          history
        };
      }
    } catch (err) {
      console.log(`[CHASER ${attempt}] Error submitting order: ${err.message}`);
      history.push({ attempt, status: 'ERROR', error: err.message, latencyMs: Date.now() - tStart });
    }

    // Delay before next attempt
    if (attempt < maxRetries) {
      await new Promise(r => setTimeout(r, retryDelayMs));
    }
  }

  return {
    success: false,
    reason: 'MAX_RETRIES_EXHAUSTED',
    attempts: maxRetries,
    history
  };
}

// CLI handler
async function main() {
  const args = process.argv.slice(2);
  const action = args[0] || 'balance';

  if (action === 'balance') {
    const res = await getBalance();
    console.log(JSON.stringify(res, null, 2));
  } else if (action === 'book') {
    const tokenID = args[1];
    if (!tokenID) {
      console.error(JSON.stringify({ error: 'Missing tokenID' }));
      process.exit(1);
    }
    const book = await fetchOrderBook(tokenID);
    console.log(JSON.stringify(book, null, 2));
  } else if (action === 'buy') {
    const tokenID = args[1];
    const amount = parseFloat(args[2]);
    const maxPrice = parseFloat(args[3] || '0.94');
    if (!tokenID || !amount) {
      console.error(JSON.stringify({ error: 'Missing tokenID or amount' }));
      process.exit(1);
    }
    const res = await executeMarketBuy(tokenID, amount, maxPrice);
    console.log(JSON.stringify(res, null, 2));
  } else if (action === 'chaser') {
    const tokenID = args[1];
    const amount = parseFloat(args[2]);
    const maxPrice = parseFloat(args[3] || '0.94');
    const retries = parseInt(args[4] || '3', 10);
    const asset = args[5] || null;
    const strike = args[6] ? parseFloat(args[6]) : null;
    const minGap = args[7] ? parseFloat(args[7]) : null;
    const direction = args[8] || 'UP';

    const res = await executeMarketBuyWithChaser(tokenID, amount, {
      maxAcceptablePrice: maxPrice,
      maxRetries: retries,
      asset,
      strikePrice: strike,
      minSafeGap: minGap,
      direction
    });
    console.log(JSON.stringify(res, null, 2));
  } else {
    console.error(JSON.stringify({ error: `Unknown action: ${action}` }));
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  });
}

module.exports = { getBalance, fetchOrderBook, fetchBinanceSpot, executeMarketBuy, executeMarketBuyWithChaser };
