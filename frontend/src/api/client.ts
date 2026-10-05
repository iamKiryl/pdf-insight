import { LIMITS } from '../lib/contract';
import { ApiErrorSchema, AnalysisResultSchema } from '../lib/schema';
import type { AnalysisResult, AnalyzeRequest } from '../lib/schema';

// Longer than the server's overall AI budget (contracts/limits.json), so the server's own timeout
// error normally arrives first. A failure ceiling, not a latency target.
export const CLIENT_TIMEOUT_MS = LIMITS.clientTimeoutMs;

export type ClientErrorCode =
  | 'NETWORK_ERROR'
  | 'CLIENT_TIMEOUT'
  | 'INVALID_RESPONSE'
  | 'CONFIG_MISSING'
  | 'CANCELLED'
  | (string & {});

export class ApiClientError extends Error {
  constructor(
    readonly code: ClientErrorCode,
    readonly serverMessage: string | null,
    readonly retryable: boolean,
    readonly status: number | null = null,
  ) {
    super(code);
    this.name = 'ApiClientError';
  }
}

export function apiBaseUrl(): string | null {
  const configured: unknown = import.meta.env.VITE_API_URL;
  if (typeof configured === 'string' && configured.trim())
    return configured.trim().replace(/\/+$/u, '');
  return import.meta.env.DEV ? 'http://localhost:8787' : null;
}

interface AnalyzeOptions {
  signal: AbortSignal;
  baseUrl?: string | null;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

/**
 * Sends exactly one request. There are no hidden retries: the backend retries invalid model output
 * once, and any further attempt is an explicit user action.
 */
export async function analyzeDocument(
  payload: AnalyzeRequest,
  {
    signal,
    baseUrl = apiBaseUrl(),
    fetchImpl = fetch,
    timeoutMs = CLIENT_TIMEOUT_MS,
  }: AnalyzeOptions,
): Promise<AnalysisResult> {
  if (!baseUrl) throw new ApiClientError('CONFIG_MISSING', null, false);
  const timeout = AbortSignal.timeout(timeoutMs);
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: AbortSignal.any([signal, timeout]),
    });
  } catch {
    throw abortReason(signal, timeout) ?? new ApiClientError('NETWORK_ERROR', null, true);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw (
      abortReason(signal, timeout) ??
      new ApiClientError(
        response.ok ? 'INVALID_RESPONSE' : 'NETWORK_ERROR',
        null,
        true,
        response.status,
      )
    );
  }

  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(body);
    if (parsed.success) {
      const { code, message, retryable } = parsed.data.error;
      throw new ApiClientError(code, message, retryable, response.status);
    }
    throw new ApiClientError('NETWORK_ERROR', null, true, response.status);
  }

  const parsed = AnalysisResultSchema.safeParse(body);
  if (!parsed.success) throw new ApiClientError('INVALID_RESPONSE', null, true, response.status);
  return parsed.data;
}

function abortReason(user: AbortSignal, timeout: AbortSignal): ApiClientError | null {
  if (user.aborted) return new ApiClientError('CANCELLED', null, false);
  if (timeout.aborted) return new ApiClientError('CLIENT_TIMEOUT', null, true);
  return null;
}
