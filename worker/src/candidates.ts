/**
 * Candidate amounts and dates with source contexts — port of backend candidates.py (rules and
 * constants unchanged; see the Python module docstring for the full description).
 */
import type { AnalyzeRequest } from './contract';
import { MAX_CANDIDATES } from './contract';
import {
  CURRENCY_AFTER,
  CURRENCY_BEFORE,
  NUMBER_SEARCH,
  amountsOnPage,
  currencyCode,
  dateOccurrences,
  wraps,
} from './numbers';

const NUMBER = NUMBER_SEARCH();
import {
  W,
  WS,
  casefold,
  collapse,
  hasLetter,
  isSpace,
  pyFind,
  pyRfind,
  pyRstrip,
  pySplit,
  pyStrip,
  searchIn,
  findIter,
  startsUpper,
} from './text';

const WINDOW = 190;
const HEADER_LINES = 30;
const HEADING_LINES = 10;
const SHORT_LINE = 80;
const ROW_MAX = 160;
const PREFIX_MAX = 90;
const CONTEXT_MAX = 500;
const EDGE_LINES = 2;
const FOOTER_MIN_PAGES = 3;
export const OPEN = '»';
export const CLOSE = '«';

const UPPER_PL = 'A-ZĄĆĘŁŃÓŚŹŻ';
const NOT_INITIAL = `(?<![${WS}(\\-][${UPPER_PL}])`;
const SENTENCE_END = new RegExp(
  `${NOT_INITIAL}[.!?;][${WS}]+(?=[${UPPER_PL}])|\\n[ \\t]*\\n|\\n(?=[ \\t]*[0-9]+\\.[${WS}])`,
  'gu',
);
const SENTENCE_INSIDE = new RegExp(`${NOT_INITIAL}[.!?][${WS}]+[${UPPER_PL}]`, 'u');
const HEADING = new RegExp(`^[${WS}]*[${UPPER_PL}]{3,}(?:[${WS}]+[${UPPER_PL}]+)+(?![${W}])`, 'u');
const PARAGRAPH = new RegExp(`^[${WS}]*[0-9]+\\.[${WS}]`, 'u');
const TWO_DECIMALS = /[.,][0-9]{2}$/u;
const CURRENCY_WORDS = new Set(['zł', 'złotych', 'pln', 'eur', 'euro', '€', 'usd', '$']);
const PAGE_MARKER = new RegExp(
  `(?<![${W}])(?:strona|str\\.|page|seite)[${WS}]*#+[${WS}]*(?:z|of|/|von)[${WS}]*#+|(?<![${W}])(?:wersja|version|ver\\.|rev\\.?)[${WS}]*#`,
  'iu',
);
const DECLARED = new RegExp(
  `(?<![${W}])(?:Waluta|Currency)[${WS}]*:[${WS}]*[A-Z]{3}(?![${W}])`,
  'u',
);

export class TooManyCandidates extends Error {}

export interface Candidate {
  id: number;
  kind: 'amount' | 'date';
  page: number;
  start: number;
  end: number;
  context: string;
  value: number | null;
  currency: string | null;
  date: string | null;
}

function clean(text: string): string {
  return collapse(text.replaceAll(OPEN, '"').replaceAll(CLOSE, '"'));
}

function sentenceBounds(
  text: string,
  start: number,
  end: number,
): [number, number, boolean, boolean] {
  const low = Math.max(0, start - WINDOW);
  let left = low;
  for (const match of findIter(SENTENCE_END, text, low, start))
    left = match.index + match[0].length;
  const stop = searchIn(SENTENCE_END, text, end, Math.min(text.length, end + WINDOW));
  let right = stop ? stop.index + 1 : Math.min(text.length, end + WINDOW);
  const cutLeft = left === low && low > 0;
  if (cutLeft) {
    const space = pyFind(text, ' ', left, start);
    left = space !== -1 ? space + 1 : left;
  }
  const cutRight = !stop && right < text.length;
  if (cutRight) {
    const space = pyRfind(text, ' ', end, right);
    right = space !== -1 ? space : right;
  }
  return [left, right, cutLeft, cutRight];
}

function lineBounds(text: string, position: number): [number, number] {
  const start = position === 0 ? 0 : text.lastIndexOf('\n', position - 1) + 1;
  const end = text.indexOf('\n', position);
  return [start, end !== -1 ? end : text.length];
}

function precedingLines(text: string, lineStart: number, limit: number): string[] {
  const lines = lineStart ? text.slice(0, lineStart).split('\n').slice(0, -1) : [];
  return lines.slice(-limit).reverse();
}

function isHeader(line: string, aboveRow = false): boolean {
  const words = pySplit(line);
  if (words.length < 3 || NUMBER.test(line) || !hasLetter(line)) return false;
  const trimmed = pyRstrip(line);
  if (
    ['.', ':', ';', ','].some((end) => trimmed.endsWith(end)) ||
    line.includes('—') ||
    line.includes('–')
  ) {
    return false;
  }
  const capitalised = words.filter(startsUpper).length;
  return (
    line.includes('|') || capitalised * 2 >= words.length || (aboveRow && line.length <= ROW_MAX)
  );
}

