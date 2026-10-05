import { z } from 'zod';
import { CURRENCIES, DOCUMENT_TYPES, LANGUAGES, LIMITS } from './contract';
import { sentenceCountWithin } from './sentences';

/** Zod mirror of backend/src/pdf_insight/contract.py. Unknown keys are rejected at every level. */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u;

function isCalendarDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number) as [number, number, number];
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

const text = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .refine((value) => value.trim().length > 0, 'must not be blank');

const fact = text(500);
const isoDate = z.string().refine(isCalendarDate, 'must be a calendar date YYYY-MM-DD');

export const DocumentInfoSchema = z.strictObject({
  fileName: text(255),
  pages: z.number().int().positive(),
  language: z.string().refine((v) => LANGUAGES.has(v), 'must be an ISO 639-1 code'),
  type: z.enum(DOCUMENT_TYPES),
  title: text(300),
  date: isoDate.nullable(),
});

export const AmountSchema = z.strictObject({
  value: z.number(), // Zod 4 rejects NaN and ±Infinity
  currency: z.string().refine((v) => CURRENCIES.has(v), 'must be an ISO 4217 code'),
  context: fact,
});

export const DateFactSchema = z.strictObject({ date: isoDate, context: fact });

export const AnalysisInfoSchema = z.strictObject({
  complete: z.boolean(),
  pagesWithoutText: z.array(z.number().int()),
  titleFallback: z.boolean(),
});

export const AnalysisResultSchema = z
  .strictObject({
    document: DocumentInfoSchema,
    summary: text(2000).refine(
      (v) => sentenceCountWithin(v, ...LIMITS.summarySentences),
      'must contain 3-5 sentences ending with punctuation',
    ),
    keyPoints: z.array(fact).min(LIMITS.keyPoints[0]).max(LIMITS.keyPoints[1]),
    entities: z.strictObject({ organizations: z.array(fact), people: z.array(fact) }),
    amounts: z.array(AmountSchema),
    dates: z.array(DateFactSchema),
    keywords: z.array(fact).max(LIMITS.maxKeywords),
    analysis: AnalysisInfoSchema.optional(),
  })
  .superRefine((result, ctx) => {
    const info = result.analysis;
    if (!info) return;
    const pages = info.pagesWithoutText;
    const sortedUnique = pages.every((page, i) => i === 0 || page > (pages[i - 1] ?? 0));
    if (!sortedUnique || pages.some((p) => p < 1 || p > result.document.pages)) {
      ctx.addIssue({
        code: 'custom',
        path: ['analysis', 'pagesWithoutText'],
        message: 'must be ascending, unique and within 1..pages',
      });
    }
    if (info.complete !== (pages.length === 0)) {
      ctx.addIssue({
        code: 'custom',
        path: ['analysis', 'complete'],
        message: 'must be true iff no pages lack text',
      });
    }
  });

export type AnalysisResult = z.infer<typeof AnalysisResultSchema>;
export type DocumentType = (typeof DOCUMENT_TYPES)[number];

export const ApiErrorSchema = z.object({
  error: z.object({ code: z.string(), message: z.string(), retryable: z.boolean() }),
});

export interface PageText {
  page: number;
  text: string;
}

export interface AnalyzeRequest {
  fileName: string;
  pageCount: number;
  pages: PageText[];
  pagesWithoutText: number[];
}
