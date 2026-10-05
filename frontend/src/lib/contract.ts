import codes from '../../../contracts/codes.json';
import limits from '../../../contracts/limits.json';

/** Shared contract data: imported from contracts/ so frontend and backend use one source. */
export const LIMITS = {
  maxFileBytes: limits.maxFileBytes,
  maxBodyBytes: limits.maxBodyBytes,
  maxPages: limits.maxPages,
  maxPageChars: limits.maxPageChars,
  maxTotalChars: limits.maxTotalChars,
  minTotalLetters: limits.minTotalLetters,
  summarySentences: [limits.summarySentences[0] ?? 3, limits.summarySentences[1] ?? 5] as const,
  keyPoints: [limits.keyPoints[0] ?? 3, limits.keyPoints[1] ?? 7] as const,
  maxKeywords: limits.maxKeywords,
  clientTimeoutMs: limits.clientTimeoutMs,
} as const;

export const LANGUAGES: ReadonlySet<string> = new Set(codes.languages);
export const CURRENCIES: ReadonlySet<string> = new Set(codes.currencies);

export const DOCUMENT_TYPES = ['faktura', 'umowa', 'oferta', 'raport', 'inne'] as const;

const LETTER = /\p{L}/u;

/** A page "has text" when it contains at least one Unicode letter (same rule as the backend). */
export function hasLetter(text: string): boolean {
  return LETTER.test(text);
}

export function countLetters(text: string): number {
  return text.match(/\p{L}/gu)?.length ?? 0;
}