function headerAbove(text: string, lineStart: number, rows: Map<string, boolean>): string | null {
  let below = text.slice(lineStart, lineBounds(text, lineStart)[1]);
  for (const line of precedingLines(text, lineStart, HEADER_LINES)) {
    if (isHeader(line, isTableRow(below, rows))) return collapse(line);
    const trimmed = pyRstrip(line);
    if (
      !pyStrip(line) ||
      PARAGRAPH.test(line) ||
      ['.', '!', '?'].some((end) => trimmed.endsWith(end))
    ) {
      return null;
    }
    below = line;
  }
  return null;
}

function headingAbove(text: string, lineStart: number): string | null {
  for (const line of precedingLines(text, lineStart, HEADING_LINES)) {
    if (HEADING.test(line)) return collapse(line);
  }
  return null;
}

/** Memoised per request (never module-level: no document text outlives the request). */
function isTableRow(line: string, rows?: Map<string, boolean>): boolean {
  if (rows) {
    let known = rows.get(line);
    if (known === undefined) {
      known = isTableRow(line);
      rows.set(line, known);
    }
    return known;
  }
  if (line.includes('|')) return true;
  if (SENTENCE_INSIDE.test(line)) return false;
  const money = amountsOnPage(0, line).filter(
    (t) => t.adjacentCurrency || TWO_DECIMALS.test(t.text),
  ).length;
  const cells = money + dateOccurrences(line).length;
  const words = pySplit(line).filter(
    (w) => hasLetter(w) && !CURRENCY_WORDS.has(casefold(w)),
  ).length;
  return cells >= 2 && words <= 2 * cells + 2;
}

function occurrence(text: string, kind: string, start: number, end: number): [number, number] {
  if (kind !== 'amount') return [start, end];
  const after = CURRENCY_AFTER.exec(text.slice(end, end + 12));
  if (after?.[1] && currencyCode(after[1])) return [start, end + after[0].length];
  const window = text.slice(Math.max(0, start - 6), start);
  const before = CURRENCY_BEFORE.exec(window);
  if (before?.[1] && currencyCode(before[1])) return [start - (window.length - before.index), end];
  return [start, end];
}

function bounds(
  text: string,
  start: number,
  end: number,
  wrapSpans: [number, number][],
  rows: Map<string, boolean>,
): [number, number, string | null, boolean, boolean] {
  const [lineStart, lineEnd] = lineBounds(text, start);
  const line = text.slice(lineStart, lineEnd);
  const crossed = wrapSpans.some(
    ([a, b]) => (a < lineEnd && lineEnd < b) || (a < lineStart - 1 && lineStart - 1 < b),
  );
  const onLine = end <= lineEnd && !crossed;
  if (onLine && isTableRow(line, rows))
    return [lineStart, lineEnd, headerAbove(text, lineStart, rows), false, false];
  if (onLine && collapse(line).length <= SHORT_LINE && text.slice(lineStart, start).includes(':')) {
    return [lineStart, lineEnd, headingAbove(text, lineStart), false, false];
  }
  if (onLine && line.length <= ROW_MAX && !(PARAGRAPH.test(line) || SENTENCE_INSIDE.test(line))) {
    const header = headerAbove(text, lineStart, rows);
    const sentence = pyRstrip(line).endsWith('.') && pySplit(line).length >= 8;
    if (header && !sentence) return [lineStart, lineEnd, header, false, false];
  }
  const [left, right, cutLeft, cutRight] = sentenceBounds(text, start, end);
  return [left, right, null, cutLeft, cutRight];
}

function fit(
  page: number,
  prefixIn: string | null,
  beforeIn: string,
  value: string,
  afterIn: string,
  cutLeftIn: boolean,
  cutRightIn: boolean,
): string {
  let prefix = prefixIn;
  let [before, after, cutLeft, cutRight] = [beforeIn, afterIn, cutLeftIn, cutRightIn];
  if (prefix && prefix.length > PREFIX_MAX) {
    const head = prefix.slice(0, PREFIX_MAX);
    const space = head.lastIndexOf(' ');
    prefix = (space === -1 ? head : head.slice(0, space)) + ' …';
  }
  const head = `s. ${page}: ` + (prefix ? `[${prefix}] ` : '');
  const marked = `${OPEN}${value}${CLOSE}`;
  const room = CONTEXT_MAX - head.length - marked.length - 4;
  if (before.length + after.length > room) {
    const keepLeft = Math.min(
      before.length,
      Math.max(Math.floor((room * 2) / 3), room - after.length),
    );
    const keepRight = room - keepLeft;
    if (keepLeft < before.length) {
      const tail = before.slice(before.length - keepLeft);
      const space = tail.indexOf(' ');
      before = space === -1 ? tail : tail.slice(space + 1);
      cutLeft = true;
    }
    if (keepRight < after.length) {
      const headPart = after.slice(0, Math.max(0, keepRight));
      const space = headPart.lastIndexOf(' ');
      after = space === -1 ? headPart : headPart.slice(0, space);
      cutRight = true;
    }
  }
  before = (cutLeft ? '… ' : '') + before;
  after = after + (cutRight ? ' …' : '');
  return head + before + marked + after;
}

