'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const handler = require('../api/chat.js');

const ORIGIN = 'https://sandymarques.github.io';

function makeRes() {
  return {
    statusCode: 0,
    headers: {},
    body: '',
    setHeader(k, v) { this.headers[k.toLowerCase()] = v; },
    end(b) { this.body = b || ''; },
    json() { return JSON.parse(this.body); },
  };
}

function makeReq({ method = 'POST', origin = ORIGIN, body, ip = '1.1.1.1' } = {}) {
  return { method, headers: { origin, 'x-forwarded-for': ip }, body, socket: {} };
}

test.beforeEach(() => {
  handler._resetRateLimit();
  process.env.DEEPSEEK_API_KEY = 'test-key';
  delete process.env.ALLOWED_ORIGINS;
});

test('OPTIONS de origem permitida retorna 204 com CORS', async () => {
  const res = makeRes();
  await handler(makeReq({ method: 'OPTIONS' }), res);
  assert.equal(res.statusCode, 204);
  assert.equal(res.headers['access-control-allow-origin'], ORIGIN);
});

test('origem não permitida é bloqueada', async () => {
  const res = makeRes();
  await handler(makeReq({ origin: 'https://evil.example', body: { messages: [{ role: 'user', content: 'oi' }] } }), res);
  assert.equal(res.statusCode, 403);
  assert.equal(res.headers['access-control-allow-origin'], undefined);
});

test('sem chave configurada retorna 503', async () => {
  delete process.env.DEEPSEEK_API_KEY;
  const res = makeRes();
  await handler(makeReq({ body: { messages: [{ role: 'user', content: 'oi' }] } }), res);
  assert.equal(res.statusCode, 503);
});

test('corpo inválido retorna 400', async () => {
  for (const body of [{}, { messages: [] }, { messages: [{ role: 'system', content: 'x' }] },
    { messages: [{ role: 'assistant', content: 'x' }] }, { messages: [{ role: 'user', content: '  ' }] }]) {
    const res = makeRes();
    await handler(makeReq({ body }), res);
    assert.equal(res.statusCode, 400);
  }
});

test('resposta válida usa a chave só no servidor e limita o contexto', async () => {
  const original = global.fetch;
  let captured;
  global.fetch = async (url, opts) => {
    captured = { url, opts };
    return { ok: true, json: async () => ({ choices: [{ message: { content: ' Olá! ' } }] }) };
  };
  try {
    const long = 'a'.repeat(2000);
    const res = makeRes();
    await handler(makeReq({ body: { messages: [{ role: 'user', content: long }] } }), res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.json().reply, 'Olá!');
    assert.deepEqual(res.json().cards, []);
    const sentBody = JSON.parse(captured.opts.body);
    assert.equal(sentBody.response_format.type, 'json_object');
    assert.equal(captured.url, 'https://api.deepseek.com/chat/completions');
    assert.equal(captured.opts.headers.Authorization, 'Bearer test-key');
    const sent = JSON.parse(captured.opts.body);
    assert.equal(sent.messages[0].role, 'system');
    assert.equal(sent.messages[1].content.length, 500);
    assert.ok(sent.max_tokens <= 600);
    assert.ok(!res.body.includes('test-key'));
  } finally {
    global.fetch = original;
  }
});

test('falha do DeepSeek retorna 502 sem vazar detalhes', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: false, status: 401, json: async () => ({}) });
  try {
    const res = makeRes();
    await handler(makeReq({ body: { messages: [{ role: 'user', content: 'oi' }] } }), res);
    assert.equal(res.statusCode, 502);
  } finally {
    global.fetch = original;
  }
});

test('rate limit por IP retorna 429', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: true, json: async () => ({ choices: [{ message: { content: 'ok' } }] }) });
  try {
    let last;
    for (let i = 0; i < 9; i += 1) {
      last = makeRes();
      await handler(makeReq({ body: { messages: [{ role: 'user', content: 'oi' }] }, ip: '9.9.9.9' }), last);
    }
    assert.equal(last.statusCode, 429);
  } finally {
    global.fetch = original;
  }
});

test('JSON do modelo: filtra cartões fora da lista e limita sugestões', () => {
  const out = handler._parseModelOutput(JSON.stringify({
    text: ' Sim! ',
    cards: ['tapioca', 'hack', 'tapioca', 'rag', 'blog', 'contato'],
    suggestions: ['a', 'b'.repeat(200), 3, 'c', 'd'],
  }));
  assert.equal(out.reply, 'Sim!');
  assert.deepEqual(out.cards, ['tapioca', 'rag', 'blog']);
  assert.equal(out.suggestions.length, 3);
  assert.equal(out.suggestions[1].length, 80);
});

test('saída sem JSON vira texto puro, sem cartões', () => {
  const out = handler._parseModelOutput('Resposta simples.');
  assert.deepEqual(out, { reply: 'Resposta simples.', cards: [], suggestions: [] });
  const wrapped = handler._parseModelOutput('```json\n{"text":"Oi","cards":["curriculo"]}\n```');
  assert.equal(wrapped.reply, 'Oi');
  assert.deepEqual(wrapped.cards, ['curriculo']);
});

test('resposta JSON completa chega ao cliente', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({ text: 'Veja o caso.', cards: ['tapioca'], suggestions: ['Quais telas tem?'] }) } }] }) });
  try {
    const res = makeRes();
    await handler(makeReq({ body: { messages: [{ role: 'user', content: 'tapioca?' }] } }), res);
    assert.deepEqual(res.json(), { reply: 'Veja o caso.', cards: ['tapioca'], suggestions: ['Quais telas tem?'] });
  } finally {
    global.fetch = original;
  }
});

test('histórico do assistente é reenviado em JSON ao DeepSeek', async () => {
  const original = global.fetch;
  let sent;
  global.fetch = async (url, opts) => {
    sent = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({ text: 'ok' }) } }] }) };
  };
  try {
    const res = makeRes();
    await handler(makeReq({ body: { messages: [
      { role: 'user', content: 'oi' },
      { role: 'assistant', content: 'Olá! Resposta antiga em texto puro.' },
      { role: 'user', content: 'e agora?' },
    ] } }), res);
    assert.equal(res.statusCode, 200);
    const assistant = sent.messages.find((m) => m.role === 'assistant');
    assert.deepEqual(JSON.parse(assistant.content), { text: 'Olá! Resposta antiga em texto puro.', cards: [], suggestions: [] });
  } finally {
    global.fetch = original;
  }
});

test('conteúdo vazio do modelo: tenta de novo e usa a segunda resposta', async () => {
  const original = global.fetch;
  let calls = 0;
  global.fetch = async () => {
    calls += 1;
    const content = calls === 1 ? '' : JSON.stringify({ text: 'Agora foi.', cards: ['blog'] });
    return { ok: true, json: async () => ({ choices: [{ message: { content } }] }) };
  };
  const origErr = console.error; console.error = () => {};
  try {
    const res = makeRes();
    await handler(makeReq({ body: { messages: [{ role: 'user', content: 'oi' }] } }), res);
    assert.equal(calls, 2);
    assert.equal(res.statusCode, 200);
    assert.deepEqual(res.json().cards, ['blog']);
  } finally {
    global.fetch = original; console.error = origErr;
  }
});

test('falha nas duas tentativas retorna 502', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  const origErr = console.error; console.error = () => {};
  try {
    const res = makeRes();
    await handler(makeReq({ body: { messages: [{ role: 'user', content: 'oi' }] } }), res);
    assert.equal(res.statusCode, 502);
  } finally {
    global.fetch = original; console.error = origErr;
  }
});
