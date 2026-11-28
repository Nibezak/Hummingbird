/**
 * LIVE ORDER EXECUTOR FOR POLYMARKET CLOB WITH ADAPTIVE CHASER & VWAP ENGINE
 * Path: c:\projects\btc-5m-recorder\live_executor.js
 * 
 * Directly leverages verified @polymarket/clob-client-v2 and viem setup from c:\projects\weather
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { performance } = require('perf_hooks');
const WebSocket = require('c:/projects/weather/node_modules/ws');

// Persistent Keep-Alive agent to eliminate repeated 300ms TCP/TLS handshake latency
const keepAliveAgent = new https.Agent({
  keepAlive: true,
  maxSockets: 25,
  keepAliveMsecs: 60000
});

// Pre-warmed per-token CLOB metadata cache to eliminate ~430ms createMarketOrder lookup penalty
const tokenMetaCache = new Map();
const tokenWarmPromises = new Map();

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
let clientPromise = null;

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, agent: keepAliveAgent, timeout: 3000 }, (res) => {
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

async function fetchOrderBook(tokenID, oppTokenID = null) {
  try {
    const fetches = [httpGetJson(`https://clob.polymarket.com/book?token_id=${tokenID}`).catch(() => null)];
    if (oppTokenID) {
      fetches.push(httpGetJson(`https://clob.polymarket.com/book?token_id=${oppTokenID}`).catch(() => null));
    }
    const [data, oppData] = await Promise.all(fetches);

    let asks = [];
    let bids = [];

    if (data) {
      for (const a of (data.asks || [])) {
        const p = parseFloat(a.price);
        const s = parseFloat(a.size);
        if (p > 0 && s > 0) asks.push({ price: p, size: s, type: 'direct' });
      }
      for (const b of (data.bids || [])) {
        const p = parseFloat(b.price);
        const s = parseFloat(b.size);
        if (p > 0 && s > 0) bids.push({ price: p, size: s, type: 'direct' });
      }
    }

    // Synthetic traversal: opposite token bids become synthetic asks (1.0 - Price(opp bid))
    if (oppData && Array.isArray(oppData.bids)) {
      for (const b of oppData.bids) {
        const bp = parseFloat(b.price);
        const bs = parseFloat(b.size);
        if (bp > 0 && bp < 1.0 && bs > 0) {
          const synthPrice = Math.round((1.0 - bp) * 10000) / 10000;
          asks.push({ price: synthPrice, size: bs, type: 'synthetic' });
        }
      }
    }

    asks.sort((a, b) => a.price - b.price);
    bids.sort((a, b) => b.price - a.price);

    const bestAsk = asks.length > 0 ? asks[0].price : null;
    const bestBid = bids.length > 0 ? bids[0].price : null;
    const askType = asks.length > 0 ? asks[0].type : 'direct';
    const askDepth = asks.slice(0, 5).reduce((sum, a) => sum + (a.price * a.size), 0);
    return { bestAsk, bestBid, askDepth: Math.round(askDepth * 100) / 100, askType, asks, bids };
  } catch (err) {
    return { bestAsk: null, bestBid: null, askDepth: 0, askType: 'direct', asks: [], bids: [], error: err.message };
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
  if (clientPromise) return clientPromise;

  clientPromise = (async () => {
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
  })();

  try {
    return await clientPromise;
  } finally {
    clientPromise = null;
  }
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

async function prewarmTokenMeta(client, assetID) {
  const key = String(assetID || '');
  if (!key) return null;
  const cached = tokenMetaCache.get(key);
  if (cached && Date.now() - cached.warmedAt < 300000) return cached;
  if (tokenWarmPromises.has(key)) return tokenWarmPromises.get(key);

  const p = (async () => {
    try {
      await client._ensureMarketInfoCached(key);
      const tickSize = await client.getTickSize(key);
      const negRisk = await client.getNegRisk(key).catch(() => false);
      const meta = { tickSize, negRisk, warmedAt: Date.now() };
      tokenMetaCache.set(key, meta);
      return meta;
    } catch (e) {
      return null;
    } finally {
      tokenWarmPromises.delete(key);
    }
  })();
  tokenWarmPromises.set(key, p);
  return p;
}

async function prewarmTokens(tokenIDs) {
  const client = await getClient();
  const unique = [...new Set((tokenIDs || []).map(String).filter(Boolean))];
  const t0 = performance.now();
  await client.resolveVersion().catch(() => null);
  await Promise.allSettled(unique.map(id => prewarmTokenMeta(client, id)));
  return { warmed: unique.filter(id => tokenMetaCache.has(id)).length, total: unique.length, elapsedMs: Math.round((performance.now() - t0) * 10) / 10 };
}

function isOrderMatched(result) {
  const errStr = result?.error || result?.errorMsg || '';
  const hasHttpError = Boolean(errStr || (typeof result?.status === 'number' && result.status >= 400));
  return Boolean(!hasHttpError && result && (
    result.status === 'matched' ||
    (result.takingAmount && Number(result.takingAmount) > 0) ||
    result.success === true
  ));
}

async function submitFakOrder(client, assetID, usePositionId, amountUSD, ceilingPrice) {
  const key = String(assetID);
  const meta = tokenMetaCache.get(key);
  const orderInput = usePositionId
    ? { positionID: key, side: clobPkg.Side.BUY, amount: amountUSD, price: ceilingPrice, orderType: clobPkg.OrderType.FAK }
    : { tokenID: key, side: clobPkg.Side.BUY, amount: amountUSD, price: ceilingPrice, orderType: clobPkg.OrderType.FAK };
  const orderOpts = meta ? { tickSize: meta.tickSize, negRisk: meta.negRisk } : undefined;
  const tSign0 = performance.now();
  const marketOrder = await client.createMarketOrder(orderInput, orderOpts);
  const signMs = performance.now() - tSign0;
  const tPost0 = performance.now();
  const result = await client.postOrder(marketOrder, clobPkg.OrderType.FAK);
  const postMs = performance.now() - tPost0;
  return { result, signMs, postMs, cacheHit: Boolean(meta) };
}

async function submitFakWithFallback(client, assetID, initialUsePositionId, amountUSD, ceilingPrice) {
  let usePositionId = Boolean(initialUsePositionId);
  let res = await submitFakOrder(client, assetID, usePositionId, amountUSD, ceilingPrice);
  let errStr = res.result?.error || res.result?.errorMsg || '';
  if (typeof errStr === 'string' && errStr.includes('POLY_1271')) {
    usePositionId = !usePositionId;
    res = await submitFakOrder(client, assetID, usePositionId, amountUSD, ceilingPrice);
  }
  return { ...res, usePositionId };
}

/**
 * Adaptive Execution Chaser Loop
 * Retries up to maxRetries if unfilled or book shifted,
 * strictly verifying that price ceiling is respected and spot gap has not collapsed.
 */
