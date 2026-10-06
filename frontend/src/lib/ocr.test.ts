import { describe, expect, it, vi } from 'vitest';
import {
  OCR_LIMITS,
  OcrError,
  applyOcr,
  cleanOcrText,
  recognizePages,
  type OcrDeps,
  type OcrEngine,
} from './ocr';
import type { ExtractedDocument } from './pdf';
import { prepareRequest } from './request';

const body = 'Umowa ramowa została zawarta pomiędzy stronami w Warszawie. '.repeat(6);
const doc: ExtractedDocument = {
  fileName: 'umowa.pdf',
  fileBytes: 1000,
  pageCount: 3,
  pages: [
    { page: 1, text: body },
    { page: 2, text: '' },
    { page: 3, text: '  ' },
  ],
  pagesWithoutText: [2, 3],
};
const blob = new Blob(['%PDF-1.7']);
const canvas = {} as HTMLCanvasElement;

function fakeDeps(texts: Record<number, string>, overrides: Partial<OcrDeps> = {}) {
  const released: number[] = [];
  const engine = {
    recognize: vi.fn<OcrEngine['recognize']>(),
    terminate: vi.fn(() => Promise.resolve()),
  };
  let current = 0;
  engine.recognize.mockImplementation(() =>
    Promise.resolve({ text: texts[current] ?? '', confidence: 88.4 }),
  );
  const destroy = vi.fn();
  const deps: OcrDeps = {
    openPdf: () =>
      Promise.resolve({
        render: (page) => {
          current = page;
          return Promise.resolve({ canvas, release: () => released.push(page) });
        },
        destroy,
      }),
    createEngine: () => Promise.resolve(engine),
    ...overrides,
  };
  return { deps, engine, destroy, released };
}

describe('recognizePages', () => {
  it('recognises the selected pages in order and releases everything', async () => {
    const { deps, engine, destroy, released } = fakeDeps({ 2: 'Aneks nr 1   \n\n\n\nKwota 5 000,00 zł', 3: ' | ~ ' });
    const progress: [number, number, number][] = [];
    const results = await recognizePages(blob, [2, 3], new AbortController().signal, (...p) => progress.push(p), deps);
    expect(results).toEqual([
      { page: 2, text: 'Aneks nr 1\n\nKwota 5 000,00 zł', confidence: 88, status: 'recognized' },
      { page: 3, text: '| ~', confidence: 88, status: 'unreadable' },
    ]);
    expect(progress.at(-1)).toEqual([2, 2, 3]);
    expect(released).toEqual([2, 3]);
    expect(destroy).toHaveBeenCalled();
    expect(engine.terminate).toHaveBeenCalled();
  }); // prettier-ignore

  it('rejects too many pages before loading anything', async () => {
    const openPdf = vi.fn<OcrDeps['openPdf']>();
    const pages = Array.from({ length: OCR_LIMITS.maxPages + 1 }, (_, i) => i + 1);
    await expect(
      recognizePages(blob, pages, new AbortController().signal, () => undefined, {
        ...fakeDeps({}).deps,
        openPdf,
      }),
    ).rejects.toEqual(new OcrError('too-many-pages'));
    expect(openPdf).not.toHaveBeenCalled();
  });

  it('reports a load failure of the OCR engine and closes the PDF', async () => {
    const { deps, destroy } = fakeDeps(
      {},
      { createEngine: () => Promise.reject(new Error('404')) },
    );
    await expect(
      recognizePages(blob, [2], new AbortController().signal, () => undefined, deps),
    ).rejects.toMatchObject({ reason: 'load-failed' });
    expect(destroy).toHaveBeenCalled();
  });

  it('a recognition error fails the run (no partial result is returned)', async () => {
    const { deps, engine } = fakeDeps({});
    engine.recognize.mockRejectedValueOnce(new Error('wasm'));
    await expect(
      recognizePages(blob, [2], new AbortController().signal, () => undefined, deps),
    ).rejects.toMatchObject({ reason: 'failed' });
    expect(engine.terminate).toHaveBeenCalled();
  });

  it('abort terminates the worker at once and the run ends as cancelled', async () => {
    const { deps, engine } = fakeDeps({});
    engine.recognize.mockImplementation(() => new Promise(() => undefined));
    const controller = new AbortController();
    const run = recognizePages(blob, [2, 3], controller.signal, () => undefined, deps);
    await vi.waitFor(() => {
      expect(engine.recognize).toHaveBeenCalled();
    });
    controller.abort();
    expect(engine.terminate).toHaveBeenCalled();
    await expect(run).rejects.toMatchObject({ reason: 'cancelled' });
  });

  it('a page that takes too long ends the run with a timeout', async () => {
    vi.useFakeTimers();
    try {
      const { deps, engine } = fakeDeps({});
      engine.recognize.mockImplementation(() => new Promise(() => undefined));
      const run = recognizePages(blob, [2], new AbortController().signal, () => undefined, deps);
      const assertion = expect(run).rejects.toMatchObject({ reason: 'timeout' });
      await vi.advanceTimersByTimeAsync(OCR_LIMITS.pageTimeoutMs + 1);
      await assertion;
      expect(engine.terminate).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('applyOcr', () => {
  it('fills only scanned pages, keeps page numbers and flags unrecovered pages', () => {
    const merged = applyOcr(doc, [
      { page: 2, text: 'Aneks nr 1. Kwota 5 000,00 zł.', confidence: 90, status: 'recognized' },
      { page: 3, text: '|', confidence: 10, status: 'unreadable' },
      { page: 1, text: 'NADPISANIE', confidence: 99, status: 'recognized' },
    ]);
    expect(merged.pages.map((p) => p.page)).toEqual([1, 2, 3]);
    expect(merged.pages[0]?.text).toBe(body);
    expect(merged.pages[1]?.text).toBe('Aneks nr 1. Kwota 5 000,00 zł.');
    expect(merged.pagesWithoutText).toEqual([3]);
    expect(merged.ocrPages).toEqual([2]);
    expect(doc.pagesWithoutText).toEqual([2, 3]); // the original document is not modified
  });

  it('the request marks OCR pages; the text-only payload is unchanged', () => {
    expect(Object.keys(prepareRequest(doc).request)).toEqual([
      'fileName',
      'pageCount',
      'pages',
      'pagesWithoutText',
    ]);
    const merged = applyOcr(doc, [
      { page: 2, text: 'Aneks nr 1.', confidence: 90, status: 'recognized' },
    ]);
    expect(prepareRequest(merged).request.ocrPages).toEqual([2]);
    expect(prepareRequest(applyOcr(doc, [])).request).not.toHaveProperty('ocrPages');
  });

  it('existing character limits apply after OCR (no truncation)', () => {
    const long = 'Ą'.repeat(20_001);
    const merged = applyOcr(doc, [{ page: 2, text: long, confidence: 90, status: 'recognized' }]);
    const readiness = prepareRequest(merged);
    expect(readiness.problem).toBe('page-too-long');
    expect(readiness.request.pages[1]?.text).toBe(long);
  });

  it('normalises only whitespace', () => {
    expect(cleanOcrText('  a  \n\n\n\nb \n')).toBe('a\n\nb');
  });
});
