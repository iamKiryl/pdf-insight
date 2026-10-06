/**
 * Bounded parsing of amounts and dates per page — port of backend/src/pdf_insight/numbers.py.
 * Same supported formats, the same line-wrap reconstruction (full prose line, reference-number
 * exclusion, ambiguous wraps rejected, never the suffix alone) and the same currency rules.
 */
import { CURRENCIES } from '../../frontend/src/lib/contract';
import { W, WS, hasLetter, pySplit } from './text';

const NUMBER =
  /(?<![0-9.,])([0-9]{1,3}(?:[   ][0-9]{3})+(?:,[0-9]{1,2})?|[0-9]{1,3}(?:\.[0-9]{3})+,[0-9]{1,2}|[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+,[0-9]{1,2}|[0-9]+\.[0-9]{1,2}|[0-9]+)(?![0-9]|[.,][0-9]|[  ]?%)/gu;
/** The NUMBER pattern without the global flag, for plain searches (candidates.py _NUMBER.search). */
export const NUMBER_SEARCH = (): RegExp => new RegExp(NUMBER.source, 'u');
const WRAP =
  /(?<![0-9.,])(?<prefix>[0-9]{1,3}(?:[   ][0-9]{3})*)[ \t]*\n[ \t]*(?<suffix>[0-9]{3}(?:[   ][0-9]{3})*(?:,[0-9]{1,2})?)(?![0-9]|[.,][0-9]|[  ]?%)/dgu;
const REFERENCE_BEFORE = new RegExp(
  `(?:(?<![${W}])(?:strona|str|s|z|nr|no|page|of|pkt|ust|art|poz|lp)\\.?|§)[${WS}]*$`,
  'iu',
);
export const WRAP_MIN_WORDS = 3;
export const WRAP_MIN_LINE = 60;
/** A currency marker may follow after one PDF line break ("184 500,00\nzł netto"). */
export const CURRENCY_AFTER = new RegExp(
  `^[ \\u00a0]*(?:\\n[ \\u00a0]*)?(zł|złotych|PLN|EUR|euro|€|USD|\\$|[A-Z]{3})(?![${W}])`,
  'u',
);
export const CURRENCY_BEFORE = /(PLN|EUR|€|USD|\$|[A-Z]{3})[  ]*$/u;
const PAGE_CURRENCY = new RegExp(
  `(?<![${W}])(?:Waluta|Currency)[${WS}]*:[${WS}]*([A-Z]{3})(?![${W}])`,
  'u',
);
const ALIASES: Record<string, string> = {
  zł: 'PLN',
  złotych: 'PLN',
  euro: 'EUR',
  '€': 'EUR',
  $: 'USD',
};

const PL_MONTHS = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia']; // prettier-ignore
const EN_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']; // prettier-ignore
const MONTH_INDEX = new Map<string, number>([
  ...PL_MONTHS.map((name, i) => [name, i + 1] as const),
  ...EN_MONTHS.map((name, i) => [name, i + 1] as const),
]);
const MONTH_NAMES = [...MONTH_INDEX.keys()].join('|');
type Part = 'y' | 'm' | 'd' | 'M';
const DATES: [RegExp, Part[]][] = [
  [/(?<![0-9])([0-9]{4})-([0-9]{2})-([0-9]{2})(?![0-9])/gu, ['y', 'm', 'd']],
  [/(?<![0-9.])([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})(?![0-9])/gu, ['d', 'm', 'y']],
  [
    new RegExp(`(?<![0-9])([0-9]{1,2})[${WS}]+(${MONTH_NAMES})[${WS}]+([0-9]{4})(?![0-9])`, 'giu'),
    ['d', 'M', 'y'],
  ],
  [
    new RegExp(
      `(?<![${W}])(${MONTH_NAMES})[${WS}]+([0-9]{1,2}),[${WS}]*([0-9]{4})(?![0-9])`,
      'giu',
    ),
    ['M', 'd', 'y'],
  ],
];

export interface AmountToken {
  page: number;
  value: number;
  currency: string | null;
  text: string;
  start: number;
  end: number;
  adjacentCurrency: boolean;
}

export function parseNumber(raw: string): number {
  let cleaned = raw.replace(/[   ]/gu, '');
  if (/^[0-9]{1,3}(?:\.[0-9]{3})+,[0-9]{1,2}$/u.test(cleaned)) {
    cleaned = cleaned.replaceAll('.', '').replace(',', '.');
  } else if (/^[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?$/u.test(cleaned)) {
    cleaned = cleaned.replaceAll(',', '');
  } else {
    cleaned = cleaned.replaceAll(',', '.');
  }
  return Number(cleaned);
}

export function currencyCode(code: string): string | null {
  const resolved = ALIASES[code] ?? ALIASES[code.toLowerCase()] ?? code;
  return CURRENCIES.has(resolved) ? resolved : null;
}

/** Line-wrapped grouped numbers to reconstruct, and start offsets never emitted on their own. */
export function wraps(text: string): { joined: [number, number, string][]; hidden: Set<number> } {
  const joined: [number, number, string][] = [];
  const hidden = new Set<number>();
  WRAP.lastIndex = 0;
  for (let match = WRAP.exec(text); match !== null; match = WRAP.exec(text)) {
    const [prefixStart, prefixEnd] = match.indices?.groups?.prefix ?? [0, 0];
    const [suffixStart, suffixEnd] = match.indices?.groups?.suffix ?? [0, 0];
    hidden.add(prefixStart).add(suffixStart);
    const lineStart = prefixStart === 0 ? 0 : text.lastIndexOf('\n', prefixStart - 1) + 1;
    const before = text.slice(lineStart, prefixStart);
    const words = pySplit(before).filter(hasLetter).length;
    const fullLine = prefixEnd - lineStart >= WRAP_MIN_LINE;
    if (fullLine && words >= WRAP_MIN_WORDS && !REFERENCE_BEFORE.test(before)) {
      joined.push([
        prefixStart,
        suffixEnd,
        `${match.groups?.prefix ?? ''} ${match.groups?.suffix ?? ''}`,
      ]);
    }
  }
  return { joined, hidden };
}

export function amountsOnPage(page: number, text: string): AmountToken[] {
  const declared = PAGE_CURRENCY.exec(text);
  const pageCurrency = declared?.[1] ? currencyCode(declared[1]) : null;
  const { joined, hidden } = wraps(text);
  const spans: [number, number, string][] = [];
  NUMBER.lastIndex = 0;
  for (let match = NUMBER.exec(text); match !== null; match = NUMBER.exec(text)) {
    if (!hidden.has(match.index))
      spans.push([match.index, match.index + match[0].length, match[0]]);
  }
  const all = [...spans, ...joined].sort(
    (a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0),
  );
  const tokens: AmountToken[] = [];
  for (const [start, end, number] of all) {
    if (/^0[0-9]/u.test(number)) continue; // identifiers such as KRS 0000990114
    const after = CURRENCY_AFTER.exec(text.slice(end, end + 12));
    const before = CURRENCY_BEFORE.exec(text.slice(Math.max(0, start - 6), start));
    let currency: string | null = null;
    if (after?.[1]) currency = currencyCode(after[1]);
    if (currency === null && before?.[1]) currency = currencyCode(before[1]);
    tokens.push({
      page,
      value: parseNumber(number),
      currency: currency ?? pageCurrency,
      text: number,
      start,
      end,
      adjacentCurrency: currency !== null,
    });
  }
  return tokens;
}

function isoDate(year: number, month: number, day: number): string | null {
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1) return null;
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  const pad = (n: number, width: number) => String(n).padStart(width, '0');
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

/** Every calendar-valid date occurrence as [iso, start, end], in source order. */
export function dateOccurrences(text: string): [string, number, number][] {
  const found: [string, number, number][] = [];
  for (const [pattern, order] of DATES) {
    pattern.lastIndex = 0;
    for (let match = pattern.exec(text); match !== null; match = pattern.exec(text)) {
      const parts = new Map<Part, string>(order.map((key, i) => [key, match[i + 1] ?? '']));
      const monthName = parts.get('M');
      const month =
        monthName !== undefined
          ? (MONTH_INDEX.get(monthName.toLowerCase()) ?? 0)
          : Number(parts.get('m'));
      const iso = isoDate(Number(parts.get('y')), month, Number(parts.get('d')));
      if (iso !== null) found.push([iso, match.index, match.index + match[0].length]);
    }
  }
  return found.sort((a, b) => a[1] - b[1]);
}