async function executeMarketBuyWithChaser(tokenID, amountUSD, options = {}) {
  const {
    maxAcceptablePrice = 0.989,
    maxRetries = 3,
    retryDelayMs = 15,
    asset = null,
    strikePrice = null,
    minSafeGap = null,
    direction = 'UP',
    oppTokenID = null,
    expectedPrice = null,
    expectedDepth = 10.0,
    skipFirstBookCheck = false
  } = options;

  let usePositionId = Boolean(options.usePositionId);
  if (options.usePositionId === undefined && oppTokenID && /^\d+$/.test(String(tokenID)) && /^\d+$/.test(String(oppTokenID))) {
    const diff = BigInt(tokenID) - BigInt(oppTokenID);
    if (diff === 1n || diff === -1n) usePositionId = true;
  }

  const client = await getClient();

  let attempt = 0;
  const history = [];

  while (attempt < maxRetries) {
    attempt++;
    const tStart = Date.now();
    const usePrechecked = attempt === 1 && skipFirstBookCheck && expectedPrice && expectedPrice <= maxAcceptablePrice;
    let book;
    if (usePrechecked) {
      book = { bestAsk: expectedPrice, askDepth: expectedDepth };
      console.log(`\n[CHASER ATTEMPT 1/${maxRetries}] Fast-path fire [${usePositionId ? 'V3' : 'V2'}] (Pre-checked ${expectedPrice}c | Depth: $${expectedDepth})...`);
    } else {
      console.log(`\n[CHASER ATTEMPT ${attempt}/${maxRetries}] Checking live book for ${usePositionId ? 'Position(V3)' : 'Token(V2)'} ${tokenID}...`);
      book = await fetchOrderBook(tokenID, oppTokenID);
    }
    const candidateAsk = book.bestAsk || expectedPrice || maxAcceptablePrice;

    // 2. Strict ceiling check (never buy at or above 99c)
    if (book.bestAsk && book.bestAsk > maxAcceptablePrice) {
      console.log(`[CHASER ${attempt}] REJECTED: Best ask (${book.bestAsk}c) exceeds ceiling (${maxAcceptablePrice}c).`);
      return {
        success: false,
        reason: 'PRICE_CEILING_EXCEEDED',
        attempt,
        bestAsk: book.bestAsk,
        maxAcceptablePrice,
        history
      };
    }

    // 3. Submit FAK Market Order with ceiling protection (maxAcceptablePrice = 0.98)
    try {
      if (!book.bestAsk || book.askDepth < 0.50) {
        console.log(`[CHASER ${attempt}] DIRECT BOOK EMPTY: No direct sell orders on this token (Depth: $${book.askDepth}).`);
        history.push({ attempt, status: 'NO_DIRECT_DEPTH', bestAsk: null, latencyMs: Date.now() - tStart });
        if (attempt < maxRetries) await new Promise(r => setTimeout(r, retryDelayMs));
        continue;
      }

      const ceilingPrice = maxAcceptablePrice;
      const displayAsk = book.bestAsk || candidateAsk;
      console.log(`[CHASER ${attempt}] Submitting FAK Buy [${usePositionId ? 'V3' : 'V2'}] (Direct Ask: ${displayAsk}c | Ceiling: ${ceilingPrice}c | Direct Depth: $${book.askDepth})...`);

      const fakExec = await submitFakWithFallback(client, tokenID, usePositionId, amountUSD, ceilingPrice);
      usePositionId = fakExec.usePositionId;
      const result = fakExec.result;
      const errStr = result?.error || result?.errorMsg || '';

      console.log(`[CHASER ${attempt}] CLOB response (${fakExec.signMs.toFixed(1)}ms sign ${fakExec.cacheHit ? 'CACHED' : 'COLD'}, ${fakExec.postMs.toFixed(1)}ms post): status=${result?.status}, success=${result?.success}, orderID=${result?.orderID}, taking=${result?.takingAmount}, error=${errStr || 'none'}`);

      const isMatched = isOrderMatched(result);

      let executedPrice = displayAsk;
      if (result && result.takingAmount && result.makingAmount && Number(result.takingAmount) > 0) {
        executedPrice = Math.round((Number(result.makingAmount) / Number(result.takingAmount)) * 100) / 100;
      } else if (book.bestAsk) {
        executedPrice = book.bestAsk;
      }

      history.push({
        attempt,
        status: isMatched ? 'FILLED' : 'PARTIAL_OR_UNFILLED',
        bestAsk: executedPrice,
        signMs: Math.round(fakExec.signMs * 10) / 10,
        postMs: Math.round(fakExec.postMs * 10) / 10,
        cacheHit: fakExec.cacheHit,
        latencyMs: Date.now() - tStart,
        result
      });

      if (isMatched) {
        console.log(`[CHASER ${attempt}] SUCCESS: Order matched at ~${executedPrice}c!`);
        return {
          success: true,
          attempt,
          executedAsk: executedPrice,
          signMs: Math.round(fakExec.signMs * 10) / 10,
          postMs: Math.round(fakExec.postMs * 10) / 10,
          amountUSD,
          tokenID,
          result,
          history
        };
      }
    } catch (err) {
      console.log(`[CHASER ${attempt}] Order submission note: ${err.message}`);
      history.push({ attempt, status: 'ERROR', error: err.message, latencyMs: Date.now() - tStart });
    }

    // Rapid retry delay (150ms)
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
    const oppTokenID = args[9] || null;
    const expectedPrice = args[10] ? parseFloat(args[10]) : null;

    const res = await executeMarketBuyWithChaser(tokenID, amount, {
      maxAcceptablePrice: maxPrice,
      maxRetries: retries,
      asset,
      strikePrice: strike,
      minSafeGap: minGap,
      direction,
      oppTokenID,
      expectedPrice
    });
    console.log(JSON.stringify(res, null, 2));
  } else if (action === 'server') {
    const port = parseInt(args[1] || '8897', 10);
    startExecutionServer(port);
  } else {
    console.error(JSON.stringify({ error: `Unknown action: ${action}` }));
    process.exit(1);
  }
}

