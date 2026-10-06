/**
 * Compact selection: prompt with inline markers, strict validation of the model's selection and
 * assembly of the public result from source candidates — port of backend compact.py (and the
 * overview checks of merge.parse_overview). The model never supplies values or contexts.
 */
import { DOCUMENT_TYPES, LANGUAGES } from '../../frontend/src/lib/contract';
import { sentenceCountWithin } from '../../frontend/src/lib/sentences';
import type { Candidate } from './candidates';
import { CLOSE, OPEN } from './candidates';
import {
  AnalysisResultSchema,
  KEY_POINTS,
  SUMMARY_SENTENCES,
  type AnalysisResult,
  type AnalyzeRequest,
} from './contract';
import { InvalidModelOutput } from './errors';
import { DEFAULT_FALLBACK_TITLE, FALLBACK_TITLES, SYSTEM_PROMPT } from './prompt';
import { W, WS, casefold, collapse, escapeRegExp, pySplit, pyStrip } from './text';

const TAG = new RegExp(`<[${WS}]*/?[${WS}]*(document|page)(?![${W}])[^>]*>?`, 'giu');

export function neutralize(text: string): string {
  return text.replace(TAG, '[tag]');
}

/** Insert ⟦A n⟧ / ⟦D n⟧ before each candidate; source brackets cannot fake a marker. */
export function markDocument(request: AnalyzeRequest, candidates: Candidate[]): string {
  const byPage = new Map<number, Candidate[]>();
  for (const c of candidates) byPage.set(c.page, [...(byPage.get(c.page) ?? []), c]);
  const parts = ['<document>'];
  const missing = new Set(request.pagesWithoutText);
  for (const page of request.pages) {
    if (missing.has(page.page)) {
      parts.push(`<page number="${page.page}" status="no-extractable-text"></page>`);
      continue;
    }
    let text = page.text.replaceAll('⟦', '[').replaceAll('⟧', ']');
    const sorted = [...(byPage.get(page.page) ?? [])].sort((a, b) => b.start - a.start);
    for (const c of sorted) {
      text = `${text.slice(0, c.start)}⟦${c.kind === 'amount' ? 'A' : 'D'}${c.id}⟧${text.slice(c.start)}`;
    }
    const source = request.ocrPages.includes(page.page) ? ' source="ocr"' : '';
    parts.push(`<page number="${page.page}"${source}>\n${neutralize(text)}\n</page>`);
  }
  parts.push('</document>');
  return parts.join('\n');
}

export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export function buildMessages(request: AnalyzeRequest, candidates: Candidate[]): Message[] {
  const missing = request.pagesWithoutText;
  let coverage = missing.length
    ? `Pages without extractable text (not analysed): ${missing.join(', ')}.`
    : 'All pages have extractable text.';
  if (request.ocrPages.length) {
    coverage +=
      ` Text of pages ${request.ocrPages.join(', ')} (marked source="ocr") was ` +
      "recognised by OCR in the user's browser and may contain recognition errors.";
  }
  const user =
    `The document has ${request.pageCount} pages. ${coverage}\n` +
    'Analyse it according to the rules. Return only the JSON object.\n\n' +
    markDocument(request, candidates);
  return [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: user },
  ];
}

export function correctionMessage(problems: string[]): Message {
  return {
    role: 'user',
    content:
      `Your previous answer did not pass validation: ${problems.slice(0, 8).join('; ')}. ` +
      'Return a corrected JSON object that follows every rule and the schema.',
  };
}

// ------------------------------------------------------------------ strict model output

export interface CompactOutput {
  insufficientContent: boolean;
  language: string;
  type: string;
  title: string | null;
  mainDateId: number | null;
  summary: string;
  keyPoints: string[];
  organizations: string[];
  people: string[];
  keywords: string[];
  amountIds: number[];
  dateIds: number[];
}

type Check = (value: unknown, path: string, problems: string[]) => void;
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v);
const scalar =
  (test: (v: unknown) => boolean, what: string): Check =>
  (value, path, problems) => {
    if (!test(value)) problems.push(`${path}: ${what}`);
  };
