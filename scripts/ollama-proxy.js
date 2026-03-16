#!/usr/bin/env node
/**
 * Ollama Proxy Server
 * 
 * Intercepts Ollama API calls, sanitizes prompts to prevent "prompt too long" errors,
 * then forwards to actual Ollama instance.
 * 
 * Usage:
 *   node ollama-proxy.js [--port PORT] [--ollama-url URL]
 * 
 * Default: listen on 11435, forward to localhost:11434
 */

const http = require('http');
const { sanitizePrompt, getContextWindow, countMessageTokens } = require('./prompt-length-guard.js');

// Configuration
const PROXY_PORT = process.env.PROXY_PORT || 11435;
const OLLAMA_URL = process.env.OLLAMA_URL || 'localhost:11434';
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

// Simple logger
const logger = {
  info: (...args) => LOG_LEVEL !== 'silent' && console.log('[INFO]', new Date().toISOString(), ...args),
  warn: (...args) => console.warn('[WARN]', new Date().toISOString(), ...args),
  error: (...args) => console.error('[ERROR]', new Date().toISOString(), ...args),
  debug: (...args) => LOG_LEVEL === 'debug' && console.log('[DEBUG]', new Date().toISOString(), ...args)
};

/**
 * Forward request to actual Ollama
 */
function forwardToOllama(requestBody) {
  return new Promise((resolve, reject) => {
    const url = new URL(`http://${OLLAMA_URL}/api/chat`);
    
    const options = {
      hostname: url.hostname,
      port: url.port || 80,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 300000 // 5 minute timeout
    };

    const req = http.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: data
          });
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request to Ollama timed out'));
    });

    req.write(JSON.stringify(requestBody));
    req.end();
  });
}

/**
 * Handle incoming /api/chat request
 */
async function handleChatRequest(req, res) {
  let body = '';
  
  return new Promise((resolve, reject) => {
    req.on('data', chunk => {
      body += chunk;
    });
    
    req.on('end', async () => {
      try {
        const requestData = JSON.parse(body);
        const model = requestData.model || 'default';
        const messages = requestData.messages || [];
        const systemPrompt = requestData.system || '';
        
        logger.debug('Received chat request:', { model, messageCount: messages.length });
        
        // Get context window for model
        const contextWindow = getContextWindow(model);
        
        // Sanitize the prompt
        const sanitized = sanitizePrompt({
          messages,
          systemPrompt,
          model
        });
        
        // Log sanitization results
        if (sanitized.truncated) {
          logger.info(`📝 Prompt truncated for model "${model}":`, {
            originalMessages: sanitized.originalCount,
            remainingMessages: sanitized.remainingCount,
            tokensUsed: sanitized.tokensUsed,
            contextWindow: sanitized.contextWindow,
            strategy: sanitized.strategy
          });
        } else {
          logger.debug('No truncation needed', {
            tokensUsed: sanitized.tokensUsed,
            contextWindow: sanitized.contextWindow
          });
        }
        
        // Build sanitized request for Ollama
        const ollamaRequest = {
          ...requestData,
          messages: sanitized.messages
        };
        
        if (sanitized.systemPrompt) {
          ollamaRequest.system = sanitized.systemPrompt;
        }
        
        // Forward to actual Ollama
        logger.debug('Forwarding to Ollama...');
        const response = await forwardToOllama(ollamaRequest);
        
        // Set CORS headers for browser accessibility
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
        
        // Forward response
        res.writeHead(response.statusCode, {
          'Content-Type': 'application/json'
        });
        res.end(response.body);
        
        resolve();
      } catch (error) {
        logger.error('Error handling request:', error.message);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
        reject(error);
      }
    });
    
    req.on('error', reject);
  });
}

/**
 * Handle other Ollama API endpoints (passthrough)
 */