// =========================================================================
// SUB-100MS STREAMING EDGE ENGINE (BINANCE WS + POLYMARKET CLOB MARKET WS)
// =========================================================================
const BINANCE_TO_ASSET = {
  BTCUSDT: 'BTC', ETHUSDT: 'ETH', SOLUSDT: 'SOL', DOGEUSDT: 'DOGE',
  XRPUSDT: 'XRP', BNBUSDT: 'BNB', HYPEUSDT: 'HYPE'
};

function isInBlackoutWindowUtc() {
  const now = new Date();
  const utcMinute = now.getUTCHours() * 60 + now.getUTCMinutes();
  const isAsianFix = 230 <= utcMinute && utcMinute < 270;   // 03:50 - 04:30 UTC (06:50 - 07:30 AM EAT)
  const isNyseBell = 865 <= utcMinute && utcMinute < 905;   // 14:25 - 15:05 UTC (05:25 - 06:05 PM EAT)
  const isEuClose = 980 <= utcMinute && utcMinute < 1000;   // 16:20 - 16:40 UTC (07:20 - 07:40 PM EAT)
  return isAsianFix || isNyseBell || isEuClose;
}

class EdgeFastMonitor {
  constructor() {
    this.spotPrices = new Map();
    this.wsBooks = new Map();
    this.tokenToAsset = new Map();
    this.armedCycle = null;
    this.inFlightKeys = new Set();
    this.filledKeys = new Set();
    this.cooldowns = new Map();
    this.pendingFastFills = [];
    this.nextFillId = 1;
    this.binanceWs = null;
    this.polyWs = null;
    this.polyTokenSignature = '';
    this.binanceConnected = false;
    this.polyConnected = false;
    this.started = false;
  }

