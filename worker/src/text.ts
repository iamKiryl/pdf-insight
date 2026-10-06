/**
 * Python-compatible text primitives. The compact path was specified and reviewed in Python
 * (backend/src/pdf_insight); these helpers reproduce the Python semantics the port relies on:
 * - whitespace = Python's str.isspace set (str.split/strip and the `\s` of `re`), which differs
 *   from JS `\s` (Python adds \x1c-\x1f and \x85; JS adds ﻿);
 * - word characters = Python's Unicode `\w`, approximated as [\p{L}\p{N}_] (JS `\w`/`\b` are ASCII);
 * - str.find/rfind with bounds, casefold, isalpha/isupper.
 * Known deviations (documented in worker/README.md): `\d` is ASCII here (Python also matches other
 * Unicode decimal digits) and lengths count UTF-16 units except where codePointLength is used.
 */

export const WS =
  '\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
export const W = '\\p{L}\\p{N}_';
const WS_RUN = new RegExp(`[${WS}]+`, 'gu');
const WS_CHAR = new RegExp(`^[${WS}]$`, 'u');
const LEADING = new RegExp(`^[${WS}]+`, 'u');
const TRAILING = new RegExp(`[${WS}]+$`, 'u');
const LETTER = /\p{L}/u;
const UPPER = /^\p{Lu}/u;

/** str.split() without arguments. */
export function pySplit(text: string): string[] {
  return text.split(WS_RUN).filter((part) => part !== '');
}

/** " ".join(text.split()) */
export function collapse(text: string): string {
  return pySplit(text).join(' ');
}

export function pyStrip(text: string): string {
  return text.replace(LEADING, '').replace(TRAILING, '');
}

export function pyRstrip(text: string): string {
  return text.replace(TRAILING, '');
}

export function isSpace(char: string | undefined): boolean {
  return char !== undefined && WS_CHAR.test(char);
}

export function hasLetter(text: string): boolean {
  return LETTER.test(text);
}

export function startsUpper(word: string): boolean {
  return UPPER.test(word);
}

export function countLetters(text: string): number {
  return text.match(/\p{L}/gu)?.length ?? 0;
}

/** len() of a Python str: code points, not UTF-16 units. */
export function codePointLength(text: string): number {
  let surrogates = 0;
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 0xdc00 && code <= 0xdfff) surrogates++;
  }
  return text.length - surrogates;
}

/** str.casefold(), close enough for the Latin/Polish text handled here. */
export function casefold(text: string): string {
  return text.toLowerCase().replace(/ß/gu, 'ss');
}

/** str.find(sub, start, end) */
export function pyFind(text: string, sub: string, start: number, end: number): number {
  const index = text.indexOf(sub, start);
  return index !== -1 && index + sub.length <= end ? index : -1;
}

/** str.rfind(sub, start, end) */
export function pyRfind(text: string, sub: string, start: number, end: number): number {
  if (end - sub.length < start) return -1;
  const index = text.lastIndexOf(sub, end - sub.length);
  return index >= start ? index : -1;
}

/** re.escape for building patterns from model-provided names. */
export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\/]/gu, '\\$&'); // '-' needs no escape outside classes
}

/**
 * Python's pattern.finditer(text, pos, endpos): lookbehind may see before pos, nothing after
 * endpos is visible. `pattern` must have the global flag.
 */
export function* findIter(
  pattern: RegExp,
  text: string,
  pos = 0,
  endpos = text.length,
): Generator<RegExpExecArray> {
  const view = endpos < text.length ? text.slice(0, endpos) : text;
  pattern.lastIndex = pos;
  for (;;) {
    const match = pattern.exec(view);
    if (match === null) return;
    if (match[0] === '') pattern.lastIndex++;
    yield match;
  }
}

/** Python's pattern.search(text, pos, endpos). */
export function searchIn(
  pattern: RegExp,
  text: string,
  pos = 0,
  endpos = text.length,
): RegExpExecArray | null {
  for (const match of findIter(pattern, text, pos, endpos)) return match;
  return null;
}
