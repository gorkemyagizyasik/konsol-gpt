const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const https = require('https');

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

// Force iframe mode in Sentinel SDK so it doesn't create document iframe elements
code = code.replace(/const ie=[^;]+;/, 'const ie = true;');

// 2. PoW Token Generator
function generateProofToken(seedUuid, difficulty = 3000) {
    if (!seedUuid) seedUuid = crypto.randomUUID();
    const ua = config.user_agent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36';
    const timeStr = new Date().toUTCString();
    const epochMs = roundMs(Date.now());

    const payload = [
        difficulty,
        timeStr,
        4395630592,
        0,
        ua,
        'https://chatgpt.com/sentinel/20260810913b/sdk.js',
        'prod-8bfe9e3526fbf9900f9332d46fef7bc0065c4478',
        'tr-TR',
        'tr-TR,tr,en-US,en',
        6,
        'deprecatedRunAdAuctionEnforcesKAnonymity\u2212false',
        'location',
        'scroll',
        148620.30000000447,
        seedUuid,
        '',
        4,
        epochMs,
        0, 0, 0, 0, 0, 0, 0
    ];

    const target = Math.floor(0xFFFFF / (Math.floor(difficulty / 1000) + 1));
    let nonce = 0;
    while (nonce < 50000) {
        payload[3] = nonce;
        const jsonStr = JSON.stringify(payload);
        const hashDigest = crypto.createHash('sha256').update(jsonStr, 'utf8').digest('hex');
        if (parseInt(hashDigest.slice(0, 5), 16) <= target) {
            const b64Payload = global.btoa(jsonStr);
            return `gAAAAAB${b64Payload}~S`;
        }
        nonce++;
    }
    const jsonStr = JSON.stringify(payload);
    return `gAAAAAB${global.btoa(jsonStr)}~S`;
}

function roundMs(ms) {
    return Math.round(ms * 10) / 10;
}

// 3. Node.js VM Sandbox Setup
const vm = require('vm');
const sandbox = {
    btoa: global.btoa,
    atob: global.atob,
    window: {
        location: { href: 'https://chatgpt.com/backend-api/sentinel/frame.html' },
        navigator: { userAgent: config.user_agent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' },
        addEventListener: (event, handler) => {
            if (event === 'message') sandbox.messageHandler = handler;
        }
    },
    document: {
        createElement: () => ({ addEventListener: () => {}, style: {} }),
        addEventListener: () => {},
        body: { appendChild: () => {} }
    },
    location: { href: 'https://chatgpt.com/backend-api/sentinel/frame.html' },
    navigator: { userAgent: config.user_agent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' },
    console: { log: () => {}, warn: () => {}, error: () => {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    crypto: global.crypto,
    URL: global.URL,
    AbortController: global.AbortController,
    performance: { now: () => Date.now(), getEntries: () => [] },
    fetch: async (url, opts) => {
        return new Promise((resolve, reject) => {
            const u = new URL(url);
            const reqOpts = {
                hostname: u.hostname,
                path: u.pathname + u.search,
                method: opts && opts.method ? opts.method : 'GET',
                headers: {
                    'User-Agent': config.user_agent || 'Mozilla/5.0',
                    'Cookie': config.cookie || '',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            };
            if (config.auth_token) {
                reqOpts.headers['Authorization'] = config.auth_token.startsWith('Bearer ') ? config.auth_token : ('Bearer ' + config.auth_token);
            }
            const req = https.request(reqOpts, (res) => {
                let data = '';
                res.on('data', c => data += c);
                res.on('end', () => {
                    resolve({
                        ok: res.statusCode >= 200 && res.statusCode < 300,
                        status: res.statusCode,
                        json: async () => JSON.parse(data),
                        text: async () => data
                    });
                });
            });
            req.on('error', reject);
            if (opts && opts.body) req.write(opts.body);
            req.end();
        });
    }
};
sandbox.window.top = {};
sandbox.window.window = sandbox.window;

vm.createContext(sandbox);
vm.runInContext(code, sandbox);

async function getSentinelTokens(flow = 'conversation') {
    const parentMsgId = process.argv[2] || crypto.randomUUID();
    const powToken = generateProofToken(parentMsgId);

    if (sandbox.messageHandler) {
        return new Promise((resolve) => {
            const requestId = 'req_' + crypto.randomUUID();
            const messageEvent = {
                source: {
                    postMessage: (resData) => {
                        let parsedResult = {};
                        if (resData && resData.result) {
                            try {
                                parsedResult = typeof resData.result === 'string' ? JSON.parse(resData.result) : resData.result;
                            } catch (e) {}
                        }
                        const token = parsedResult.token || (parsedResult.c ? parsedResult.c : null);
                        const turnstileToken = parsedResult.t || (parsedResult.turnstile ? parsedResult.turnstile : null);

                        resolve({
                            status: 'ok',
                            token: token,
                            proof_token: powToken,
                            turnstile_token: turnstileToken,
                            raw: parsedResult
                        });
                    }
                },
                origin: 'https://chatgpt.com',
                data: {
                    type: 'token',
                    flow: flow,
                    requestId: requestId,
                    p: powToken
                }
            };
            sandbox.messageHandler(messageEvent);
        });
    } else {
        return {
            status: 'ok',
            proof_token: powToken
        };
    }
}

getSentinelTokens('conversation').then(result => {
    console.log(JSON.stringify(result));
}).catch(err => {
    console.log(JSON.stringify({ status: 'error', message: err.message }));
});
