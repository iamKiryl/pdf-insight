/**
 * Conservative sentence counting, identical to backend/src/pdf_insight/sentences.py
 * (see contracts/README.md). Ambiguous boundaries (after abbreviations, initials or before a
 * digit) count as non-boundaries for `min` and as boundaries for `max`.
 */

const ABBREVIATIONS = new Set([
  // Polish
  'al', 'art', 'dr', 'godz', 'hab', 'inż', 'itd', 'itp', 'lit', 'mgr', 'mld', 'mln', 'nr', 'np',
  'ok', 'pkt', 'pn', 'por', 'poz', 'prof', 'pt', 'r', 'sp', 'sz', 'tj', 'tys', 'ul', 'ust', 'wg',
  'ww', 'zob',
  // English
  'approx', 'ca', 'co', 'corp', 'dept', 'etc', 'fig', 'inc', 'jr', 'ltd', 'mr', 'mrs', 'ms', 'no',
  'sr', 'st', 'vs',
]); // prettier-ignore

const CANDIDATE = /([.!?…]+)["'”’»)\]]*\s+["'„“«([]*(\S)/gu;
const ENDS_WITH_TERMINAL = /[.!?…]["'”’»)\]]*$/u;
const TOKEN_BEFORE = /(?:\p{L}|\.)+$/u;
const UPPERCASE = /^\p{Lu}$/u;
const DIGIT = /^\p{Nd}$/u;

export interface SentenceCount {
  min: number;
  max: number;
  valid: boolean;
}

function isAmbiguousToken(textBeforeDot: string): boolean {
  const match = TOKEN_BEFORE.exec(textBeforeDot);
  if (!match) return false;
  const token = match[0].replace(/^\.+|\.+$/gu, '').toLowerCase();
  if (!token) return false;
  return Array.from(token).length === 1 || token.includes('.') || ABBREVIATIONS.has(token);
}

export function countSentences(text: string): SentenceCount {
  const stripped = text.trim();
  if (!stripped) return { min: 0, max: 0, valid: false };
  let definite = 0;
  let ambiguous = 0;
  for (const match of stripped.matchAll(CANDIDATE)) {
    const run = match[1] ?? '';
    const next = match[2] ?? '';
    if (DIGIT.test(next)) {
      ambiguous += 1;
    } else if (UPPERCASE.test(next)) {
      if (run === '.' && isAmbiguousToken(stripped.slice(0, match.index))) ambiguous += 1;
      else definite += 1;
    }
  }
  return {
    min: definite + 1,
    max: definite + ambiguous + 1,
    valid: ENDS_WITH_TERMINAL.test(stripped),
  };
}

export function sentenceCountWithin(text: string, low: number, high: number): boolean {
  const result = countSentences(text);
  return result.valid && result.min <= high && result.max >= low;
}
