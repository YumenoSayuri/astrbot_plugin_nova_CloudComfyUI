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

// 从命令行参数或环境变量获取配置
const args = process.argv.slice(2);

// 解析命令行参数
function parseArgs() {
    const config = {
        url: '',
        method: 'POST',
        apiKey: '',
        proxy: '',
        data: '{}'
    };

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--url' && args[i + 1]) {
            config.url = args[i + 1];
            i++;
        } else if (args[i] === '--method' && args[i + 1]) {
            config.method = args[i + 1];
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
        }
    }

    return config;
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

    // 配置代理
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
        const headers = {
            'Content-Type': 'application/json'
        };

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

        const contentType = response.headers.get('content-type') || '';
        let responseBody;

        if (contentType.includes('application/json')) {
            responseBody = await response.json();
        } else {
            responseBody = await response.text();
        }

        const result = {
            status: response.status,
            statusText: response.statusText,
            headers: Object.fromEntries(response.headers.entries()),
            body: responseBody,
            isJson: contentType.includes('application/json'),
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