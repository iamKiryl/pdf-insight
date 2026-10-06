/** Transport and analysis-loop behaviour of the TS Worker (fake bindings, NOT live AI). */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import worker, { type Env } from '../src/index';

const here = dirname(fileURLToPath(import.meta.url));
const offer = JSON.parse(readFileSync(join(here, 'parity/offer.json'), 'utf-8')) as {
  request: Record<string, unknown>;
  scenarios: { label: string; payload: Record<string, unknown>; result: unknown }[];
};
const oracle = offer.scenarios.find((s) => s.label === 'oracle');
if (!oracle) throw new Error('missing oracle scenario');
const ORIGIN = 'https://iamkiryl.github.io';
const URL_ANALYZE = 'https://api.example/api/analyze';

class FakeAI {
  calls: Record<string, unknown>[] = [];
  constructor(private readonly answers: unknown[]) {}
  run = (_model: string, inputs: Record<string, unknown>): Promise<unknown> => {
    this.calls.push(inputs);
    const answer = this.answers.shift();
    if (answer instanceof Error) return Promise.reject(answer);
    if (answer === 'hang') return new Promise(() => undefined);
    return Promise.resolve({
      response: answer,
      usage: { prompt_tokens: 10, completion_tokens: 5 },
    });
  };
}

const limiter = (success = true, broken = false) => ({
  keys: [] as string[],
  limit(options: { key: string }) {
    this.keys.push(options.key);
    return broken ? Promise.reject(new Error('binding failure')) : Promise.resolve({ success });
  },
});

function env(ai: FakeAI | null, vars: Record<string, string> = {}, limiters = true): Env {
  return {
    ENVIRONMENT: 'production',
    ALLOWED_ORIGINS: ORIGIN,
    ...vars,
    ...(ai ? { AI: ai } : {}),
    ...(limiters ? { ANALYZE_IP_LIMITER: limiter(), ANALYZE_GLOBAL_LIMITER: limiter() } : {}),
  };
}

