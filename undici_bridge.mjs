#!/usr/bin/env node
/**
 * undici 桥接脚本
 * 使用 Node.js 的 undici 库来绕过 Cloudflare
 * Python 插件通过 subprocess 调用此脚本
 */

import { fetch, ProxyAgent, setGlobalDispatcher } from 'undici';

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
    
    // 配置代理
    if (config.proxy) {
        try {
            const proxyAgent = new ProxyAgent(config.proxy);
            setGlobalDispatcher(proxyAgent);
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
            headers: headers
        };
        
        if (config.method === 'POST' && config.data) {
            fetchOptions.body = config.data;
        }
        
        const response = await fetch(config.url, fetchOptions);
        
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
            isJson: contentType.includes('application/json')
        };
        
        console.log(JSON.stringify(result));
        
    } catch (e) {
        console.log(JSON.stringify({ 
            error: e.message,
            code: e.code || 'UNKNOWN'
        }));
        process.exit(1);
    }
}

main();