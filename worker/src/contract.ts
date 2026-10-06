/**
 * Request contract (backend contract.py AnalyzeRequest) and the shared result schema. The result
 * schema is the frontend's Zod mirror of the Python AnalysisResult (one source, shared fixtures).
 */
import { z } from 'zod';
import limits from '../../contracts/limits.json';
import { AnalysisResultSchema } from '../../frontend/src/lib/schema';
import { codePointLength, countLetters, hasLetter, pyStrip } from './text';

export { AnalysisResultSchema };
export type AnalysisResult = z.infer<typeof AnalysisResultSchema>;

export const MAX_PAGES = limits.maxPages;
export const MAX_PAGE_CHARS = limits.maxPageChars;
export const COMPACT_MAX_CHARS = limits.compactMaxChars;
export const MIN_TOTAL_LETTERS = limits.minTotalLetters;
export const MAX_CANDIDATES = limits.maxCandidates;
export const KEY_POINTS = limits.keyPoints as [number, number];
export const SUMMARY_SENTENCES = limits.summarySentences as [number, number];

const FORBIDDEN_FILENAME = /[\x00-\x1f\x7f/\\]/u;
const codePoints = (max: number) => (value: string) => codePointLength(value) <= max;

const PageTextSchema = z.strictObject({
  page: z.int().min(1),
  text: z.string().refine(codePoints(MAX_PAGE_CHARS), 'too long'),
});

export const AnalyzeRequestSchema = z
  .strictObject({
    fileName: z
      .string()
      .min(1)
      .refine(codePoints(255), 'too long')
      .refine((value) => pyStrip(value) !== '', 'must not be blank')
      .refine((value) => !FORBIDDEN_FILENAME.test(value), 'must not contain control characters'),
    pageCount: z.int().min(1).max(MAX_PAGES),
    pages: z.array(PageTextSchema).max(MAX_PAGES),
    pagesWithoutText: z.array(z.int()).max(MAX_PAGES),
  })
  .superRefine((request, ctx) => {
    if (request.pages.length !== request.pageCount) {
      ctx.addIssue({ code: 'custom', message: 'pages must contain exactly pageCount items' });
      return;
    }
    if (request.pages.some((page, index) => page.page !== index + 1)) {
      ctx.addIssue({ code: 'custom', message: 'page numbers must be 1..pageCount in order' });
      return;
    }
    const expected = request.pages.filter((page) => !hasLetter(page.text)).map((p) => p.page);
    const given = request.pagesWithoutText;
    if (expected.length !== given.length || expected.some((page, i) => page !== given[i])) {
      ctx.addIssue({ code: 'custom', message: 'pagesWithoutText does not match page texts' });
    }
  });

export type AnalyzeRequest = z.infer<typeof AnalyzeRequestSchema>;

export function totalChars(request: AnalyzeRequest): number {
  return request.pages.reduce((sum, page) => sum + codePointLength(page.text), 0);
}

export function totalLetters(request: AnalyzeRequest): number {
  return request.pages.reduce((sum, page) => sum + countLetters(page.text), 0);
}