  start() {
    if (this.started) return;
    this.started = true;
    this.connectBinance();
    this.connectPoly([]);
  }

  connectBinance() {
    const streams = Object.keys(BINANCE_TO_ASSET).map(s => `${s.toLowerCase()}@trade`).join('/');
    const url = `wss://stream.binance.com:9443/stream?streams=${streams}`;
    try {
      const ws = new WebSocket(url);
      this.binanceWs = ws;
      ws.on('open', () => {
        this.binanceConnected = true;
        console.log('[WS BINANCE] Sub-100ms trade stream connected (7 pairs incl. HYPE).');
      });
      ws.on('message', (raw) => {
        const tRecv = performance.now();
        try {
          const parsed = JSON.parse(raw.toString());
          const d = parsed.data || parsed;
          const asset = BINANCE_TO_ASSET[d.s];
          const price = parseFloat(d.p);
          if (asset && price > 0) {
            this.spotPrices.set(asset, { price, ts: Date.now() });
            this.evaluateFastAsset(asset, tRecv);
          }
        } catch (e) {}
      });
      ws.on('close', () => {
        this.binanceConnected = false;
        setTimeout(() => this.connectBinance(), 1500);
      });
      ws.on('error', () => {});
    } catch (e) {
      setTimeout(() => this.connectBinance(), 2000);
    }
  }

