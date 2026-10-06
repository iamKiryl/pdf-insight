import type { TextItem } from 'pdfjs-dist/types/src/display/api';
import { LIMITS, hasLetter } from './contract';
import type { PageText } from './schema';
import { itemsToText } from './textLayout';

export interface ExtractedDocument {
  fileName: string;
  fileBytes: number;
  pageCount: number;
  pages: PageText[];
  pagesWithoutText: number[];
  /** Pages whose text the user accepted from browser OCR (absent: no OCR text in the document). */
  ocrPages?: number[];
  /** The chosen file, kept in browser memory only so OCR can render its scanned pages. */
  source?: Blob;
}

export type FileProblem = 'not-pdf' | 'too-large' | 'empty';

export class PdfExtractionError extends Error {
  constructor(
    readonly reason: 'not-pdf' | 'password' | 'corrupt' | 'too-many-pages' | 'cancelled',
  ) {
    super(reason);
    this.name = 'PdfExtractionError';
  }
}

/** Cheap checks before reading the file: type/extension and the 10 MB limit. */
export function checkFile(file: File): FileProblem | null {
  if (file.size === 0) return 'empty';
  const looksLikePdf = file.type === 'application/pdf' || /\.pdf$/iu.test(file.name);
  if (!looksLikePdf) return 'not-pdf';
  if (file.size > LIMITS.maxFileBytes) return 'too-large';
  return null;
}

/** Content check: a PDF starts with "%PDF-" (allowing a little leading garbage, as readers do). */
export function hasPdfSignature(bytes: Uint8Array): boolean {
  const head = new TextDecoder('latin1').decode(bytes.subarray(0, 1024));
  return head.includes('%PDF-');
}

type PdfJs = typeof import('pdfjs-dist');
let pdfjsPromise: Promise<PdfJs> | undefined;

/** pdf.js is loaded lazily; the worker URL is emitted by Vite with the correct /<repo>/ base. */
export async function loadPdfJs(): Promise<PdfJs> {
  pdfjsPromise ??= Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]).then(([pdfjs, worker]) => {
    pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
    return pdfjs;
  });
  return pdfjsPromise;
}

function isTextItem(item: unknown): item is TextItem {
  return typeof item === 'object' && item !== null && 'str' in item && 'transform' in item;
}

function errorName(error: unknown): string {
  return error instanceof Error ? error.name : '';
}

export async function extractPdf(
  file: File,
  signal: AbortSignal,
  onProgress: (page: number, total: number) => void,
): Promise<ExtractedDocument> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!hasPdfSignature(bytes)) throw new PdfExtractionError('not-pdf');
  const pdfjs = await loadPdfJs();
  const task = pdfjs.getDocument({ data: bytes });
  const abort = () => void task.destroy();
  signal.addEventListener('abort', abort, { once: true });
  try {
    const doc = await task.promise.catch((error: unknown) => {
      if (signal.aborted) throw new PdfExtractionError('cancelled');
      throw new PdfExtractionError(
        errorName(error) === 'PasswordException' ? 'password' : 'corrupt',
      );
    });
    if (doc.numPages > LIMITS.maxPages) throw new PdfExtractionError('too-many-pages');
    const pages: PageText[] = [];
    for (let number = 1; number <= doc.numPages; number += 1) {
      if (signal.aborted) throw new PdfExtractionError('cancelled');
      onProgress(number, doc.numPages);
      const page = await doc.getPage(number);
      const content = await page.getTextContent();
      const items = content.items.filter(isTextItem).map((item) => ({
        str: item.str,
        x: Number(item.transform[4]),
        y: Number(item.transform[5]),
        width: item.width,
        height: item.height || Math.abs(Number(item.transform[3])),
        hasEOL: item.hasEOL,
      }));
      pages.push({ page: number, text: itemsToText(items) });
      page.cleanup();
    }
    return {
      fileName: file.name,
      fileBytes: file.size,
      source: file,
      pageCount: doc.numPages,
      pages,
      pagesWithoutText: pages.filter((p) => !hasLetter(p.text)).map((p) => p.page),
    };
  } catch (error) {
    if (error instanceof PdfExtractionError) throw error;
    if (signal.aborted) throw new PdfExtractionError('cancelled');
    throw new PdfExtractionError('corrupt');
  } finally {
    signal.removeEventListener('abort', abort);
    void task.destroy();
  }
}
