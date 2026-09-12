const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// 1. Browser Primitives & Mocks
global.btoa = (str) => Buffer.from(str, 'binary').toString('base64');
global.atob = (b64) => Buffer.from(b64, 'base64').toString('binary');
global.crypto = {
    getRandomValues: (buf) => crypto.randomFillSync(buf),
    subtle: crypto.webcrypto.subtle,
    randomUUID: () => crypto.randomUUID()
};
global.URL = require('url').URL;
global.AbortController = global.AbortController || class { abort() {} };

const configPath = path.join(__dirname, 'config.json');
const sdkPath = path.join(__dirname, 'sentinel_sdk.js');

let config = {};
if (fs.existsSync(configPath)) {
    try {
        config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    } catch (e) {}
}

let code = '';
if (fs.existsSync(sdkPath)) {
    code = fs.readFileSync(sdkPath, 'utf8');
} else {
    console.log(JSON.stringify({ status: 'error', message: 'sentinel_sdk.js file not found' }));
    process.exit(1);
}

// Force iframe mode and expose Turnstile solver function (Rn)
code = code.replace(',t.token=je,t}({});', ',t.solveTurnstile=Rn,t.token=je,t}({});');
code = code.replace(/const ie=[^;]+;/, 'const ie = true;');

const vm = require('vm');
const sandbox = {
    btoa: global.btoa,
    atob: global.atob,
    window: {
        location: { href: 'https://chatgpt.com/backend-api/sentinel/frame.html?sv=20260810913b' },
        navigator: { userAgent: config.user_agent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' },
        addEventListener: () => {}
    },
    document: {
        createElement: () => ({ addEventListener: () => {}, style: {} }),
        addEventListener: () => {},
        body: { appendChild: () => {} },
        scripts: [
            { src: 'https://chatgpt.com/sentinel/20260810913b/sdk.js' }
        ]
    },
    location: { href: 'https://chatgpt.com/backend-api/sentinel/frame.html?sv=20260810913b' },
    navigator: { userAgent: config.user_agent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' },
    console: { log: () => {}, warn: () => {}, error: () => {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    crypto: global.crypto,
    URL: global.URL,
    AbortController: global.AbortController,
    performance: { now: () => Date.now(), getEntries: () => [] }
};
sandbox.window.top = {};
sandbox.window.window = sandbox.window;

vm.createContext(sandbox);
vm.runInContext('var SentinelSDK = {};' + code, sandbox);

async function solveTurnstile() {
    const prepDataStr = process.argv[2] || '{}';
    const dx = process.argv[3] || '';
    try {
        const prepData = JSON.parse(prepDataStr);
        if (!dx) {
            console.log(JSON.stringify({ status: 'error', message: 'dx missing' }));
            return;
        }
        const solved = await sandbox.SentinelSDK.solveTurnstile(prepData, dx);
        console.log(JSON.stringify({ status: 'ok', solved: solved }));
    } catch (e) {
        console.log(JSON.stringify({ status: 'error', message: e.message }));
    }
}

solveTurnstile();