const list =
  (test: (v: unknown) => boolean, what: string): Check =>
  (value, path, problems) => {
    if (!Array.isArray(value)) problems.push(`${path}: Input should be a valid list`);
  else value.forEach((item, i) => { if (!test(item)) problems.push(`${path}.${i}: ${what}`); }); // prettier-ignore
  };
const isString = (v: unknown) => typeof v === 'string';
const FIELDS: Record<keyof CompactOutput, Check> = {
  insufficientContent: scalar((v) => typeof v === 'boolean', 'Input should be a valid boolean'),
  language: scalar(isString, 'Input should be a valid string'),
  type: scalar(isString, 'Input should be a valid string'),
  title: scalar((v) => v === null || isString(v), 'Input should be a valid string'),
  mainDateId: scalar((v) => v === null || isInt(v), 'Input should be a valid integer'),
  summary: scalar(isString, 'Input should be a valid string'),
  keyPoints: list(isString, 'Input should be a valid string'),
  organizations: list(isString, 'Input should be a valid string'),
  people: list(isString, 'Input should be a valid string'),
  keywords: list(isString, 'Input should be a valid string'),
  amountIds: list(isInt, 'Input should be a valid integer'),
  dateIds: list(isInt, 'Input should be a valid integer'),
};

/** Pydantic strict model semantics: every key required, no coercion, extra keys ignored. */
export function validateOutput(payload: Record<string, unknown>): CompactOutput {
  const problems: string[] = [];
  for (const [field, check] of Object.entries(FIELDS)) {
    if (!(field in payload)) problems.push(`${field}: Field required`);
    else check(payload[field], field, problems);
  }
  if (problems.length) throw new InvalidModelOutput(problems);
  const output: Record<string, unknown> = {};
  for (const field of Object.keys(FIELDS)) output[field] = payload[field];
  return output as unknown as CompactOutput;
}

/** Trim, drop blanks and case-insensitive duplicates (analyzer._clean_list). */
export function cleanList(values: string[]): string[] {
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of values.map(pyStrip)) {
    if (item && !seen.has(casefold(item))) {
      seen.add(casefold(item));
      cleaned.push(item);
    }
  }
  return cleaned;
}

const COPIED_MARKER = new RegExp(`⟦[AD][0-9]+⟧(?=[${WS}]*[0-9])`, 'gu');
const TEXT_FIELDS = [
  'title',
  'summary',
  'keyPoints',
  'organizations',
  'people',
  'keywords',
] as const;

function withoutCopiedMarkers(output: CompactOutput): CompactOutput {
  const strip = (value: string) => value.replace(COPIED_MARKER, '');
  return {
    ...output,
    title: output.title === null ? null : strip(output.title),
    summary: strip(output.summary),
    keyPoints: output.keyPoints.map(strip),
    organizations: output.organizations.map(strip),
    people: output.people.map(strip),
    keywords: output.keywords.map(strip),
  };
}

function markerProblems(output: CompactOutput): string[] {
  const problems: string[] = [];
  for (const field of TEXT_FIELDS) {
    const value = output[field];
    const values = Array.isArray(value) ? value : [value];
    values.forEach((text, i) => {
      if (text && (text.includes('⟦') || text.includes('⟧'))) {
        problems.push(
          `${Array.isArray(value) ? `${field}.${i}` : field}: contains an internal marker; write plain text`,
        );
      }
    });
  }
  return problems;
}

/** merge.parse_overview: ISO language, type enum, 3-5 summary sentences, 3-7 distinct points. */
function checkOverview(output: CompactOutput): void {
  const problems: string[] = [];
  if (!LANGUAGES.has(pyStrip(output.language).toLowerCase()))
    problems.push('language: must be an ISO 639-1 code');
  if (!(DOCUMENT_TYPES as readonly string[]).includes(output.type))
    problems.push('type: Input should be one of the document types');
  if (problems.length) throw new InvalidModelOutput(problems);
  if (!sentenceCountWithin(pyStrip(output.summary), ...SUMMARY_SENTENCES)) {
    problems.push('summary: must contain 3-5 sentences ending with punctuation');
  }
  const points = cleanList(output.keyPoints);
  if (points.length < KEY_POINTS[0] || points.length > KEY_POINTS[1]) {
    problems.push(`keyPoints: need ${KEY_POINTS[0]}-${KEY_POINTS[1]} non-empty distinct items`);
  }
  if (problems.length) throw new InvalidModelOutput(problems);
}

