import { LIMITS, countLetters } from './contract';
import type { ExtractedDocument } from './pdf';
import type { AnalyzeRequest } from './schema';

export type ReadinessProblem =
  'no-text-layer' | 'insufficient-content' | 'page-too-long' | 'document-too-long';

export interface Readiness {
  request: AnalyzeRequest;
  problem: ReadinessProblem | null;
  totalChars: number;
  bodyBytes: number;
}

/**
 * Builds the API payload and applies the same limits as the server before sending.
 * Text is never truncated: an oversized document is reported instead.
 */
export function prepareRequest(doc: ExtractedDocument): Readiness {
  const request: AnalyzeRequest = {
    fileName: doc.fileName,
    pageCount: doc.pageCount,
    pages: doc.pages,
    pagesWithoutText: doc.pagesWithoutText,
    // Only when the user accepted OCR text: the text-only payload stays exactly as before.
    ...(doc.ocrPages?.length ? { ocrPages: doc.ocrPages } : {}),
  };
  const totalChars = doc.pages.reduce((sum, page) => sum + page.text.length, 0);
  const bodyBytes = new TextEncoder().encode(JSON.stringify(request)).length;
  let problem: ReadinessProblem | null = null;
  if (doc.pagesWithoutText.length === doc.pageCount) problem = 'no-text-layer';
  else if (doc.pages.some((page) => page.text.length > LIMITS.maxPageChars))
    problem = 'page-too-long';
  else if (totalChars > LIMITS.maxTotalChars || bodyBytes > LIMITS.maxBodyBytes)
    problem = 'document-too-long';
  else if (doc.pages.reduce((sum, p) => sum + countLetters(p.text), 0) < LIMITS.minTotalLetters)
    problem = 'insufficient-content';
  return { request, problem, totalChars, bodyBytes };
}