async function handlePassthrough(req, res) {
  const path = req.url;
  
  // Only allow certain endpoints to pass through
  const allowedEndpoints = ['/api/generate', '/api/embeddings', '/api/tags', '/api/models'];
  
  const isAllowed = allowedEndpoints.some(endpoint => path.startsWith(endpoint));
  
  if (!isAllowed) {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Endpoint not supported by proxy' }));
    return;
  }
  
  let body = '';
  req.on('data', chunk => body += chunk);
  
  await new Promise((resolve) => {
    req.on('end', async () => {
      try {
        const url = new URL(`http://${OLLAMA_URL}${path}`);
        
        const options = {
          hostname: url.hostname,
          port: url.port || 80,
          path: url.pathname + url.search,
          method: req.method,
          headers: {
            'Content-Type': 'application/json',
          }
        };
        
        const proxyReq = http.request(options, (proxyRes) => {
          res.writeHead(proxyRes.statusCode, proxyRes.headers);
          
          proxyRes.on('data', (chunk) => {
            res.write(chunk);
          });
          
          proxyRes.on('end', () => {
            res.end();
            resolve();
          });
        });
        
        proxyReq.on('error', (e) => {
          logger.error('Passthrough error:', e.message);
          res.writeHead(502);
          res.end();
          resolve();
        });
        
        if (body) {
          proxyReq.write(body);
        }
        proxyReq.end();
      } catch (e) {
        logger.error('Passthrough setup error:', e.message);
        res.writeHead(500);
        res.end();
        resolve();
      }
    });
  });
}

/**
 * Create and start the proxy server
 */
function startProxy() {
  const server = http.createServer(async (req, res) => {
    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
      });
      res.end();
      return;
    }
    
    const url = req.url;
    
    try {
      // Route based on endpoint
      if (url === '/api/chat' || url.startsWith('/api/chat?')) {
        await handleChatRequest(req, res);
      } else if (url.startsWith('/api/')) {
        // Other API endpoints - pass through
        await handlePassthrough(req, res);
      } else if (url === '/health' || url === '/v1/health') {
        // Health check endpoint
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', proxy: 'ollama-proxy' }));
      } else if (url === '/') {
        // Root - show proxy info
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(`
<!DOCTYPE html>
<html>
<head><title>Ollama Proxy</title></head>
<body>
<h1>Ollama Proxy Server</h1>
<p>Port: ${PROXY_PORT}</p>
<p>Forwarding to: ${OLLAMA_URL}</p>
<p>Endpoint: <code>/api/chat</code></p>
<p><a href="/health">Health Check</a></p>
</body>
</html>
        `);
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    } catch (error) {
      logger.error('Server error:', error);
    }
  });

  server.listen(PROXY_PORT, () => {
    logger.info(`🚀 Ollama Proxy running on http://localhost:${PROXY_PORT}`);
    logger.info(`   Forwarding to: http://${OLLAMA_URL}/api/chat`);
    logger.info(`   Sanitization: ENABLED`);
    logger.info('');
    logger.info('Configuration for OpenClaw:');
    logger.info(`   Set model endpoint to: http://127.0.0.1:${PROXY_PORT}`);
    logger.info(`   Or set OLLAMA_PROXY_URL=http://127.0.0.1:${PROXY_PORT}`);
  });

  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      logger.error(`Port ${PROXY_PORT} is already in use`);
      logger.info(`Try: PROXY_PORT=11436 node ollama-proxy.js`);
    } else {
      logger.error('Server error:', err);
    }
    process.exit(1);
  });
}

// Start if run directly
if (require.main === module) {
  const args = process.argv.slice(2);
  
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port' || args[i] === '-p') {
      process.env.PROXY_PORT = args[++i];
    } else if (args[i] === '--ollama-url' || args[i] === '-u') {
      process.env.OLLAMA_URL = args[++i];
    } else if (args[i] === '--debug') {
      process.env.LOG_LEVEL = 'debug';
    } else if (args[i] === '--silent') {
      process.env.LOG_LEVEL = 'silent';
    } else if (args[i] === '--help' || args[i] === '-h') {
      console.log(`
Ollama Proxy Server

Usage:
  node ollama-proxy.js [options]

Options:
  -p, --port PORT        Proxy port (default: 11435)
  -u, --ollama-url URL   Ollama URL (default: localhost:11434)
  --debug                Enable debug logging
  --silent               Suppress all logging
  -h, --help             Show this help

Examples:
  node ollama-proxy.js                    # Default: 11435 -> localhost:11434
  node ollama-proxy.js --port 11436       # Use different port
  node ollama-proxy.js -u 192.168.1.100:11434  # Forward to remote Ollama
  DEBUG=true node ollama-proxy.js         # Debug output
      `);
      process.exit(0);
    }
  }
  
  startProxy();
}

module.exports = { startProxy };