function normalized(text: string): string {
  return collapse(casefold(text.normalize('NFC')));
}

const WORD_CHAR = /^[\p{L}\p{N}_]$/u;

/** True when `phrase` occurs in `text` with no word character directly before or after — the
 * same as the regex (?<![\p{L}\p{N}_])phrase(?![\p{L}\p{N}_]) for a literal phrase, without
 * compiling a Unicode regex per name (measured cold-start hotspot). */
export function containsWholePhrase(text: string, phrase: string): boolean {
  for (let at = text.indexOf(phrase); at !== -1; at = text.indexOf(phrase, at + 1)) {
    const before =
      at > 0
        ? String.fromCodePoint(
            text.codePointAt(at - 1 - (isLowSurrogate(text, at - 1) ? 1 : 0)) ?? 0,
          )
        : '';
    const after =
      at + phrase.length < text.length
        ? String.fromCodePoint(text.codePointAt(at + phrase.length) ?? 0)
        : '';
    if (!WORD_CHAR.test(before) && !WORD_CHAR.test(after)) return true;
  }
  return false;
}

function isLowSurrogate(text: string, index: number): boolean {
  const code = text.charCodeAt(index);
  return index > 0 && code >= 0xdc00 && code <= 0xdfff;
}

/** Names whose words do not appear consecutively as whole words in one page (no morphology). */
export function unattestedPeople(names: string[], request: AnalyzeRequest): string[] {
  if (!names.length) return [];
  const pages = request.pages.map((p) => normalized(p.text));
  return names.filter((name) => {
    const words = pySplit(normalized(name));
    if (!words.length) return false;
    const phrase = words.join(' ');
    return !pages.some((page) => containsWholePhrase(page, phrase));
  });
}

export interface Selection {
  output: CompactOutput;
  amounts: Candidate[];
  dates: Candidate[];
  mainDate: Candidate | null;
}

export function parseSelection(
  payload: Record<string, unknown>,
  byId: Map<number, Candidate>,
  request?: AnalyzeRequest,
): Selection {
  let output = validateOutput(payload);
  if (output.insufficientContent) return { output, amounts: [], dates: [], mainDate: null };
  output = withoutCopiedMarkers(output);
  const markers = markerProblems(output);
  if (markers.length) throw new InvalidModelOutput(markers);
  checkOverview(output);
  const problems: string[] = [];
  const resolve = (field: string, ids: number[], kind: Candidate['kind']): Candidate[] => {
    const chosen: Candidate[] = [];
    const seen = new Set<number>();
    ids.forEach((id, position) => {
      const candidate = byId.get(id);
      if (seen.has(id)) problems.push(`${field}.${position}: id ${id} repeated`);
      else if (!candidate) problems.push(`${field}.${position}: id ${id} is not a candidate`);
      else if (candidate.kind !== kind)
        problems.push(`${field}.${position}: id ${id} is not a ${kind} candidate`);
      else chosen.push(candidate);
      seen.add(id);
    });
    return chosen;
  };
  if (request) {
    const missing = new Set(unattestedPeople(output.people, request));
    output.people.forEach((name, position) => {
      if (missing.has(name)) {
        problems.push(
          `people.${position}: not written in the document; copy the name exactly as one occurrence spells it, or leave it out`,
        );
      }
    });
  }
  const amounts = resolve('amountIds', output.amountIds, 'amount');
  const dates = resolve('dateIds', output.dateIds, 'date');
  let mainDate: Candidate | null = null;
  if (output.mainDateId !== null)
    mainDate = resolve('mainDateId', [output.mainDateId], 'date')[0] ?? null;
  if (problems.length) throw new InvalidModelOutput(problems);
  return { output, amounts, dates, mainDate };
}

// ------------------------------------------------------------------ assembly