function post(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(URL_ANALYZE, {
    method: 'POST',
    headers: { 'content-type': 'application/json', origin: ORIGIN, ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

const call = (request: Request, e: Env) => worker.fetch(request, e);
const code = async (response: Response) =>
  ((await response.json()) as { error: { code: string } }).error.code;

afterEach(() => {
  vi.restoreAllMocks();
});

describe('routes, CORS and body bounds', () => {
  it('health reports bindings and mode without calling AI', async () => {
    const response = await call(new Request('https://api.example/api/health'), env(new FakeAI([])));
    expect(await response.json()).toEqual({
      status: 'ok',
      environment: 'production',
      aiBinding: true,
      rateLimiter: true,
      mode: 'compact',
    });
  });

  it('rejects foreign origins, answers preflight, adds CORS to allowed responses', async () => {
    const foreign = await call(post({}, { origin: 'https://evil.example' }), env(new FakeAI([])));
    expect([foreign.status, await code(foreign), foreign.headers.get('vary')]).toEqual([
      403,
      'ORIGIN_NOT_ALLOWED',
      'Origin',
    ]);
    const preflight = await call(
      new Request(URL_ANALYZE, { method: 'OPTIONS', headers: { origin: `${ORIGIN}/` } }),
      env(null),
    );
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get('access-control-allow-methods')).toBe('GET, POST, OPTIONS');
    const health = await call(
      new Request('https://api.example/api/health', { headers: { origin: ORIGIN } }),
      env(null),
    );
    expect(health.headers.get('access-control-allow-origin')).toBe(ORIGIN);
  });

  it('enforces content type and declared/streamed size before parsing', async () => {
    const e = env(new FakeAI([]));
    expect(await code(await call(post('{}', { 'content-type': 'text/plain' }), e))).toBe(
      'UNSUPPORTED_MEDIA_TYPE',
    );
    expect(await code(await call(post('{}', { 'content-length': 'abc' }), e))).toBe(
      'INVALID_REQUEST',
    );
    const big = 'x'.repeat(262_145);
    const streamed = await call(post(big), e);
    expect([streamed.status, await code(streamed)]).toEqual([413, 'BODY_TOO_LARGE']);
  });

  it('unknown paths and methods are 404/405', async () => {
    expect((await call(new Request('https://api.example/api/analyze/'), env(null))).status).toBe(
      404,
    );
    expect((await call(new Request(URL_ANALYZE), env(null))).status).toBe(405);
  });
});

describe('rate limiting and request validation', () => {
  it('fails closed without limiter bindings in production and when a limiter breaks', async () => {
    expect(await code(await call(post(offer.request), env(new FakeAI([]), {}, false)))).toBe(
      'SERVICE_MISCONFIGURED',
    );
    const broken = { ...env(new FakeAI([])), ANALYZE_IP_LIMITER: limiter(true, true) };
    expect(await code(await call(post(offer.request), broken))).toBe('SERVICE_MISCONFIGURED');
  });

  it('returns 429 when either limiter refuses, before parsing the body', async () => {
    const ai = new FakeAI([]);
    const ipDenied = { ...env(ai), ANALYZE_IP_LIMITER: limiter(false) };
    const response = await call(post('not json', { 'cf-connecting-ip': '203.0.113.7' }), ipDenied);
    expect([response.status, await code(response)]).toEqual([429, 'RATE_LIMITED']);
    const globalDenied = { ...env(ai), ANALYZE_GLOBAL_LIMITER: limiter(false) };
    expect(await code(await call(post(offer.request), globalDenied))).toBe('RATE_LIMITED');
    expect(ai.calls).toHaveLength(0);
  });

  it('rejects malformed, inconsistent, too long and text-less requests without AI', async () => {
    const ai = new FakeAI([]);
    const e = env(ai);
    expect(await code(await call(post('{not json'), e))).toBe('INVALID_REQUEST');
    expect(await code(await call(post({ ...offer.request, pageCount: 3 }), e))).toBe(
      'INVALID_REQUEST',
    );
    expect(await code(await call(post({ ...offer.request, extra: 1 }), e))).toBe('INVALID_REQUEST');
    expect(await code(await call(post({ ...offer.request, pageCount: true }), e))).toBe(
      'INVALID_REQUEST',
    );
    const long = {
      fileName: 'd.pdf',
      pageCount: 2,
      pagesWithoutText: [],
      pages: [1, 2].map((page) => ({ page, text: 'Treść umowy. '.repeat(1_200) })),
    };
    expect(await code(await call(post(long), e))).toBe('DOCUMENT_TOO_LONG');
    const scan = {
      fileName: 'd.pdf',
      pageCount: 1,
      pagesWithoutText: [1],
      pages: [{ page: 1, text: '' }],
    };
    expect(await code(await call(post(scan), e))).toBe('NO_TEXT_LAYER');
    const short = {
      fileName: 'd.pdf',
      pageCount: 1,
      pagesWithoutText: [],
      pages: [{ page: 1, text: 'Krótko.' }],
    };
    expect(await code(await call(post(short), e))).toBe('INSUFFICIENT_CONTENT');
    expect(ai.calls).toHaveLength(0);
  });

  it('unsupported model or mode fails clearly', async () => {
    expect(
      await code(
        await call(
          post(offer.request),
          env(new FakeAI([]), { AI_MODEL: '@cf/meta/llama-3.1-8b-instruct-fp8' }),
        ),
      ),
    ).toBe('SERVICE_MISCONFIGURED');
    expect(
      await code(await call(post(offer.request), env(new FakeAI([]), { AI_MODE: 'chunked' }))),
    ).toBe('SERVICE_MISCONFIGURED');
  });
});

describe('analysis loop (fake AI)', () => {
  it('returns the Python-identical result; server owns file name and pages', async () => {
    const ai = new FakeAI([{ ...oracle.payload, fileName: 'inny.pdf', pages: 99 }]);
    const response = await call(post(offer.request), env(ai));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(oracle.result);
    expect(ai.calls).toHaveLength(1);
    expect(ai.calls[0]?.response_format).toEqual({
      type: 'json_schema',
      json_schema: expect.any(Object) as unknown,
    });
  });

  it('corrects invalid output exactly once', async () => {
    const ai = new FakeAI([{ ...oracle.payload, amountIds: [9999] }, oracle.payload]);
    expect((await call(post(offer.request), env(ai))).status).toBe(200);
    const correction = (ai.calls[1]?.messages as { content: string }[]).at(-1)?.content ?? '';
    expect(correction).toContain('amountIds.0: id 9999 is not a candidate');
    const twice = new FakeAI([
      { ...oracle.payload, amountIds: [9999] },
      'not json at all',
      oracle.payload,
    ]);
    expect(await code(await call(post(offer.request), env(twice)))).toBe('AI_INVALID_OUTPUT');
    expect(twice.calls).toHaveLength(2);
  });

  it('JSON-mode failure is a correctable invalid output; other provider errors are not retried', async () => {
    const jsonMode = new FakeAI([new Error("5024: JSON Mode couldn't be met"), oracle.payload]);
    expect((await call(post(offer.request), env(jsonMode))).status).toBe(200);
    expect(jsonMode.calls).toHaveLength(2);
    const logs: string[] = [];
    vi.spyOn(console, 'log').mockImplementation((line: string) => logs.push(line));
    const down = new FakeAI([new Error('AiError: 5025: something about the input Zielony Port')]);
    expect(await code(await call(post(offer.request), env(down)))).toBe('AI_UNAVAILABLE');
    expect(down.calls).toHaveLength(1);
    expect(logs.some((line) => line.includes('"providerCode":5025'))).toBe(true);
    expect(logs.join('\n')).not.toContain('Zielony');
    const quota = new FakeAI([
      new Error('4006: you have used up your daily free allocation of neurons'),
    ]);
    expect(await code(await call(post(offer.request), env(quota)))).toBe('AI_QUOTA_EXCEEDED');
  });

  it('times out per call within the overall budget, without a retry', async () => {
    const ai = new FakeAI(['hang']);
    const response = await call(post(offer.request), env(ai, { AI_TIMEOUT_SECONDS: '1' }));
    expect([response.status, await code(response)]).toEqual([504, 'AI_TIMEOUT']);
    expect(ai.calls).toHaveLength(1);
  });

  it('insufficient content from the model is a 422, never padded', async () => {
    const ai = new FakeAI([{ ...oracle.payload, insufficientContent: true }]);
    expect(await code(await call(post(offer.request), env(ai)))).toBe('INSUFFICIENT_CONTENT');
  });

  it('logs numbers and labels only, never document text', async () => {
    const logs: string[] = [];
    vi.spyOn(console, 'log').mockImplementation((line: string) => logs.push(line));
    await call(post(offer.request), env(new FakeAI([oracle.payload])));
    const text = logs.join('\n');
    expect(text).toContain('"event":"analyze"');
    expect(text).not.toMatch(/Baltic|EnergyWatch|Zielony|96 000/u);
  });
});
