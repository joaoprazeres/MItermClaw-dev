#!/usr/bin/env node
/**
 * LLM Wrapper - Integrates prompt-length-guard into LLM calls
 * 
 * This wrapper sanitizes prompts before sending to the LLM API
 * to prevent "prompt too long" errors.
 * 
 * Usage:
 *   const { callLlmWithGuard } = require('./llm-wrapper.js');
 *   const result = await callLlmWithGuard({ messages, systemPrompt, model, provider, ... });
 * 
 * Or as CLI:
 *   node llm-wrapper.js --messages '[{"role":"user","content":"..."}]' --model minimax-m2.5:cloud
 */

const fs = require('fs');
const path = require('path');

// Load the prompt-length-guard module
const guardPath = path.join(__dirname, 'prompt-length-guard.js');
const { sanitizePrompt } = require(guardPath);

/**
 * Call LLM with automatic prompt sanitization
 * 
 * @param {Object} options
 * @param {Array} options.messages - Chat messages array
 * @param {string} options.systemPrompt - System prompt
 * @param {string} options.model - Model ID (e.g., "minimax-m2.5:cloud")
 * @param {string} options.provider - Provider (e.g., "ollama")
 * @param {Function} options.llmCallFn - The actual LLM call function (required)
 * @returns {Promise<Object>} LLM response
 */
async function callLlmWithGuard(options) {
  const {
    messages = [],
    systemPrompt = '',
    model = 'minimax-m2.5:cloud',
    provider = 'ollama',
    llmCallFn,
    dryRun = false
  } = options;

  // Sanitize the prompt (always)
  const sanitized = sanitizePrompt({ messages, systemPrompt, model });
  
  console.error(`[llm-wrapper] Token stats: ${sanitized.tokensUsed}/${sanitized.contextWindow} (${sanitized.strategy})`);
  
  if (sanitized.truncated) {
    console.error(`[llm-wrapper] Truncated ${sanitized.originalCount} -> ${sanitized.remainingCount} messages`);
  }

  // Dry run mode - just return sanitization info
  if (dryRun) {
    return {
      dryRun: true,
      sanitized,
      originalMessageCount: messages.length,
      truncated: sanitized.truncated
    };
  }

  // Validate LLM function is provided for actual calls
  if (!llmCallFn || typeof llmCallFn !== 'function') {
    throw new Error('llmCallFn is required for non-dry-run calls');
  }

  // Make the actual LLM call with sanitized messages
  const result = await llmCallFn({
    messages: sanitized.messages,
    systemPrompt: sanitized.systemPrompt,
    model,
    provider
  });

  return {
    ...result,
    _sanitization: {
      truncated: sanitized.truncated,
      tokensUsed: sanitized.tokensUsed,
      contextWindow: sanitized.contextWindow,
      strategy: sanitized.strategy,
      originalMessageCount: messages.length,
      remainingMessageCount: sanitized.messages.length
    }
  };
}

/**
 * Simple Ollama API caller (example implementation)
 */
async function callOllama(options) {
  const { messages, systemPrompt, model = 'minimax-m2.5:cloud', baseUrl = 'http://127.0.0.1:11434' } = options;
  
  // Combine system prompt into first user message if present
  let fullMessages = [...messages];
  if (systemPrompt) {
    fullMessages = fullMessages.map(msg => {
      if (msg.role === 'user') {
        return { ...msg, content: `SYSTEM: ${systemPrompt}\n\n${msg.content}` };
      }
      return msg;
    });
  }

  const response = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: model,
      messages: fullMessages,
      stream: false
    })
  });

  if (!response.ok) {
    throw new Error(`Ollama API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// CLI mode
if (require.main === module) {
  const args = process.argv.slice(2);
  const options = {
    messages: [],
    systemPrompt: '',
    model: 'minimax-m2.5:cloud',
    provider: 'ollama',
    dryRun: false
  };

  // Parse arguments
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--messages' || arg === '-m') {
      try {
        options.messages = JSON.parse(args[++i]);
      } catch (e) {
        console.error('Invalid JSON for messages');
        process.exit(1);
      }
    } else if (arg === '--system' || arg === '-s') {
      options.systemPrompt = args[++i];
    } else if (arg === '--model' || arg === '-M') {
      options.model = args[++i];
    } else if (arg === '--provider' || arg === '-p') {
      options.provider = args[++i];
    } else if (arg === '--dry-run' || arg === '-d') {
      options.dryRun = true;
    } else if (arg === '--file' || arg === '-f') {
      try {
        const fileContent = fs.readFileSync(args[++i], 'utf8');
        const data = JSON.parse(fileContent);
        options.messages = data.messages || [];
        options.systemPrompt = data.systemPrompt || '';
        if (data.model) options.model = data.model;
      } catch (e) {
        console.error('Error reading file:', e.message);
        process.exit(1);
      }
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
LLM Wrapper - Prompt sanitization for LLM calls

Usage:
  node llm-wrapper.js [options]

Options:
  -m, --messages <json>    Messages array (JSON)
  -s, --system <text>      System prompt
  -M, --model <name>      Model name (default: minimax-m2.5:cloud)
  -p, --provider <name>   Provider (default: ollama)
  -f, --file <path>       Read input from JSON file
  -d, --dry-run           Only sanitize, don't call LLM
  -h, --help              Show this help

Examples:
  node llm-wrapper.js -m '[{"role":"user","content":"Hello"}]' -M phi4-mini
  node llm-wrapper.js -f ./prompt.json -M minimax-m2.5:cloud -d
      `);
      process.exit(0);
    }
  }

  if (!options.messages.length && !options.systemPrompt) {
    console.error('Error: Provide either --messages, --file, or --system');
    process.exit(1);
  }

  // Test the sanitizer (dry run or actual call)
  callLlmWithGuard({
    ...options,
    llmCallFn: options.dryRun ? null : callOllama
  }).then(result => {
    console.log(JSON.stringify(result, null, 2));
  }).catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
  });
}

module.exports = {
  callLlmWithGuard,
  callOllama,
  sanitizePrompt
};