const LEGAL_FORM = `(?:sp\\.[${WS}]?z[${WS}]?o\\.[${WS}]?o\\.|sp\\.[${WS}]?k\\.|sp\\.[${WS}]?j\\.|sp\\.[${WS}]?p\\.|s\\.[${WS}]?k\\.[${WS}]?a\\.|s\\.[${WS}]?a\\.|spółka z ograniczoną odpowiedzialnością|spółka akcyjna|gmbh|ltd\\.?|inc\\.?|llc)`;
const HAS_LEGAL_FORM = new RegExp(`(?:^|[${WS}])${LEGAL_FORM}(?=[${WS}]|,|$)`, 'iu');
const CAPITALISED_BEFORE = new RegExp(`[A-ZĄĆĘŁŃÓŚŹŻ][${W}-]*[ \\t]+$`, 'u');

/** Short names resolve only to a unique "<name> <legal form>" written in the source. */
export function resolveOrganizations(names: string[], request: AnalyzeRequest): string[] {
  const resolved: string[] = [];
  for (const name of names) {
    let full = name;
    if (!HAS_LEGAL_FORM.test(name)) {
      const words = pySplit(name).map(escapeRegExp).join(`[${WS}]+`);
      const pattern = new RegExp(`(?<![${W}-])${words},?[${WS}]+(${LEGAL_FORM})(?![${W}])`, 'giu');
      const matches = new Set<string>();
      for (const page of request.pages) {
        pattern.lastIndex = 0;
        for (let m = pattern.exec(page.text); m !== null; m = pattern.exec(page.text)) {
          if (CAPITALISED_BEFORE.test(page.text.slice(0, m.index))) continue;
          matches.add(collapse(m[0]));
        }
      }
      if (matches.size === 1) full = [...matches][0] ?? name;
    }
    if (!resolved.some((r) => casefold(r) === casefold(full))) resolved.push(full);
  }
  return resolved;
}

function unique(candidates: Candidate[], key: (c: Candidate) => string): Candidate[] {
  const seen = new Set<string>();
  return [...candidates]
    .sort((a, b) => a.id - b.id)
    .filter((c) => (seen.has(key(c)) ? false : (seen.add(key(c)), true)));
}

export function fallbackTitle(language: string): string {
  return FALLBACK_TITLES[language] ?? DEFAULT_FALLBACK_TITLE;
}

export function assemble(request: AnalyzeRequest, selection: Selection): AnalysisResult {
  const { output } = selection;
  const amounts = unique(selection.amounts, (c) =>
    JSON.stringify([c.value, c.currency, c.context]),
  );
  const dates = unique(selection.dates, (c) =>
    JSON.stringify([c.date, c.context.replaceAll(OPEN, '').replaceAll(CLOSE, '')]),
  );
  const language = pyStrip(output.language).toLowerCase();
  const title = pyStrip(output.title ?? '');
  const candidate = {
    document: {
      fileName: pyStrip(request.fileName),
      pages: request.pageCount,
      language,
      type: output.type,
      title: title || fallbackTitle(language),
      date: selection.mainDate ? selection.mainDate.date : null,
    },
    summary: pyStrip(output.summary),
    keyPoints: cleanList(output.keyPoints),
    entities: {
      organizations: resolveOrganizations(cleanList(output.organizations), request),
      people: cleanList(output.people),
    },
    amounts: amounts.map((c) => ({ value: c.value, currency: c.currency, context: c.context })),
    dates: dates.map((c) => ({ date: c.date, context: c.context })),
    keywords: cleanList(output.keywords).slice(0, 20),
    analysis: {
      complete: request.pagesWithoutText.length === 0,
      pagesWithoutText: [...request.pagesWithoutText],
      titleFallback: !title,
      ...(request.ocrPages.length ? { ocrPages: [...request.ocrPages] } : {}),
    },
  };
  const parsed = AnalysisResultSchema.safeParse(candidate);
  if (!parsed.success) {
    throw new InvalidModelOutput(
      parsed.error.issues.map((i) => `${i.path.join('.') || 'root'}: ${i.message}`),
    );
  }
  return parsed.data;
}