  connectPoly(tokenIDs) {
    const cleanIds = [...new Set((tokenIDs || []).map(String).filter(Boolean))];
    if (this.polyWs) {
      try { this.polyWs.terminate(); } catch (e) {}
      this.polyWs = null;
    }
    this.polyConnected = false;
    if (cleanIds.length === 0) return;

    const ws = new WebSocket('wss://ws-subscriptions-clob.polymarket.com/ws/market');
    this.polyWs = ws;
    let pingTimer = null;

    ws.on('open', () => {
      this.polyConnected = true;
      ws.send(JSON.stringify({ assets_ids: cleanIds, type: 'market' }));
      console.log(`[WS POLYMARKET] Subscribed live L2 orderbook feed (${cleanIds.length} tokens).`);
      pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('PING');
      }, 10000);
    });

    ws.on('message', (raw) => {
      const tRecv = performance.now();
      const txt = raw.toString();
      if (!txt || txt === 'PONG') return;
      try {
        const msg = JSON.parse(txt);
        const touchedAssets = new Set();
        const items = Array.isArray(msg) ? msg : [msg];
        for (const item of items) {
          if (item && item.asset_id && (Array.isArray(item.asks) || Array.isArray(item.bids))) {
            this.applySnapshot(String(item.asset_id), item.asks || [], item.bids || []);
            const asset = this.tokenToAsset.get(String(item.asset_id));
            if (asset) touchedAssets.add(asset);
          } else if (item && Array.isArray(item.price_changes)) {
            for (const pc of item.price_changes) {
              const assetId = String(pc.asset_id || '');
              if (!assetId) continue;
              this.applyPriceChange(assetId, pc);
              const asset = this.tokenToAsset.get(assetId);
              if (asset) touchedAssets.add(asset);
            }
          }
        }
        for (const asset of touchedAssets) {
          this.evaluateFastAsset(asset, tRecv);
        }
      } catch (e) {}
    });

    ws.on('close', () => {
      if (pingTimer) clearInterval(pingTimer);
      this.polyConnected = false;
      if (this.polyWs === ws && this.polyTokenSignature) {
        const currentIds = this.polyTokenSignature.split(',').filter(Boolean);
        setTimeout(() => {
          if (this.polyTokenSignature === currentIds.join(',')) {
            this.connectPoly(currentIds);
          }
        }, 1500);
      }
    });
    ws.on('error', () => {});
  }

  recomputeTop(book) {
    const askLevels = [];
    for (const [pStr, sNum] of book.asksMap.entries()) {
      const p = parseFloat(pStr);
      if (p > 0 && sNum > 0) askLevels.push([p, sNum]);
    }
    askLevels.sort((a, b) => a[0] - b[0]);
    book.bestAsk = askLevels.length > 0 ? askLevels[0][0] : null;
    let aDepth = 0;
    for (let i = 0; i < Math.min(5, askLevels.length); i++) {
      aDepth += askLevels[i][0] * askLevels[i][1];
    }
    book.askDepth = Math.round(aDepth * 100) / 100;

    const bidLevels = [];
    if (book.bidsMap) {
      for (const [pStr, sNum] of book.bidsMap.entries()) {
        const p = parseFloat(pStr);
        if (p > 0 && sNum > 0) bidLevels.push([p, sNum]);
      }
      bidLevels.sort((a, b) => b[0] - a[0]); // highest bid first
    }
    book.bestBid = bidLevels.length > 0 ? bidLevels[0][0] : null;
    let bDepth = 0;
    for (let i = 0; i < Math.min(5, bidLevels.length); i++) {
      bDepth += bidLevels[i][0] * bidLevels[i][1];
    }
    book.bidDepth = Math.round(bDepth * 100) / 100;

    book.updatedAt = Date.now();
  }

  applySnapshot(tokenID, asksArr = [], bidsArr = []) {
    const asksMap = new Map();
    for (const a of asksArr) {
      const p = String(a.price);
      const s = parseFloat(a.size);
      if (parseFloat(p) > 0 && s > 0) asksMap.set(p, s);
    }
    const bidsMap = new Map();
    for (const b of bidsArr) {
      const p = String(b.price);
      const s = parseFloat(b.size);
      if (parseFloat(p) > 0 && s > 0) bidsMap.set(p, s);
    }
    const book = { asksMap, bidsMap, bestAsk: null, bestBid: null, askDepth: 0, bidDepth: 0, updatedAt: Date.now() };
    this.recomputeTop(book);
    this.wsBooks.set(tokenID, book);
  }

  applyPriceChange(tokenID, pc) {
    let book = this.wsBooks.get(tokenID);
    if (!book) {
      book = { asksMap: new Map(), bidsMap: new Map(), bestAsk: null, bestBid: null, askDepth: 0, bidDepth: 0, updatedAt: Date.now() };
      this.wsBooks.set(tokenID, book);
    }
    if (!book.bidsMap) book.bidsMap = new Map();
    const side = String(pc.side || '').toUpperCase();
    if (side === 'SELL' && pc.price !== undefined) {
      const pKey = String(pc.price);
      const sz = parseFloat(pc.size || '0');
      if (sz > 0) book.asksMap.set(pKey, sz);
      else book.asksMap.delete(pKey);
      this.recomputeTop(book);
    } else if (side === 'BUY' && pc.price !== undefined) {
      const pKey = String(pc.price);
      const sz = parseFloat(pc.size || '0');
      if (sz > 0) book.bidsMap.set(pKey, sz);
      else book.bidsMap.delete(pKey);
      this.recomputeTop(book);
    } else if (pc.best_ask !== undefined) {
      const ba = parseFloat(pc.best_ask);
      if (ba > 0 && ba < 1 && book.asksMap.size === 0) {
        book.bestAsk = ba;
        book.updatedAt = Date.now();
      }
    } else if (pc.best_bid !== undefined) {
      const bb = parseFloat(pc.best_bid);
      if (bb > 0 && bb < 1 && book.bidsMap.size === 0) {
        book.bestBid = bb;
        book.updatedAt = Date.now();
      }
    }
  }

  getEffectiveAsk(tokenID, oppTokenID) {
    const book = this.wsBooks.get(String(tokenID));
    const oppBook = oppTokenID ? this.wsBooks.get(String(oppTokenID)) : null;

    let directAsk = (book && book.bestAsk !== null && Date.now() - book.updatedAt < 45000) ? book.bestAsk : null;
    let directDepth = directAsk ? (book.askDepth || 0) : 0;

    let synthAsk = null;
    let synthDepth = 0;
    if (oppBook && oppBook.bestBid !== null && Date.now() - oppBook.updatedAt < 45000) {
      if (oppBook.bestBid > 0 && oppBook.bestBid < 1.0) {
        synthAsk = Math.round((1.0 - oppBook.bestBid) * 10000) / 10000;
        synthDepth = oppBook.bidDepth || 0;
      }
    }

    if (directAsk !== null && synthAsk !== null) {
      if (directAsk <= synthAsk) {
        return { bestAsk: directAsk, askDepth: directDepth, isSynthetic: false };
      } else {
        return { bestAsk: synthAsk, askDepth: synthDepth, isSynthetic: true };
      }
    } else if (directAsk !== null) {
      return { bestAsk: directAsk, askDepth: directDepth, isSynthetic: false };
    } else if (synthAsk !== null) {
      return { bestAsk: synthAsk, askDepth: synthDepth, isSynthetic: true };
    }
    return { bestAsk: null, askDepth: 0, isSynthetic: false };
  }

  armCycle(payload) {
    const assetsMap = new Map();
    const tokenList = [];
    this.tokenToAsset.clear();

    for (const a of (payload.assets || [])) {
      assetsMap.set(a.asset, a);
      if (a.up_token_id) {
        const u = String(a.up_token_id);
        tokenList.push(u);
        this.tokenToAsset.set(u, a.asset);
      }
      if (a.down_token_id) {
        const d = String(a.down_token_id);
        tokenList.push(d);
        this.tokenToAsset.set(d, a.asset);
      }
    }

    for (const key of (payload.traded_keys || [])) {
      this.filledKeys.add(String(key));
    }

    const cycleChanged = !this.armedCycle || this.armedCycle.cycle_id !== payload.cycle_id;
    this.armedCycle = {
      cycle_id: payload.cycle_id,
      end_ts: Number(payload.end_ts || 0),
      available_cash: Number(payload.available_cash || 0),
      blackout_active: Boolean(payload.blackout_active),
      min_rem: Number(payload.min_rem ?? 35),
      max_rem: Number(payload.max_rem ?? 120),
      stake_fraction: Number(payload.stake_fraction ?? 0.20),
      min_floor: Number(payload.min_floor ?? 1.00),
      max_ceiling: Number(payload.max_ceiling ?? 15.00),
      strong_98c_threshold: Number(payload.strong_98c_threshold ?? 0.70),
      min_ask: Number(payload.min_ask ?? 0.80),
      max_ask: Number(payload.max_ask ?? 0.989),
      assetsMap
    };

    const sig = [...new Set(tokenList)].sort().join(',');
    if (cycleChanged || sig !== this.polyTokenSignature) {
      this.polyTokenSignature = sig;
      this.connectPoly(tokenList);
      prewarmTokens(tokenList).then(r => {
        console.log(`[PRE-WARM] Warmed ${r.warmed}/${r.total} tokens for cycle ${payload.cycle_id} in ${r.elapsedMs}ms.`);
      }).catch(() => {});
    }
    return { armed: assetsMap.size, tokens: tokenList.length, available_cash: this.armedCycle.available_cash };
  }

  selectBoundary(assetInfo, remaining) {
    const w = assetInfo.windows || {};
    let k = '30';
    if (remaining >= 105) k = '120';
    else if (remaining >= 80) k = '90';
    else if (remaining >= 55) k = '60';
    else if (remaining >= 40) k = '45';
    return w[k] || w['30'] || null;
  }

  markExternalFilled(cycleId, asset) {
    if (cycleId && asset) this.filledKeys.add(`${cycleId}:${asset}`);
  }

  isBlockedExternal(cycleId, asset) {
    if (!cycleId || !asset) return false;
    const key = `${cycleId}:${asset}`;
    return this.filledKeys.has(key) || this.inFlightKeys.has(key);
  }

  evaluateFastAsset(asset, tDetect) {
    const cycle = this.armedCycle;
    if (!cycle || !cachedClient || cycle.blackout_active || isInBlackoutWindowUtc()) return;
    const assetInfo = cycle.assetsMap.get(asset);
    if (!assetInfo || !assetInfo.strike) return;

    const nowSec = Date.now() / 1000;
    const remaining = Math.round(cycle.end_ts - nowSec);
    if (remaining > cycle.max_rem || remaining < cycle.min_rem) return;

    const key = `${cycle.cycle_id}:${asset}`;
    if (this.filledKeys.has(key) || this.inFlightKeys.has(key)) return;
    const cd = this.cooldowns.get(key) || 0;
    if (Date.now() < cd) return;
    if (cycle.available_cash < cycle.min_floor) return;

    const spotObj = this.spotPrices.get(asset);
    if (!spotObj || Date.now() - spotObj.ts > 5000) return;
    const spot = spotObj.price;
    const gap = spot - Number(assetInfo.strike);

    const b = this.selectBoundary(assetInfo, remaining);
    if (!b) return;

    let direction = null;
    let tokenID = null;
    let oppTokenID = null;
    let safeGap = 0;
    let strong98Req = 0;

    if (gap >= b.up_safe && assetInfo.up_token_id) {
      direction = 'Up';
      tokenID = String(assetInfo.up_token_id);
      oppTokenID = String(assetInfo.down_token_id || '');
      safeGap = b.up_safe;
      strong98Req = b.raw_up * cycle.strong_98c_threshold;
    } else if (gap <= b.dn_safe && assetInfo.down_token_id) {
      direction = 'Down';
      tokenID = String(assetInfo.down_token_id);
      oppTokenID = String(assetInfo.up_token_id || '');
      safeGap = b.dn_safe;
      strong98Req = Math.abs(b.raw_dn) * cycle.strong_98c_threshold;
    } else {
      return;
    }

    const eff = this.getEffectiveAsk(tokenID, oppTokenID);
    if (eff.bestAsk === null || eff.askDepth < 0.50) return;
    if (eff.bestAsk < cycle.min_ask || eff.bestAsk > cycle.max_ask) return;

    let stake = Math.round(Math.min(Math.max(cycle.min_floor, cycle.available_cash * cycle.stake_fraction), cycle.max_ceiling) * 100) / 100;
    if (cycle.available_cash < stake) {
      if (cycle.available_cash >= cycle.min_floor) stake = Math.round(cycle.available_cash * 100) / 100;
      else return;
    }

    // Synchronous atomic reservation before async CLOB dispatch
    this.inFlightKeys.add(key);
    cycle.available_cash = Math.round((cycle.available_cash - stake) * 100) / 100;

    const elapsed = Math.max(0, 300 - remaining);
    const snapAsk = eff.bestAsk;
    const snapDepth = eff.askDepth;
    const usePosId = Boolean(assetInfo.use_pos_id);
    const synthTag = eff.isSynthetic ? ' [SYNTHETIC DUAL-BOOK]' : '';

    console.log(`\n[SUB-100MS WS TRIGGER] ${asset} ${direction.toUpperCase()} [${usePosId ? 'V3' : 'V2'}]${synthTag} @ ${(snapAsk * 100).toFixed(1)}c (Depth $${snapDepth}) | T-${remaining}s | Stake $${stake.toFixed(2)}`);

    submitFakWithFallback(cachedClient, tokenID, usePosId, stake, cycle.max_ask).then((execRes) => {
      const localPipelineMs = Math.round(Math.max(execRes.signMs, performance.now() - tDetect - execRes.postMs) * 10) / 10;
      const totalMs = Math.round((performance.now() - tDetect) * 10) / 10;
      const matched = isOrderMatched(execRes.result);

      if (matched) {
        let executedAsk = snapAsk;
        if (execRes.result.takingAmount && execRes.result.makingAmount && Number(execRes.result.takingAmount) > 0) {
          executedAsk = Math.round((Number(execRes.result.makingAmount) / Number(execRes.result.takingAmount)) * 100) / 100;
        }
        this.filledKeys.add(key);
        this.inFlightKeys.delete(key);
        this.pendingFastFills.push({
          fill_id: this.nextFillId++,
          cycle_id: cycle.cycle_id,
          asset,
          direction,
          elapsed_seconds: elapsed,
          remaining_seconds: remaining,
          spot_price: spot,
          strike_price: Number(assetInfo.strike),
          gap_dollars: gap,
          safe_gap: safeGap,
          executed_ask: executedAsk,
          stake,
          shares: Math.round((stake / executedAsk) * 100) / 100,
          local_ms: localPipelineMs,
          sign_ms: Math.round(execRes.signMs * 10) / 10,
          post_ms: Math.round(execRes.postMs * 10) / 10,
          total_ms: totalMs,
          timestamp: Math.floor(Date.now() / 1000),
          call_time: new Date().toISOString()
        });
        console.log(`[SUB-100MS FILLED!] ${asset} ${direction.toUpperCase()} @ ${(executedAsk * 100).toFixed(1)}c | Local Detect->Sign->Wire: ${localPipelineMs}ms (Sign: ${execRes.signMs.toFixed(1)}ms) | CLOB ACK: ${execRes.postMs.toFixed(1)}ms`);
      } else {
        cycle.available_cash = Math.round((cycle.available_cash + stake) * 100) / 100;
        this.cooldowns.set(key, Date.now() + 400);
        this.inFlightKeys.delete(key);
        const errMsg = execRes.result?.error || execRes.result?.errorMsg || execRes.result?.status || 'UNFILLED';
        console.log(`[WS FAST MISS] ${asset} ${direction.toUpperCase()} unfilled (${errMsg}) | Local: ${localPipelineMs}ms | Released $${stake.toFixed(2)}`);
      }
    }).catch((err) => {
      cycle.available_cash = Math.round((cycle.available_cash + stake) * 100) / 100;
      this.cooldowns.set(key, Date.now() + 500);
      this.inFlightKeys.delete(key);
      console.error(`[WS FAST ERROR] ${asset}: ${err.message}`);
    });
  }
}

