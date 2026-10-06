import { hasLetter } from './contract';
import { loadPdfJs, type ExtractedDocument } from './pdf';

/**
 * Optional browser OCR (F-10) for pages without a text layer. pdf.js renders only the selected
 * pages to a canvas; Tesseract.js (one Web Worker, Polish + English, LSTM) recognises them one at a
 * time. Page images never leave this browser and no model is called. Worker, WASM cores and
 * language data are served from this site (public/ocr/, copied from pinned packages).
 */
export const OCR_LIMITS = {
  /** Scanned pages recognised in one run. */
  maxPages: 20,
  /** Render scale for a typical page (≈ 144 dpi), lowered when a page would exceed maxPixels. */
  scale: 2,
  maxPixels: 4_000_000,
  /** Per page, including the first page's engine start. The whole run stops when exceeded. */
  pageTimeoutMs: 90_000,
} as const;

export const OCR_LANGUAGES = ['pol', 'eng'] as const;

export type OcrPageStatus = 'recognized' | 'unreadable';

export interface OcrPageResult {
  page: number;
  text: string;
  /** Tesseract mean word confidence 0–100 (an indicator only, not accuracy). */
  confidence: number;
  status: OcrPageStatus;
}

export class OcrError extends Error {
  constructor(
    readonly reason: 'cancelled' | 'too-many-pages' | 'load-failed' | 'timeout' | 'failed',
  ) {
    super(reason);
    this.name = 'OcrError';
  }
}

export interface OcrEngine {
  recognize(image: HTMLCanvasElement): Promise<{ text: string; confidence: number }>;
  terminate(): Promise<unknown>;
}

export interface RenderedPdf {
  render(page: number): Promise<{ canvas: HTMLCanvasElement; release: () => void }>;
  destroy(): void;
}

export interface OcrDeps {
  openPdf: (source: Blob) => Promise<RenderedPdf>;
  createEngine: () => Promise<OcrEngine>;
}

function assetUrl(path: string): string {
  return new URL(`${import.meta.env.BASE_URL}ocr/${path}`, window.location.href).href;
}

async function createTesseractEngine(): Promise<OcrEngine> {
  const { createWorker, OEM } = await import('tesseract.js');
  const worker = await createWorker([...OCR_LANGUAGES], OEM.LSTM_ONLY, {
    workerPath: assetUrl('worker.min.js'),
    corePath: assetUrl('core'),
    langPath: assetUrl('lang'),
    workerBlobURL: false,
    gzip: true,
    // Language data comes from this site; nothing is stored in IndexedDB.
    cacheMethod: 'none',
  });
  return {
    async recognize(image) {
      const { data } = await worker.recognize(image);
      return { text: data.text, confidence: data.confidence };
    },
    terminate: () => worker.terminate(),
  };
}

async function openPdfWithPdfJs(source: Blob): Promise<RenderedPdf> {
  const pdfjs = await loadPdfJs();
  const task = pdfjs.getDocument({ data: new Uint8Array(await source.arrayBuffer()) });
  const doc = await task.promise;
  return {
    async render(number) {
      const page = await doc.getPage(number);
      const base = page.getViewport({ scale: 1 });
      const fit = Math.sqrt(OCR_LIMITS.maxPixels / (base.width * base.height));
      const viewport = page.getViewport({ scale: Math.min(OCR_LIMITS.scale, fit) });
      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      await page.render({ canvas, viewport }).promise;
      return {
        canvas,
        release: () => {
          canvas.width = 0;
          canvas.height = 0;
          page.cleanup();
        },
      };
    },
    destroy: () => void task.destroy(),
  };
}

const defaultDeps: OcrDeps = { openPdf: openPdfWithPdfJs, createEngine: createTesseractEngine };

/** Tesseract output with trailing spaces and blank-line runs normalised; the text is not edited. */
export function cleanOcrText(text: string): string {
  return text
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
    .replace(/\n{3,}/gu, '\n\n')
    .trim();
}

