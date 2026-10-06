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
  /** Machine-recognised text (kept unchanged; user corrections live in the review state). */
  text: string;
  /** Tesseract mean word confidence 0–100 for the machine text (an indicator only). */
  confidence: number;
  status: OcrPageStatus;
  /** The rendered page image for side-by-side comparison; browser memory only, never sent. */
  preview: Blob | null;
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

export interface RenderedPage {
  canvas: HTMLCanvasElement;
  release: () => void;
}

export interface RenderedPdf {
  render(page: number): Promise<RenderedPage>;
  destroy(): void;
}

export interface OcrDeps {
  /** `signal` aborts loading itself (the pdf.js task is destroyed before it resolves). */
  openPdf: (source: Blob, signal: AbortSignal) => Promise<RenderedPdf>;
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

async function openPdfWithPdfJs(source: Blob, signal: AbortSignal): Promise<RenderedPdf> {
  const pdfjs = await loadPdfJs();
  const data = new Uint8Array(await source.arrayBuffer());
  if (signal.aborted) throw new OcrError('cancelled');
  const task = pdfjs.getDocument({ data });
  const destroy = () => void task.destroy();
  signal.addEventListener('abort', destroy, { once: true });
  const doc = await task.promise.finally(() => {
    signal.removeEventListener('abort', destroy);
  });
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
    destroy,
  };
}

/** JPEG snapshot of a rendered page for the review step (null where canvases cannot encode). */
function snapshot(canvas: HTMLCanvasElement): Promise<Blob | null> {
  if (typeof canvas.toBlob !== 'function') return Promise.resolve(null);
  return new Promise((resolve) => {
    canvas.toBlob(resolve, 'image/jpeg', 0.85);
  });
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
 * Recognises the given pages sequentially. Abort (or a timeout) rejects the run immediately,
 * terminates a started OCR worker, destroys the pdf.js document or its loading task, and releases
 * a page render that completes late. Limit: Tesseract.js cannot cancel a worker that is still
 * starting — it is terminated as soon as its start settles (if it never settles, it lives until
 * the page is closed).
 */
export async function recognizePages(
  source: Blob,
  pages: readonly number[],
  signal: AbortSignal,
  onProgress: (done: number, total: number, page: number) => void,
  deps: OcrDeps = defaultDeps,
): Promise<OcrPageResult[]> {
  if (pages.length > OCR_LIMITS.maxPages) throw new OcrError('too-many-pages');
  // Stops loading on cancel and on any failure or timeout of this run.
  const stop = new AbortController();
  let pdf: RenderedPdf | null = null;
  let engine: OcrEngine | null = null;
  const active = (): { pdf: RenderedPdf | null; engine: OcrEngine | null } => ({ pdf, engine });
  const release = () => {
    stop.abort();
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
      // A PDF or engine that finishes loading after an abort or a timeout is released then.
      const opening = deps.openPdf(source, stop.signal);
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
      const rendering = current.pdf.render(number);
      const image = await bounded(rendering, OCR_LIMITS.pageTimeoutMs, signal).catch(
        (error: unknown) => {
          // A render finishing after a timeout or cancel still releases its canvas and page.
          void rendering.then(
            (late) => {
              late.release();
            },
            () => undefined,
          );
          check();
          throw error instanceof OcrError ? error : new OcrError('failed');
        },
      );
      try {
        check();
        const { text, confidence } = await bounded(
          current.engine.recognize(image.canvas),
          OCR_LIMITS.pageTimeoutMs,
          signal,
        );
        check();
        const cleaned = cleanOcrText(text);
        const preview = await snapshot(image.canvas).catch(() => null);
        check();
        results.push({
          page: number,
          text: cleaned,
          confidence: Math.round(confidence),
          status: hasLetter(cleaned) ? 'recognized' : 'unreadable',
          preview,
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

/** User corrections of OCR text, by page (absent: the machine text is used as recognised). */
export type OcrEdits = Readonly<Record<number, string>>;

/**
 * The document with accepted OCR text (machine or user-corrected) on pages that had no text.
 * Text-layer pages are never touched; pages that still have no letters stay flagged. OCR
 * provenance accumulates: pages accepted in an earlier pass stay marked.
 */
export function applyOcr(
  doc: ExtractedDocument,
  results: readonly OcrPageResult[],
  edits: OcrEdits = {},
): ExtractedDocument {
  const missing = new Set(doc.pagesWithoutText);
  const accepted = new Map<number, string>();
  for (const result of results) {
    const text = edits[result.page] ?? result.text;
    if (missing.has(result.page) && hasLetter(text)) accepted.set(result.page, text);
  }
  const pages = doc.pages.map((page) => {
    const text = accepted.get(page.page);
    return text === undefined ? page : { page: page.page, text };
  });
  const withText = new Set(pages.filter((p) => hasLetter(p.text)).map((p) => p.page));
  const ocrPages = [...new Set([...(doc.ocrPages ?? []), ...accepted.keys()])]
    .filter((page) => withText.has(page))
    .sort((a, b) => a - b);
  return {
    ...doc,
    pages,
    pagesWithoutText: pages.filter((p) => !withText.has(p.page)).map((p) => p.page),
    ocrPages,
  };
}
