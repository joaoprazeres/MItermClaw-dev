#!/usr/bin/env node
/**
 * Prompt Length Guard - Context protection for LLM calls
 * 
 * Prevents "prompt too long" errors by:
 * 1. Token counting before LLM calls
 * 2. Smart truncation (FIFO for chat, start+end for docs)
 * 3. Prompt compression (strip redundant preamble)
 * 
 * Usage:
 *   node prompt-length-guard.js --input "prompt text" --model minimax-m2.5:cloud
 *   node prompt-length-guard.js --file path/to/messages.json --model phi4-mini
 */

const fs = require('fs');
const path = require('path');

// Model context windows (approximate - can be extended)
const MODEL_CONTEXT_WINDOWS = {
  // Ollama models
  'minimax-m2.5:cloud': 128000,
  'minimax-m2.5': 128000,
  'phi4-mini': 4096,
  'phi4': 4096,
  'qwen3:4b': 4096,
  'qwen2.5:14b': 4096,
  'qwen2.5:7b': 4096,
  'llama3.1:8b': 4096,
  'llama3.1:70b': 4096,
  'llama3.3:70b': 4096,
  'gemma2:9b': 4096,
  'gemma2:27b': 4096,
  'mistral:7b': 4096,
  'mixtral:8x7b': 4096,
  'deepseek-r1:7b': 4096,
  'deepseek-r1:14b': 4096,
  'deepseek-r1:70b': 4096,
  'codellama:7b': 4096,
  'codellama:13b': 4096,
  'codellama:34b': 4096,
  'atlas/intersync-gemma-7b-instruct-function-calling': 8192,
  'MFDoom/deepseek-r1-tool-calling:7b': 8192,
  
  // Default fallback
  'default': 4096
};

/**
 * Estimate token count using a simple heuristic
 * Roughly: 1 token ≈ 4 characters for English text
 * More accurate for code: 1 token ≈ 3 characters
 */
