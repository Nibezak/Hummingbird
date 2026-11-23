/**
 * LIVE ORDER EXECUTOR FOR POLYMARKET CLOB
 * Path: c:\projects\btc-5m-recorder\live_executor.js
 * 
 * Directly leverages verified @polymarket/clob-client-v2 and viem setup from c:\projects\weather
 */

const fs = require('fs');
const path = require('path');

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

async function executeMarketBuy(tokenID, amountUSD, maxAcceptablePrice = 0.96) {
  const client = await getClient();
  
  // 1. Balance verification
  const balInfo = await getBalance();
  if (balInfo.balanceUSDC < amountUSD) {
    throw new Error(`Insufficient funds: Balance is $${balInfo.balanceUSDC} USDC, required is $${amountUSD} USDC`);
  }

  // 2. Market order placement (FAK - Fill And Kill)
  console.log(`[LIVE EXEC] Submitting Market Buy FAK: $${amountUSD} for Token ${tokenID}...`);
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
    timestamp: new Date().toISOString()
  };
}

// CLI handler
async function main() {
  const args = process.argv.slice(2);
  const action = args[0] || 'balance';

  if (action === 'balance') {
    const res = await getBalance();
    console.log(JSON.stringify(res));
  } else if (action === 'buy') {
    const tokenID = args[1];
    const amount = parseFloat(args[2]);
    const maxPrice = parseFloat(args[3] || '0.96');
    if (!tokenID || !amount) {
      console.error(JSON.stringify({ error: 'Missing tokenID or amount' }));
      process.exit(1);
    }
    const res = await executeMarketBuy(tokenID, amount, maxPrice);
    console.log(JSON.stringify(res));
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

module.exports = { getBalance, executeMarketBuy };
