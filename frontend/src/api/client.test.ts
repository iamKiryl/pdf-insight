import { describe, expect, it, vi } from 'vitest';
import { acceptedResult } from '../test/fixtures';
import type { AnalyzeRequest } from '../lib/schema';
import { ApiClientError, analyzeDocument } from './client';

const payload: AnalyzeRequest = {
  fileName: 'umowa.pdf',
  pageCount: 1,
  pages: [{ page: 1, text: 'Treść' }],
  pagesWithoutText: [],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function failure(promise: Promise<unknown>): Promise<ApiClientError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiClientError) return error;
    throw error;
  }
  throw new Error('expected failure');
}

const base = { baseUrl: 'https://api.example' };

describe('analyzeDocument', () => {
  it('posts once and returns a validated result', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(acceptedResult()));
    const result = await analyzeDocument(payload, {
      ...base,
      signal: new AbortController().signal,
      fetchImpl,
    });
    expect(result.document.type).toBe('umowa');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('https://api.example/api/analyze');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual(payload);
  });

  it('rejects a 200 response that fails the schema and does not retry', async () => {
    const bad = { ...acceptedResult(), keyPoints: ['Jeden.'] };
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(bad));
    const error = await failure(
      analyzeDocument(payload, { ...base, signal: new AbortController().signal, fetchImpl }),
    );
    expect(error.code).toBe('INVALID_RESPONSE');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('maps a server error body without retrying', async () => {
    const body = {
      error: { code: 'AI_INVALID_OUTPUT', message: 'Model AI zwrócił…', retryable: true },
    };
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(body, 502));
    const error = await failure(
      analyzeDocument(payload, { ...base, signal: new AbortController().signal, fetchImpl }),
    );
    expect(error).toMatchObject({ code: 'AI_INVALID_OUTPUT', retryable: true, status: 502 });
    expect(error.serverMessage).toBe('Model AI zwrócił…');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('maps network failures', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await failure(
      analyzeDocument(payload, { ...base, signal: new AbortController().signal, fetchImpl }),
    );
    expect(error.code).toBe('NETWORK_ERROR');
  });

  it('reports user cancellation as CANCELLED', async () => {
    const controller = new AbortController();
    const fetchImpl = vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }),
    );
    const pending = analyzeDocument(payload, { ...base, signal: controller.signal, fetchImpl });
    controller.abort();
    expect((await failure(pending)).code).toBe('CANCELLED');
  });

  it('reports a client timeout', async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Timeout', 'TimeoutError'));
          });
        }),
    );
    const pending = analyzeDocument(payload, {
      ...base,
      signal: new AbortController().signal,
      fetchImpl,
      timeoutMs: 20,
    });
    expect((await failure(pending)).code).toBe('CLIENT_TIMEOUT');
  });

  it('fails clearly when the backend URL is not configured', async () => {
    const error = await failure(
      analyzeDocument(payload, { baseUrl: null, signal: new AbortController().signal }),
    );
    expect(error.code).toBe('CONFIG_MISSING');
  });
});
