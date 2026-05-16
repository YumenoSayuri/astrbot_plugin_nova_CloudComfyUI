#!/usr/bin/env node
/**
 * Node 桥接脚本
 * 优先使用 undici；若未安装 undici，则回退到 Node 18+/24 自带 fetch
 * 当需要代理时，仍建议安装 undici 以支持 ProxyAgent
 */

let fetchImpl = globalThis.fetch;
let ProxyAgentImpl = null;
let setGlobalDispatcherImpl = null;
let usingUndici = false;

try {
    const undici = await import('undici');
    fetchImpl = undici.fetch || fetchImpl;
    ProxyAgentImpl = undici.ProxyAgent || null;
    setGlobalDispatcherImpl = undici.setGlobalDispatcher || null;
    usingUndici = true;
} catch (e) {
    usingUndici = false;
}

const args = process.argv.slice(2);

function parseArgs() {
    const config = {
        url: '',
        method: 'POST',
        apiKey: '',
        proxy: '',
        data: '{}',
        responseType: 'auto'
    };

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--url' && args[i + 1]) {
            config.url = args[i + 1];
            i++;
        } else if (args[i] === '--method' && args[i + 1]) {
            config.method = args[i + 1].toUpperCase();
            i++;
        } else if (args[i] === '--api-key' && args[i + 1]) {
            config.apiKey = args[i + 1];
            i++;
        } else if (args[i] === '--proxy' && args[i + 1]) {
            config.proxy = args[i + 1];
            i++;
        } else if (args[i] === '--data' && args[i + 1]) {
            config.data = args[i + 1];
            i++;
        } else if (args[i] === '--response-type' && args[i + 1]) {
            config.responseType = args[i + 1].toLowerCase();
            i++;
        }
    }

    return config;
}

async function readResponseBody(response, responseType) {
    const contentType = response.headers.get('content-type') || '';

    if (responseType === 'base64') {
        const arrayBuffer = await response.arrayBuffer();
        return {
            body: Buffer.from(arrayBuffer).toString('base64'),
            isJson: false,
            isBase64: true,
            contentType
        };
    }

    if (responseType === 'text') {
        return {
            body: await response.text(),
            isJson: false,
            isBase64: false,
            contentType
        };
    }

    if (responseType === 'json') {
        return {
            body: await response.json(),
            isJson: true,
            isBase64: false,
            contentType
        };
    }

    if (contentType.includes('application/json')) {
        return {
            body: await response.json(),
            isJson: true,
            isBase64: false,
            contentType
        };
    }

    return {
        body: await response.text(),
        isJson: false,
        isBase64: false,
        contentType
    };
}

async function main() {
    const config = parseArgs();

    if (!config.url) {
        console.log(JSON.stringify({ error: 'Missing --url parameter' }));
        process.exit(1);
    }

    if (!fetchImpl) {
        console.log(JSON.stringify({
            error: 'No fetch implementation available. Please use Node 18+ or install undici.'
        }));
        process.exit(1);
    }

    if (config.proxy) {
        if (!usingUndici || !ProxyAgentImpl || !setGlobalDispatcherImpl) {
            console.log(JSON.stringify({
                error: 'Proxy requires undici. Please run npm install in plugin directory to install undici.',
                code: 'UNDICI_REQUIRED_FOR_PROXY'
            }));
            process.exit(1);
        }

        try {
            const proxyAgent = new ProxyAgentImpl(config.proxy);
            setGlobalDispatcherImpl(proxyAgent);
        } catch (e) {
            console.log(JSON.stringify({ error: `Proxy config error: ${e.message}` }));
            process.exit(1);
        }
    }

    try {
        const headers = {};

        if (config.method === 'POST') {
            headers['Content-Type'] = 'application/json';
        }

        if (config.apiKey) {
            headers['Authorization'] = `Bearer ${config.apiKey}`;
        }

        const fetchOptions = {
            method: config.method,
            headers
        };

        if (config.method === 'POST' && config.data) {
            fetchOptions.body = config.data;
        }

        const response = await fetchImpl(config.url, fetchOptions);
        const parsed = await readResponseBody(response, config.responseType);

        const result = {
            status: response.status,
            statusText: response.statusText,
            headers: Object.fromEntries(response.headers.entries()),
            body: parsed.body,
            isJson: parsed.isJson,
            isBase64: parsed.isBase64,
            usingUndici
        };

        console.log(JSON.stringify(result));
    } catch (e) {
        console.log(JSON.stringify({
            error: e.message,
            code: e.code || 'UNKNOWN',
            usingUndici
        }));
        process.exit(1);
    }
}

main();