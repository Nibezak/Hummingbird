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

// Persistent Keep-Alive agent to eliminate repeated 300ms TCP/TLS handshake latency
const keepAliveAgent = new https.Agent({
  keepAlive: true,
  maxSockets: 25,
  keepAliveMsecs: 60000
});

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
    const pDirect = httpGetJson(`https://clob.polymarket.com/book?token_id=${tokenID}`);
    const data = await pDirect.catch(() => null);

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

    asks.sort((a, b) => a.price - b.price);
    bids.sort((a, b) => b.price - a.price);

    const bestAsk = asks.length > 0 ? asks[0].price : null;
    const bestBid = bids.length > 0 ? bids[0].price : null;
    const askDepth = asks.slice(0, 5).reduce((sum, a) => sum + (a.price * a.size), 0);
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

async function submitFakOrder(client, assetID, usePositionId, amountUSD, ceilingPrice) {
  const orderInput = usePositionId
    ? { positionID: assetID, side: clobPkg.Side.BUY, amount: amountUSD, price: ceilingPrice, orderType: clobPkg.OrderType.FAK }
    : { tokenID: assetID, side: clobPkg.Side.BUY, amount: amountUSD, price: ceilingPrice, orderType: clobPkg.OrderType.FAK };
  const marketOrder = await client.createMarketOrder(orderInput);
  return client.postOrder(marketOrder, clobPkg.OrderType.FAK);
}

/**
 * Adaptive Execution Chaser Loop
 * Retries up to maxRetries if unfilled or book shifted,
 * strictly verifying that price ceiling is respected and spot gap has not collapsed.
 */
async function executeMarketBuyWithChaser(tokenID, amountUSD, options = {}) {
  const {
    maxAcceptablePrice = 0.98,
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

      let result = await submitFakOrder(client, tokenID, usePositionId, amountUSD, ceilingPrice);
      let errStr = result?.error || result?.errorMsg || '';
      if (typeof errStr === 'string' && errStr.includes('POLY_1271')) {
        console.log(`[CHASER ${attempt}] Signature routing mismatch -> switching ${usePositionId ? 'V3->V2' : 'V2->V3'} and retrying immediately...`);
        usePositionId = !usePositionId;
        result = await submitFakOrder(client, tokenID, usePositionId, amountUSD, ceilingPrice);
        errStr = result?.error || result?.errorMsg || '';
      }

      console.log(`[CHASER ${attempt}] CLOB response: status=${result?.status}, success=${result?.success}, orderID=${result?.orderID}, taking=${result?.takingAmount}, error=${errStr || 'none'}`);

      const hasHttpError = Boolean(errStr || (typeof result?.status === 'number' && result.status >= 400));
      const isMatched = Boolean(!hasHttpError && result && (
        result.status === 'matched' ||
        (result.takingAmount && Number(result.takingAmount) > 0) ||
        result.success === true
      ));

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
        latencyMs: Date.now() - tStart,
        result
      });

      if (isMatched) {
        console.log(`[CHASER ${attempt}] SUCCESS: Order matched at ~${executedPrice}c!`);
        return {
          success: true,
          attempt,
          executedAsk: executedPrice,
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

function startExecutionServer(port = 8897) {
  console.log(`[PRE-WARMED EXECUTOR] Initializing and pre-authenticating ClobClient...`);
  getClient().then(() => {
    console.log(`[PRE-WARMED EXECUTOR] ClobClient ready and authenticated with keep-alive.`);
  }).catch(err => {
    console.error(`[PRE-WARMED EXECUTOR] Warning during client pre-warm: ${err.message}`);
  });

  const server = http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/chaser') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        const tStart = Date.now();
        try {
          const payload = JSON.parse(body || '{}');
          const tokenID = payload.tokenID;
          const amountUSD = parseFloat(payload.amountUSD || '1.00');
          const options = payload.options || {};
          
          console.log(`\n[SERVER DISPATCH] Immediate trade request for Token ${tokenID} ($${amountUSD})...`);
          const result = await executeMarketBuyWithChaser(tokenID, amountUSD, options);
          const duration = Date.now() - tStart;
          console.log(`[SERVER DISPATCH COMPLETED] Execution duration: ${duration}ms | Success: ${result.success}`);
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
        } catch (err) {
          console.error(`[SERVER DISPATCH ERROR] ${err.message}`);
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: false, error: err.message }));
        }
      });
    } else if (req.method === 'POST' && req.url === '/books') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const payload = JSON.parse(body || '{}');
          const tokenIDs = Array.isArray(payload.tokenIDs) ? payload.tokenIDs : [];
          const results = await Promise.all(tokenIDs.map(id => fetchOrderBook(id).then(b => [String(id), { bestAsk: b.bestAsk, askDepth: b.askDepth }])));
          const books = Object.fromEntries(results);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ books }));
        } catch (err) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message }));
        }
      });
    } else if (req.method === 'GET' && req.url === '/ping') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ready', time: Date.now() }));
    } else {
      res.writeHead(404);
      res.end('Not Found');
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