function estimateTokens(text) {
  if (!text || typeof text !== 'string') return 0;
  
  // Handle both string and array content (OpenAI format)
  let fullText = '';
  
  if (Array.isArray(text)) {
    for (const block of text) {
      if (typeof block === 'string') {
        fullText += block;
      } else if (block?.type === 'text') {
        fullText += block.text || '';
      } else if (block?.type === 'tool_use') {
        fullText += JSON.stringify(block);
      } else if (block?.type === 'tool_result') {
        fullText += block.content || '';
      }
    }
  } else {
    fullText = text;
  }
  
  // Count tokens using character-based estimate
  // This is ~4 chars/token for English, adjusted for code
  const codePatterns = /function|const|let|var|import|export|class|def |async |await |=>|\{\{|\[\]|->/g;
  const codeMatches = fullText.match(codePatterns) || [];
  const codeRatio = Math.min(codeMatches.length / 100, 0.5); // Cap at 50% code
  
  const avgCharsPerToken = 4 - codeRatio; // 3-4 chars per token
  const tokens = Math.ceil(fullText.length / avgCharsPerToken);
  
  // Add overhead for JSON structure if messages array
  return tokens;
}

/**
 * Count tokens in messages array
 */
function countMessageTokens(messages, systemPrompt = '') {
  let total = estimateTokens(systemPrompt);
  
  for (const msg of messages) {
    // Role takes ~4 tokens
    total += 4;
    
    // Content
    if (typeof msg.content === 'string') {
      total += estimateTokens(msg.content);
    } else if (Array.isArray(msg.content)) {
      total += estimateTokens(msg.content);
    }
    
    // Tool calls add significant tokens
    if (msg.tool_calls) {
      total += estimateTokens(JSON.stringify(msg.tool_calls));
    }
    
    // Name field
    if (msg.name) {
      total += estimateTokens(msg.name) + 2;
    }
  }
  
  return total;
}

/**
 * Get context window for model
 */
function getContextWindow(model) {
  if (!model) return MODEL_CONTEXT_WINDOWS['default'];
  
  // Direct match
  if (MODEL_CONTEXT_WINDOWS[model]) {
    return MODEL_CONTEXT_WINDOWS[model];
  }
  
  // Partial match (e.g., "qwen3:4b" matches "qwen3")
  for (const [key, value] of Object.entries(MODEL_CONTEXT_WINDOWS)) {
    if (model.includes(key) || key.includes(model)) {
      return value;
    }
  }
  
  return MODEL_CONTEXT_WINDOWS['default'];
}

/**
 * Compress prompt by removing redundant preamble
 */
function compressPrompt(text) {
  if (!text) return text;
  
  let result = text;
  
  // Remove common redundant preambles
  const redundantPatterns = [
    /^You are a helpful AI assistant[\s\S]*?\n\n/i,
    /^You are a helpful assistant[\s\S]*?\n\n/i,
    /^As an AI[\s\S]*?\n\n/i,
    /^I am an AI assistant[\s\S]*?\n\n/i,
    /^Hello![\s\S]*?help you[\s\S]*?\n\n/i,
    /^Sure,?[\s\S]*?happy to help[\s\S]*?\n\n/i,
    /^I'd be happy to help[\s\S]*?\n\n/i,
    /^Great question[\s\S]*?\n\n/i,
    /^\*\*System:\*\*[\s\S]*?\n\n/i,
    /^\[System\] [\s\S]*?\n\n/i,
  ];
  
  for (const pattern of redundantPatterns) {
    result = result.replace(pattern, '');
  }
  
  // Collapse multiple newlines
  result = result.replace(/\n{3,}/g, '\n\n');
  
  return result.trim();
}

/**
 * Truncate messages using FIFO (keep most recent)
 */
function truncateChatMessages(messages, maxTokens, systemPrompt = '') {
  const availableTokens = Math.floor(maxTokens * 0.75); // Reserve 25% for output
  let tokensUsed = countMessageTokens([], systemPrompt);
  
  // Keep at least 2 messages for context
  const result = [];
  
  // Start from most recent
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    const msgTokens = countMessageTokens([msg]);
    
    if (tokensUsed + msgTokens <= availableTokens || result.length < 2) {
      result.unshift(msg);
      tokensUsed += msgTokens;
    } else {
      break;
    }
  }
  
  return {
    messages: result,
    truncated: result.length < messages.length,
    originalCount: messages.length,
    remainingCount: result.length,
    tokensUsed,
    availableTokens
  };
}

/**
 * Truncate document-style content (keep start + end)
 */
function truncateDocument(content, maxTokens) {
  const availableTokens = Math.floor(maxTokens * 0.75);
  const text = typeof content === 'string' ? content : JSON.stringify(content);
  const textTokens = estimateTokens(text);
  
  if (textTokens <= availableTokens) {
    return {
      content,
      truncated: false,
      tokensUsed: textTokens
    };
  }
  
  // Keep start and end
  const charsToKeep = Math.floor((availableTokens / 2) * 4); // Approx chars
  const start = text.slice(0, charsToKeep);
  const end = text.slice(-charsToKeep);
  
  const truncatedContent = `${start}\n\n[... ${textTokens - estimateTokens(start + end)} tokens truncated ...]\n\n${end}`;
  
  return {
    content: truncatedContent,
    truncated: true,
    tokensUsed: estimateTokens(truncatedContent),
    originalTokens: textTokens
  };
}

/**
 * Main sanitization function - the public API
 */
function sanitizePrompt(options) {
  const {
    messages,
    systemPrompt = '',
    model = 'default',
    maxTokens = null // Override for output reservation
  } = options;
  
  const contextWindow = maxTokens || getContextWindow(model);
  const maxInputTokens = Math.floor(contextWindow * 0.75);
  
  // Step 1: Compress system prompt
  const compressedSystem = compressPrompt(systemPrompt);
  
  // Step 2: Count current tokens
  const currentTokens = countMessageTokens(messages || [], compressedSystem);
  
  // If within limits, return as-is
  if (currentTokens <= maxInputTokens) {
    return {
      messages,
      systemPrompt: compressedSystem,
      truncated: false,
      tokensUsed: currentTokens,
      contextWindow,
      strategy: 'none'
    };
  }
  
  // Step 3: Truncate messages (FIFO for chat)
  let result;
  if (messages && messages.length > 0) {
    result = truncateChatMessages(messages, contextWindow, compressedSystem);
  } else {
    result = { messages: [], truncated: false, tokensUsed: 0 };
  }
  
  // Step 4: If still over, compress further
  if (result.tokensUsed > maxInputTokens && result.messages.length > 0) {
    // Keep only last message + system
    const lastMsg = result.messages[result.messages.length - 1];
    result = {
      messages: [lastMsg],
      truncated: true,
      originalCount: messages.length,
      remainingCount: 1,
      tokensUsed: countMessageTokens([lastMsg], compressedSystem),
      availableTokens: maxInputTokens
    };
  }
  
  return {
    messages: result.messages,
    systemPrompt: compressedSystem,
    truncated: result.truncated,
    tokensUsed: result.tokensUsed,
    contextWindow,
    strategy: result.truncated ? 'fifo' : 'none',
    originalCount: messages?.length || 0,
    remainingCount: result.messages?.length || 0
  };
}

// CLI mode
if (require.main === module) {
  const args = process.argv.slice(2);
  const options = {
    messages: [],
    systemPrompt: '',
    model: 'minimax-m2.5:cloud'
  };
  
  // Parse arguments
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--input' || arg === '-i') {
      options.messages = [{ role: 'user', content: args[++i] }];
    } else if (arg === '--system' || arg === '-s') {
      options.systemPrompt = args[++i];
    } else if (arg === '--model' || arg === '-m') {
      options.model = args[++i];
    } else if (arg === '--file' || arg === '-f') {
      try {
        const fileContent = fs.readFileSync(args[++i], 'utf8');
        const data = JSON.parse(fileContent);
        options.messages = data.messages || [];
        options.systemPrompt = data.systemPrompt || '';
      } catch (e) {
        console.error('Error reading file:', e.message);
        process.exit(1);
      }
    } else if (arg === '--tokens' || arg === '-t') {
      options.maxTokens = parseInt(args[++i], 10);
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
Prompt Length Guard - Context protection for LLM calls

Usage:
  node prompt-length-guard.js [options]

Options:
  -i, --input <text>      Input prompt text
  -s, --system <text>    System prompt
  -m, --model <name>     Model name (default: minimax-m2.5:cloud)
  -f, --file <path>      Read messages from JSON file
  -t, --tokens <n>       Override context window
  -h, --help             Show this help

Examples:
  node prompt-length-guard.js -i "Hello, how are you?" -m phi4-mini
  node prompt-length-guard.js -f ./messages.json -m qwen3:4b
      `);
      process.exit(0);
    }
  }
  
  if (!options.messages.length && !options.systemPrompt) {
    console.error('Error: Provide either --input, --file, or --system');
    process.exit(1);
  }
  
  const result = sanitizePrompt(options);
  
  console.log(JSON.stringify({
    success: true,
    result
  }, null, 2));
}

module.exports = {
  estimateTokens,
  countMessageTokens,
  getContextWindow,
  compressPrompt,
  truncateChatMessages,
  truncateDocument,
  sanitizePrompt,
  MODEL_CONTEXT_WINDOWS
};