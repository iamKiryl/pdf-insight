/** Runtime settings from Worker vars (config.py semantics; only the compact mode exists here). */

export const DEFAULT_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';
const DEV_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173'];

export interface Settings {
  environment: 'production' | 'development';
  allowedOrigins: ReadonlySet<string>;
  maxBodyBytes: number;
  aiModel: string;
  /** "compact" is the only mode of this Worker; anything else fails closed. */
  aiMode: string;
  aiTimeoutSeconds: number;
  aiTotalBudgetSeconds: number;
  aiMaxTokens: number;
}

function clampInt(raw: string | undefined, fallback: number, low: number, high: number): number {
  const value = raw === undefined || !/^[+-]?\d+$/u.test(raw.trim()) ? fallback : Number(raw);
  return Math.min(Math.max(value, low), high);
}

function clampFloat(raw: string | undefined, fallback: number, low: number, high: number): number {
  const parsed = raw === undefined ? Number.NaN : Number(raw);
  const value = Number.isFinite(parsed) ? parsed : fallback;
  return Math.min(Math.max(value, low), high);
}

export function loadSettings(get: (name: string) => string | undefined): Settings {
  const environment = get('ENVIRONMENT') === 'development' ? 'development' : 'production';
  const origins = new Set(
    (get('ALLOWED_ORIGINS') ?? '')
      .split(',')
      .map((origin) => origin.trim().replace(/\/+$/u, ''))
      .filter(Boolean),
  );
  if (environment === 'development') for (const origin of DEV_ORIGINS) origins.add(origin);
  return {
    environment,
    allowedOrigins: origins,
    maxBodyBytes: clampInt(get('MAX_BODY_BYTES'), 262_144, 1_024, 1_048_576),
    aiModel: get('AI_MODEL') || DEFAULT_MODEL,
    aiMode: get('AI_MODE') || 'compact',
    aiTimeoutSeconds: clampFloat(get('AI_TIMEOUT_SECONDS'), 40, 1, 60),
    aiTotalBudgetSeconds: clampFloat(get('AI_TOTAL_BUDGET_SECONDS'), 55, 1, 90),
    aiMaxTokens: clampInt(get('AI_MAX_TOKENS'), 2048, 256, 4096),
  };
}