function context(
  text: string,
  page: number,
  kind: string,
  start: number,
  end: number,
  wrapSpans: [number, number][],
  rows: Map<string, boolean>,
): string {
  const [left, right, prefix, cutLeft, cutRight] = bounds(text, start, end, wrapSpans, rows);
  let [occStart, occEnd] = occurrence(text, kind, start, end);
  occStart = Math.max(left, occStart);
  occEnd = Math.min(right, occEnd);
  let before = clean(text.slice(left, occStart));
  const value = clean(text.slice(occStart, occEnd));
  let after = clean(text.slice(occEnd, right));
  before = before && isSpace(text[occStart - 1]) ? before + ' ' : before;
  after = after && isSpace(text[occEnd]) ? ' ' + after : after;
  const header = prefix ? clean(prefix).replaceAll('[', '(').replaceAll(']', ')') : prefix;
  return fit(page, header, before, value, after, cutLeft, cutRight);
}

/** Line spans of repeated running headers/footers carrying page-numbering or version marks. */
export function metadataSpans(request: AnalyzeRequest): Map<number, [number, number][]> {
  const seen = new Map<string, { page: number; start: number; end: number; dates: string }[]>();
  for (const page of request.pages) {
    if (!hasLetter(page.text)) continue;
    const offsets: [number, number][] = [];
    let position = 0;
    for (const line of page.text.split('\n')) {
      if (pyStrip(line)) offsets.push([position, position + line.length]);
      position += line.length + 1;
    }
    const edges = [...offsets.slice(0, EDGE_LINES), ...offsets.slice(-EDGE_LINES)];
    const unique = new Map(edges.map((edge) => [`${edge[0]}:${edge[1]}`, edge]));
    for (const [start, end] of unique.values()) {
      const line = page.text.slice(start, end);
      const key = collapse(line).replace(/[0-9]+/gu, '#');
      if (PAGE_MARKER.test(key)) {
        const dates = [...new Set(dateOccurrences(line).map(([iso]) => iso))].sort().join(',');
        const list = seen.get(key) ?? [];
        list.push({ page: page.page, start, end, dates });
        seen.set(key, list);
      }
    }
  }
  const spans = new Map<number, [number, number][]>();
  for (const occurrences of seen.values()) {
    const pages = new Set(occurrences.map((o) => o.page));
    const sameDates = new Set(occurrences.map((o) => o.dates)).size === 1;
    if (pages.size >= FOOTER_MIN_PAGES && sameDates) {
      for (const o of occurrences)
        spans.set(o.page, [...(spans.get(o.page) ?? []), [o.start, o.end]]);
    }
  }
  return spans;
}

type Found = [page: number, start: number, kind: 'amount' | 'date', value: number | null, currency: string | null, date: string | null, end: number]; // prettier-ignore

export function extractCandidates(request: AnalyzeRequest): Candidate[] {
  const found: Found[] = [];
  const metadata = metadataSpans(request);
  for (const page of request.pages) {
    if (!hasLetter(page.text)) continue;
    const text = page.text;
    const skip = metadata.get(page.page) ?? [];
    const inMetadata = (position: number) => skip.some(([s, e]) => s <= position && position < e);
    const declared = DECLARED.test(text);
    for (const token of amountsOnPage(page.page, text)) {
      if (token.currency === null || inMetadata(token.start)) continue;
      if (!token.adjacentCurrency && !(declared && TWO_DECIMALS.test(token.text))) continue;
      found.push([page.page, token.start, 'amount', token.value, token.currency, null, token.end]);
    }
    for (const [iso, start, end] of dateOccurrences(text)) {
      if (!inMetadata(start)) found.push([page.page, start, 'date', null, null, iso, end]);
    }
  }
  if (found.length > MAX_CANDIDATES) throw new TooManyCandidates();
  found.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const texts = new Map(request.pages.map((p) => [p.page, p.text]));
  const wrapSpans = new Map(
    request.pages.map((p) => [
      p.page,
      wraps(p.text).joined.map(([a, b]) => [a, b] as [number, number]),
    ]),
  );
  const rows = new Map<string, boolean>(); // per-request memo of line classification
  return found.map(([page, start, kind, value, currency, date, end], i) => ({
    id: i + 1,
    kind,
    page,
    start,
    end,
    context: context(
      texts.get(page) ?? '',
      page,
      kind,
      start,
      end,
      wrapSpans.get(page) ?? [],
      rows,
    ),
    value,
    currency,
    date,
  }));
}
