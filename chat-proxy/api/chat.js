'use strict';

const { SYSTEM_PROMPT } = require('../lib/prompt.js');

const DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions';
const DEFAULT_ORIGINS = ['https://sandymarques.github.io'];

const MAX_MESSAGES = 6;
const MAX_CONTENT_CHARS = 500;
const MAX_TOKENS = 500;
const CARD_IDS = ['experiencia', 'tapioca', 'rag', 'planilhas', 'projetos-dev', 'blog', 'curriculo', 'contato'];
const MAX_CARDS = 3;
const MAX_SUGGESTIONS = 3;
const MAX_SUGGESTION_CHARS = 80;
const RATE_LIMIT = 8; // requisições por janela, por IP (melhor esforço, em memória)
const RATE_WINDOW_MS = 60 * 1000;
const UPSTREAM_TIMEOUT_MS = 20 * 1000;

const hits = new Map();

function allowedOrigins() {
  const raw = process.env.ALLOWED_ORIGINS;
  if (!raw) return DEFAULT_ORIGINS;
  return raw.split(',').map((s) => s.trim()).filter(Boolean);
}

function rateLimited(ip, now) {
  const entry = hits.get(ip);
  if (!entry || now - entry.start > RATE_WINDOW_MS) {
    hits.set(ip, { start: now, count: 1 });
    if (hits.size > 5000) {
      for (const [key, value] of hits) {
        if (now - value.start > RATE_WINDOW_MS) hits.delete(key);
      }
    }
    return false;
  }
  entry.count += 1;
  return entry.count > RATE_LIMIT;
}

function sanitizeMessages(input) {
  if (!Array.isArray(input)) return null;
  const cleaned = [];
  for (const m of input.slice(-MAX_MESSAGES)) {
    if (!m || (m.role !== 'user' && m.role !== 'assistant')) return null;
    if (typeof m.content !== 'string') return null;
    const content = m.content.trim().slice(0, MAX_CONTENT_CHARS);
    if (!content) return null;
    cleaned.push({ role: m.role, content });
  }
  if (!cleaned.length || cleaned[cleaned.length - 1].role !== 'user') return null;
  return cleaned;
}

// Interpreta a saída do modelo (JSON pedido no prompt). Se não vier JSON válido,
// usa o conteúdo como texto puro. Cartões só da lista fixa; sugestões só texto curto.
function parseModelOutput(raw) {
  let parsed = null;
  try { parsed = JSON.parse(raw); } catch (_) {
    const match = /\{[\s\S]*\}/.exec(raw);
    if (match) { try { parsed = JSON.parse(match[0]); } catch (__) { parsed = null; } }
  }
  if (!parsed || typeof parsed !== 'object' || typeof parsed.text !== 'string' || !parsed.text.trim()) {
    return { reply: raw.trim(), cards: [], suggestions: [] };
  }
  const cards = Array.isArray(parsed.cards)
    ? [...new Set(parsed.cards.filter((id) => CARD_IDS.includes(id)))].slice(0, MAX_CARDS)
    : [];
  const suggestions = Array.isArray(parsed.suggestions)
    ? parsed.suggestions
      .filter((q) => typeof q === 'string' && q.trim())
      .map((q) => q.trim().slice(0, MAX_SUGGESTION_CHARS))
      .slice(0, MAX_SUGGESTIONS)
    : [];
  return { reply: parsed.text.trim(), cards, suggestions };
}

// O modo JSON do DeepSeek falha (conteúdo vazio) quando o histórico traz respostas
// antigas em texto puro. Reenvia as falas do assistente no mesmo formato pedido.
function toUpstreamMessages(messages) {
  return messages.map((m) => (m.role === 'assistant'
    ? { role: 'assistant', content: JSON.stringify({ text: m.content, cards: [], suggestions: [] }) }
    : m));
}

async function callDeepSeek(apiKey, messages) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const upstream = await fetch(DEEPSEEK_URL, {
      method: 'POST',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({
        model: process.env.DEEPSEEK_MODEL || 'deepseek-chat',
        messages: [{ role: 'system', content: SYSTEM_PROMPT }, ...toUpstreamMessages(messages)],
        max_tokens: MAX_TOKENS,
        temperature: 0.3,
        response_format: { type: 'json_object' },
        stream: false,
      }),
    });
    if (!upstream.ok) return { error: `http_${upstream.status}` };
    const data = await upstream.json();
    const reply = data && data.choices && data.choices[0] && data.choices[0].message
      && data.choices[0].message.content;
    if (typeof reply !== 'string' || !reply.trim()) return { error: 'empty_content' };
    return { reply };
  } catch (err) {
    return { error: err && err.name === 'AbortError' ? 'timeout' : 'network' };
  } finally {
    clearTimeout(timer);
  }
}

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(body));
}

module.exports = async function handler(req, res) {
  const origin = req.headers.origin;
  const allowed = allowedOrigins();
  const originOk = origin && allowed.includes(origin);

  if (originOk) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Access-Control-Max-Age', '86400');
  }

  if (req.method === 'OPTIONS') {
    res.statusCode = originOk ? 204 : 403;
    return res.end();
  }
  if (req.method !== 'POST') return send(res, 405, { error: 'Método não permitido.' });
  if (!originOk) return send(res, 403, { error: 'Origem não permitida.' });

  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return send(res, 503, { error: 'Assistente indisponível no momento.' });

  const fwd = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  const ip = fwd || (req.socket && req.socket.remoteAddress) || 'unknown';
  if (rateLimited(ip, Date.now())) {
    return send(res, 429, { error: 'Muitas perguntas seguidas. Tente novamente em instantes.' });
  }

  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (_) { body = null; }
  }
  const messages = sanitizeMessages(body && body.messages);
  if (!messages) return send(res, 400, { error: 'Requisição inválida.' });

  let result = await callDeepSeek(apiKey, messages);
  if (result.error) {
    console.error('deepseek_attempt_1_failed', result.error);
    result = await callDeepSeek(apiKey, messages);
  }
  if (result.error) {
    console.error('deepseek_attempt_2_failed', result.error);
    return send(res, 502, { error: 'O assistente não respondeu agora.' });
  }
  return send(res, 200, parseModelOutput(result.reply));
};

module.exports._resetRateLimit = () => hits.clear();
module.exports._toUpstreamMessages = toUpstreamMessages;
module.exports._parseModelOutput = parseModelOutput;
module.exports.CARD_IDS = CARD_IDS;
