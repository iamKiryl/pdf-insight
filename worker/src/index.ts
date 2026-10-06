/**
 * PDF Insight API — compact mode as a TypeScript Cloudflare Worker (candidate replacement for the
 * Python Worker in backend/). Same public API: GET /api/health, POST /api/analyze.
 *
 * Order of checks (as in backend middleware.py + app.py): exact origin allowlist and preflight →
 * content type and declared length → body streamed with a MAX_BODY_BYTES + 1 cap before parsing →
 * shared rate limiting (fail closed in production) → JSON + strict request validation → compact
 * analysis. Errors are the same JSON bodies and statuses; logs carry numbers only.
 */
import { analyzeCompact, ModelUsage, type AIClient } from './analyze';
import { loadSettings, type Settings } from './config';
import {
  AnalyzeRequestSchema,
  COMPACT_MAX_CHARS,
  MIN_TOTAL_LETTERS,
  totalChars,
  totalLetters,
  type AnalyzeRequest,
} from './contract';
import {
  AIProviderError,
  ApiError,
  ERRORS,
  classifyProviderError,
  errorBody,
  providerErrorCode,
  type ErrorCode,
} from './errors';
import { logEvent } from './logs';
import { COMPACT_PROMPT_VERSION } from './prompt';

interface RateLimiter {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

interface AiBinding {
  run(model: string, inputs: Record<string, unknown>): Promise<unknown>;
}

export interface Env {
  AI?: AiBinding;
  ANALYZE_IP_LIMITER?: RateLimiter;
  ANALYZE_GLOBAL_LIMITER?: RateLimiter;
  [name: string]: unknown;
}

const ANALYZE_PATH = '/api/analyze';

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...headers },
  });
}

function error(code: ErrorCode, headers: Record<string, string> = {}): Response {
  return json(ERRORS[code].status, errorBody(code), headers);
}

function decodedPath(url: URL): string | null {
  try {
    return decodeURIComponent(url.pathname);
  } catch {
    return null;
  }
}

/** Header-only checks for POST /api/analyze (middleware.body_precheck). */
function bodyPrecheck(request: Request, limit: number): ErrorCode | null {
  const contentType = (request.headers.get('content-type') ?? '')
    .split(';')[0]
    ?.trim()
    .toLowerCase();
  if (contentType !== 'application/json') return 'UNSUPPORTED_MEDIA_TYPE';
  const length = request.headers.get('content-length');
  if (length === null) return null;
  if (!/^\s*[+-]?\d+\s*$/u.test(length)) return 'INVALID_REQUEST';
  const declared = Number(length);
  if (declared < 0) return 'INVALID_REQUEST';
  if (declared > limit) return 'BODY_TOO_LARGE';
  return null;
}

