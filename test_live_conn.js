const fs = require('fs');
const path = require('path');

// Point to the weather directory for node_modules and .env
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

async function testConnection() {
  console.log('Testing CLOB connection...');
  console.log('Funder Address:', FUNDER_ADDRESS);
  console.log('CLOB Host:', CLOB_HOST);
  console.log('RPC URL:', RPC_URL);

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
  console.log('API Key Derived Successfully!');

  const client = new clobPkg.ClobClient({
    host: CLOB_HOST,
    chain: clobPkg.Chain.POLYGON,
    signer,
    creds: apiCreds,
    funderAddress: FUNDER_ADDRESS,
    signatureType: 3
  });

  try {
    const bal = await client.getBalanceAllowance({ asset_type: clobPkg.AssetType.COLLATERAL });
    console.log('Balance & Allowance Result:', JSON.stringify(bal));
    if (bal && bal.balance) {
      console.log(`Available Collateral Balance: $${(Number(bal.balance) / 1e6).toFixed(2)} USDC`);
      console.log(`Allowance: $${(Number(bal.allowance) / 1e6).toFixed(2)} USDC`);
    }
  } catch (err) {
    console.error('Error fetching balance:', err.message);
  }
}

testConnection().catch(err => {
  console.error('Fatal connection error:', err);
});