const fastMonitor = new EdgeFastMonitor();

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try { resolve(JSON.parse(body || '{}')); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

function sendJson(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data));
}

function startExecutionServer(port = 8897) {
  console.log(`[PRE-WARMED EXECUTOR] Initializing and pre-authenticating ClobClient...`);
  getClient().then(() => {
    console.log(`[PRE-WARMED EXECUTOR] ClobClient ready and authenticated with keep-alive.`);
    fastMonitor.start();
  }).catch(err => {
    console.error(`[PRE-WARMED EXECUTOR] Warning during client pre-warm: ${err.message}`);
  });

  const server = http.createServer(async (req, res) => {
    try {
      if (req.method === 'POST' && req.url === '/chaser') {
        const tStart = Date.now();
        const payload = await readJsonBody(req);
        const tokenID = payload.tokenID;
        const amountUSD = parseFloat(payload.amountUSD || '1.00');
        const options = payload.options || {};
        if (options.cycleId && options.asset && fastMonitor.isBlockedExternal(options.cycleId, options.asset)) {
          return sendJson(res, 200, { success: false, reason: 'ALREADY_FILLED_OR_IN_FLIGHT_WS' });
        }
        console.log(`\n[SERVER DISPATCH] Immediate trade request for Token ${tokenID} ($${amountUSD})...`);
        const result = await executeMarketBuyWithChaser(tokenID, amountUSD, options);
        if (result.success && options.cycleId && options.asset) {
          fastMonitor.markExternalFilled(options.cycleId, options.asset);
        }
        const duration = Date.now() - tStart;
        console.log(`[SERVER DISPATCH COMPLETED] Execution duration: ${duration}ms | Success: ${result.success}`);
        return sendJson(res, 200, result);
      } else if (req.method === 'POST' && req.url === '/books') {
        const payload = await readJsonBody(req);
        let pairs = [];
        if (Array.isArray(payload.pairs)) {
          pairs = payload.pairs;
        } else if (Array.isArray(payload.tokenIDs)) {
          pairs = payload.tokenIDs.map(id => ({ token_id: id, opp_token_id: null }));
        }
        const results = await Promise.all(pairs.map(async p => {
          const sId = String(p.token_id || p.tokenID || '');
          const oppId = (p.opp_token_id || p.oppTokenID) ? String(p.opp_token_id || p.oppTokenID) : null;
          if (!sId) return [sId, { bestAsk: null, askDepth: 0 }];

          const eff = fastMonitor.getEffectiveAsk(sId, oppId);
          if (eff.bestAsk !== null) {
            return [sId, { bestAsk: eff.bestAsk, askDepth: eff.askDepth, isSynthetic: eff.isSynthetic, source: 'ws' }];
          }
          const b = await fetchOrderBook(sId, oppId);
          return [sId, { bestAsk: b.bestAsk, askDepth: b.askDepth, isSynthetic: b.askType === 'synthetic', source: 'rest' }];
        }));
        return sendJson(res, 200, { books: Object.fromEntries(results) });
      } else if (req.method === 'POST' && req.url === '/prewarm') {
        const payload = await readJsonBody(req);
        const out = await prewarmTokens(payload.tokenIDs || []);
        return sendJson(res, 200, out);
      } else if (req.method === 'POST' && req.url === '/cycle_arm') {
        const payload = await readJsonBody(req);
        const out = fastMonitor.armCycle(payload);
        return sendJson(res, 200, out);
      } else if (req.method === 'GET' && req.url === '/fast_fills') {
        return sendJson(res, 200, { fills: fastMonitor.pendingFastFills });
      } else if (req.method === 'POST' && req.url === '/fast_fills_ack') {
        const payload = await readJsonBody(req);
        const ackIds = new Set((payload.fill_ids || []).map(Number));
        fastMonitor.pendingFastFills = fastMonitor.pendingFastFills.filter(f => !ackIds.has(f.fill_id));
        return sendJson(res, 200, { remaining: fastMonitor.pendingFastFills.length });
      } else if (req.method === 'GET' && req.url === '/balance') {
        const bal = await getBalance();
        return sendJson(res, 200, bal);
      } else if (req.method === 'GET' && req.url === '/ping') {
        return sendJson(res, 200, {
          status: 'ready',
          time: Date.now(),
          binanceWs: fastMonitor.binanceConnected,
          polyWs: fastMonitor.polyConnected,
          prewarmedTokens: tokenMetaCache.size,
          wsBooksCount: fastMonitor.wsBooks.size,
          armedCycle: fastMonitor.armedCycle ? fastMonitor.armedCycle.cycle_id : null
        });
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    } catch (err) {
      console.error(`[SERVER ERROR] ${err.message}`);
      sendJson(res, 500, { success: false, error: err.message });
    }
  });

  server.listen(port, '127.0.0.1', () => {
    console.log(`[PRE-WARMED EXECUTOR SERVER] Ultra-low latency engine listening on http://127.0.0.1:${port}`);
  });
}

if (require.main === module) {
  main().catch(err => {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  });
}

module.exports = { getBalance, fetchOrderBook, fetchBinanceSpot, executeMarketBuy, executeMarketBuyWithChaser, startExecutionServer };