/** Reads at most limit + 1 bytes and cancels the rest of the stream. */
export async function readLimited(
  body: ReadableStream<Uint8Array> | null,
  limit: number,
): Promise<Uint8Array> {
  if (!body) return new Uint8Array();
  const cap = limit + 1;
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (size < cap) {
      const { done, value } = await reader.read();
      if (done) break;
      const kept = value.subarray(0, cap - size);
      chunks.push(kept);
      size += kept.length;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  const out = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

async function enforceRateLimit(env: Env, settings: Settings, clientKey: string): Promise<void> {
  const ip = env.ANALYZE_IP_LIMITER;
  const global = env.ANALYZE_GLOBAL_LIMITER;
  if (!ip || !global) {
    if (settings.environment === 'production') throw new ApiError('SERVICE_MISCONFIGURED');
    return; // development without bindings: explicitly unlimited (reported by /api/health)
  }
  let allowed: boolean;
  try {
    allowed = (await ip.limit({ key: `ip:${clientKey}` })).success === true;
    allowed = allowed && (await global.limit({ key: 'global' })).success === true;
  } catch {
    throw new ApiError('SERVICE_MISCONFIGURED'); // fail closed if the limiter breaks
  }
  if (!allowed) throw new ApiError('RATE_LIMITED');
}

function parseRequest(body: Uint8Array): AnalyzeRequest {
  let data: unknown;
  try {
    data = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(body));
  } catch {
    throw new ApiError('INVALID_REQUEST');
  }
  const parsed = AnalyzeRequestSchema.safeParse(data);
  if (!parsed.success) throw new ApiError('INVALID_REQUEST');
  const request = parsed.data;
  if (totalChars(request) > COMPACT_MAX_CHARS) throw new ApiError('DOCUMENT_TOO_LONG');
  if (request.pagesWithoutText.length === request.pageCount) throw new ApiError('NO_TEXT_LAYER');
  if (totalLetters(request) < MIN_TOTAL_LETTERS) throw new ApiError('INSUFFICIENT_CONTENT');
  return request;
}

function workersAI(binding: AiBinding): AIClient {
  return {
    async run(model, inputs) {
      try {
        return await binding.run(model, inputs);
      } catch (cause) {
        const text = cause instanceof Error ? cause.message : String(cause);
        throw new AIProviderError(classifyProviderError(text), providerErrorCode(text));
      }
    },
  };
}

async function analyzeRoute(
  request: Request,
  env: Env,
  settings: Settings,
  body: Uint8Array,
): Promise<Response> {
  const started = performance.now();
  const usage = new ModelUsage();
  let fields: Record<string, unknown> = {
    event: 'analyze',
    runtime: 'ts',
    model: settings.aiModel,
    promptVersion: COMPACT_PROMPT_VERSION,
    mode: settings.aiMode,
  };
  const ms = () => Math.round(performance.now() - started);
  try {
    if (settings.aiMode !== 'compact') throw new ApiError('SERVICE_MISCONFIGURED');
    await enforceRateLimit(env, settings, request.headers.get('cf-connecting-ip') ?? 'unknown');
    const parsed = parseRequest(body);
    fields = {
      ...fields,
      pageCount: parsed.pageCount,
      pagesWithoutText: parsed.pagesWithoutText.length,
      ocrPages: parsed.ocrPages.length,
      textChars: totalChars(parsed),
    };
    if (!env.AI) throw new ApiError('SERVICE_MISCONFIGURED');
    const outcome = await analyzeCompact(parsed, workersAI(env.AI), settings, usage);
    logEvent({
      ...fields,
      ...usage.logFields(),
      outcome: 'ok',
      status: 200,
      attempts: outcome.attempts,
      ms: ms(),
    });
    return json(200, outcome.result, { 'content-type': 'application/json' });
  } catch (cause) {
    const code: ErrorCode = cause instanceof ApiError ? cause.code : 'INTERNAL_ERROR';
    logEvent({
      ...fields,
      ...usage.logFields(),
      outcome: code,
      status: ERRORS[code].status,
      ms: ms(),
    });
    return error(code);
  }
}

async function route(request: Request, env: Env, settings: Settings): Promise<Response> {
  const url = new URL(request.url);
  const path = decodedPath(url);
  if (path === ANALYZE_PATH && request.method === 'POST') {
    const precheck = bodyPrecheck(request, settings.maxBodyBytes);
    if (precheck) return error(precheck);
    const body = await readLimited(request.body, settings.maxBodyBytes);
    if (body.length > settings.maxBodyBytes) return error('BODY_TOO_LARGE');
    return analyzeRoute(request, env, settings, body);
  }
  if (path === '/api/health' && request.method === 'GET') {
    return json(200, {
      status: 'ok',
      environment: settings.environment,
      aiBinding: Boolean(env.AI),
      rateLimiter: Boolean(env.ANALYZE_IP_LIMITER && env.ANALYZE_GLOBAL_LIMITER),
      mode: settings.aiMode,
    }, { 'content-type': 'application/json' }); // prettier-ignore
  }
  if (path === ANALYZE_PATH || path === '/api/health')
    return json(405, { detail: 'Method Not Allowed' });
  return json(404, { detail: 'Not Found' });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const settings = loadSettings((name) =>
      typeof env[name] === 'string' ? (env[name] as string) : undefined,
    );
    const origin = request.headers.get('origin');
    if (origin === null) return route(request, env, settings);
    const vary = { vary: 'Origin' };
    if (!settings.allowedOrigins.has(origin.replace(/\/+$/u, '')))
      return error('ORIGIN_NOT_ALLOWED', vary);
    const cors = { 'access-control-allow-origin': origin, ...vary };
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          ...cors,
          'access-control-allow-methods': 'GET, POST, OPTIONS',
          'access-control-allow-headers': 'Content-Type',
          'access-control-max-age': '600',
        },
      });
    }
    const response = await route(request, env, settings);
    const headers = new Headers(response.headers);
    for (const [key, value] of Object.entries(cors)) headers.set(key, value);
    return new Response(response.body, { status: response.status, headers });
  },
} satisfies ExportedHandler<Env>;