/** Settles with the step, a timeout or the user's abort — whichever comes first. */
function bounded<T>(promise: Promise<T>, ms: number, signal: AbortSignal): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let onAbort: () => void = () => undefined;
  const stop = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new OcrError('timeout'));
    }, ms);
    onAbort = () => {
      reject(new OcrError('cancelled'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
  return Promise.race([promise, stop]).finally(() => {
    clearTimeout(timer);
    signal.removeEventListener('abort', onAbort);
  });
}

/**
 * Recognises the given pages sequentially. Aborting terminates the OCR worker and the pdf.js task
 * at once; both are always released when the run ends.
 */
export async function recognizePages(
  source: Blob,
  pages: readonly number[],
  signal: AbortSignal,
  onProgress: (done: number, total: number, page: number) => void,
  deps: OcrDeps = defaultDeps,
): Promise<OcrPageResult[]> {
  if (pages.length > OCR_LIMITS.maxPages) throw new OcrError('too-many-pages');
  let pdf: RenderedPdf | null = null;
  let engine: OcrEngine | null = null;
  const active = (): { pdf: RenderedPdf | null; engine: OcrEngine | null } => ({ pdf, engine });
  const release = () => {
    pdf?.destroy();
    pdf = null;
    const running = engine;
    engine = null;
    void running?.terminate().catch(() => undefined);
  };
  signal.addEventListener('abort', release, { once: true });
  const check = () => {
    if (signal.aborted) throw new OcrError('cancelled');
  };
  try {
    check();
    onProgress(0, pages.length, pages[0] ?? 0);
    try {
      // A PDF or engine that finishes loading after an abort or a timeout is released at once.
      const opening = deps.openPdf(source);
      pdf = await bounded(opening, OCR_LIMITS.pageTimeoutMs, signal).catch((error: unknown) => {
        void opening.then(
          (late) => {
            late.destroy();
          },
          () => undefined,
        );
        throw error;
      });
      check();
      const starting = deps.createEngine();
      engine = await bounded(starting, OCR_LIMITS.pageTimeoutMs, signal).catch((error: unknown) => {
        void starting.then(
          (late) => late.terminate().catch(() => undefined),
          () => undefined,
        );
        throw error;
      });
      check();
    } catch (error) {
      check();
      throw error instanceof OcrError ? error : new OcrError('load-failed');
    }
    const results: OcrPageResult[] = [];
    for (const [index, number] of pages.entries()) {
      check();
      onProgress(index, pages.length, number);
      const current = active();
      if (!current.pdf || !current.engine) throw new OcrError('cancelled');
      const image = await bounded(
        current.pdf.render(number),
        OCR_LIMITS.pageTimeoutMs,
        signal,
      ).catch((error: unknown) => {
        check();
        throw error instanceof OcrError ? error : new OcrError('failed');
      });
      try {
        check();
        const { text, confidence } = await bounded(
          current.engine.recognize(image.canvas),
          OCR_LIMITS.pageTimeoutMs,
          signal,
        );
        check();
        const cleaned = cleanOcrText(text);
        results.push({
          page: number,
          text: cleaned,
          confidence: Math.round(confidence),
          status: hasLetter(cleaned) ? 'recognized' : 'unreadable',
        });
      } catch (error) {
        check();
        throw error instanceof OcrError ? error : new OcrError('failed');
      } finally {
        image.release();
      }
    }
    onProgress(pages.length, pages.length, pages.at(-1) ?? 0);
    return results;
  } finally {
    signal.removeEventListener('abort', release);
    release();
  }
}

/**
 * The document with accepted OCR text on its originally scanned pages. Text-layer pages are never
 * touched; pages whose OCR text has no letters stay without text and stay flagged.
 */
export function applyOcr(
  doc: ExtractedDocument,
  results: readonly OcrPageResult[],
): ExtractedDocument {
  const missing = new Set(doc.pagesWithoutText);
  const recognized = new Map(
    results
      .filter((r) => r.status === 'recognized' && missing.has(r.page) && hasLetter(r.text))
      .map((r) => [r.page, r.text]),
  );
  const pages = doc.pages.map((page) => {
    const text = recognized.get(page.page);
    return text === undefined ? page : { page: page.page, text };
  });
  return {
    ...doc,
    pages,
    pagesWithoutText: pages.filter((p) => !hasLetter(p.text)).map((p) => p.page),
    ocrPages: [...recognized.keys()].sort((a, b) => a - b),
  };
}
