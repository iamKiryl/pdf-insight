/** API errors with safe Polish messages — identical to backend/src/pdf_insight/errors.py. */

interface ErrorSpec {
  status: number;
  message: string;
  retryable: boolean;
}

export const ERRORS = {
  INVALID_REQUEST: { status: 400, message: 'Nieprawidłowe żądanie. Odśwież stronę i spróbuj ponownie.', retryable: false },
  ORIGIN_NOT_ALLOWED: { status: 403, message: 'Ta strona nie ma dostępu do usługi analizy.', retryable: false },
  BODY_TOO_LARGE: { status: 413, message: 'Tekst dokumentu jest zbyt duży, aby wysłać go do analizy.', retryable: false },
  DOCUMENT_TOO_LONG: {
    status: 413,
    message: 'Dokument przekracza długość tekstu obsługiwaną przez tę usługę. Tekst nie jest obcinany — użyj krótszego dokumentu.',
    retryable: false,
  },
  UNSUPPORTED_MEDIA_TYPE: { status: 415, message: 'Nieobsługiwany format żądania.', retryable: false },
  TOO_MANY_CANDIDATES: {
    status: 422,
    message: 'Dokument zawiera zbyt wiele kwot i dat, aby przeanalizować go w tym trybie. Nic nie zostało pominięte — użyj krótszego dokumentu.',
    retryable: false,
  },
  NO_TEXT_LAYER: {
    status: 422,
    message: 'Dokument nie zawiera warstwy tekstowej (prawdopodobnie jest skanem). Rozpoznawanie tekstu (OCR) nie jest jeszcze dostępne — użyj PDF z tekstem.',
    retryable: false,
  },
  INSUFFICIENT_CONTENT: {
    status: 422,
    message: 'Dokument zawiera za mało treści, aby rzetelnie przygotować podsumowanie i co najmniej 3 kluczowe punkty.',
    retryable: false,
  },
  RATE_LIMITED: { status: 429, message: 'Zbyt wiele analiz w krótkim czasie. Odczekaj minutę i spróbuj ponownie.', retryable: true },
  AI_INVALID_OUTPUT: { status: 502, message: 'Model AI zwrócił niepoprawną odpowiedź (także po ponownej próbie). Spróbuj ponownie.', retryable: true },
  AI_UNAVAILABLE: { status: 502, message: 'Usługa AI jest chwilowo niedostępna. Spróbuj ponownie za chwilę.', retryable: true },
  AI_QUOTA_EXCEEDED: { status: 503, message: 'Wyczerpano dzienny limit analiz AI. Spróbuj ponownie później.', retryable: true },
  SERVICE_MISCONFIGURED: { status: 503, message: 'Usługa analizy jest niepoprawnie skonfigurowana. Spróbuj później.', retryable: false },
  AI_TIMEOUT: { status: 504, message: 'Analiza trwała zbyt długo i została przerwana. Spróbuj ponownie.', retryable: true },
  INTERNAL_ERROR: { status: 500, message: 'Wystąpił nieoczekiwany błąd serwera.', retryable: true },
} as const satisfies Record<string, ErrorSpec>; // prettier-ignore

export type ErrorCode = keyof typeof ERRORS;

export class ApiError extends Error {
  constructor(readonly code: ErrorCode) {
    super(code);
  }
}

export function errorBody(code: ErrorCode) {
  const spec = ERRORS[code];
  return { error: { code, message: spec.message, retryable: spec.retryable } };
}

/** Invalid model output: field paths and fixed reasons only, never input values. */
export class InvalidModelOutput extends Error {
  constructor(readonly problems: string[]) {
    super(problems.join('; '));
  }
}

export type ProviderErrorKind = 'invalid_output' | 'quota' | 'unavailable';

export class AIProviderError extends Error {
  constructor(
    readonly kind: ProviderErrorKind,
    readonly code: number | null = null,
  ) {
    super(kind);
  }
}

/** Map provider error text to a category without exposing the text (runtime.py). */
export function classifyProviderError(message: string): ProviderErrorKind {
  const text = message.toLowerCase();
  if (text.includes("json mode couldn't be met") || text.includes('json mode could not be met')) {
    return 'invalid_output';
  }
  if (
    ['4006', 'neuron', 'quota', 'daily free allocation'].some((marker) => text.includes(marker))
  ) {
    return 'quota';
  }
  return 'unavailable';
}

/** The first 4-digit Workers AI error code in the message, or null — never the text. */
export function providerErrorCode(message: string): number | null {
  const match = /(?<![0-9])([1-9][0-9]{3})(?![0-9])/u.exec(message);
  return match?.[1] ? Number(match[1]) : null;
}
