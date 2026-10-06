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
      { page: 2, text: 'Aneks nr 1\n\nKwota 5 000,00 zł', confidence: 88, status: 'recognized', preview: null },
      { page: 3, text: '| ~', confidence: 88, status: 'unreadable', preview: null },
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
      {
        page: 2,
        text: 'Aneks nr 1. Kwota 5 000,00 zł.',
        confidence: 90,
        status: 'recognized',
        preview: null,
      },
      { page: 3, text: '|', confidence: 10, status: 'unreadable', preview: null },
      { page: 1, text: 'NADPISANIE', confidence: 99, status: 'recognized', preview: null },
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
      { page: 2, text: 'Aneks nr 1.', confidence: 90, status: 'recognized', preview: null },
    ]);
    expect(prepareRequest(merged).request.ocrPages).toEqual([2]);
    expect(prepareRequest(applyOcr(doc, [])).request).not.toHaveProperty('ocrPages');
  });

  it('existing character limits apply after OCR (no truncation)', () => {
    const long = 'Ą'.repeat(20_001);
    const merged = applyOcr(doc, [
      { page: 2, text: long, confidence: 90, status: 'recognized', preview: null },
    ]);
    const readiness = prepareRequest(merged);
    expect(readiness.problem).toBe('page-too-long');
    expect(readiness.request.pages[1]?.text).toBe(long);
  });

  it('normalises only whitespace', () => {
    expect(cleanOcrText('  a  \n\n\n\nb \n')).toBe('a\n\nb');
  });
});

describe('review fixes (REVIEW_OCR_FIXES)', () => {
  const ok = (page: number, text: string) =>
    ({ page, text, confidence: 90, status: 'recognized', preview: null }) as const;

  it('a second OCR pass keeps earlier provenance (union, sorted, only pages with text)', () => {
    const first = applyOcr(doc, [ok(2, 'Aneks nr 1.'), { ...ok(3, '|'), status: 'unreadable' }]);
    expect(first.ocrPages).toEqual([2]);
    expect(first.pagesWithoutText).toEqual([3]);
    const second = applyOcr(first, [ok(3, 'Załącznik nr 2.'), ok(1, 'NADPISANIE')]);
    expect(second.ocrPages).toEqual([2, 3]);
    expect(second.pages[0]?.text).toBe(body); // a text-layer page never becomes OCR text
    expect(second.pages[1]?.text).toBe('Aneks nr 1.');
    expect(prepareRequest(second).request.ocrPages).toEqual([2, 3]);
    const empty = applyOcr(first, [{ ...ok(3, ''), status: 'unreadable' }]);
    expect(empty.ocrPages).toEqual([2]); // an empty/failed pass never erases provenance
  });

  it('user corrections replace machine text, keep provenance and recompute missing pages', () => {
    const machine = [ok(2, 'zmienić $ 5 ust. 2 Umowy'), { ...ok(3, ''), status: 'unreadable' as const }];
    const edited = applyOcr(doc, machine, { 2: 'zmienić § 5 ust. 2 Umowy', 3: 'Wpisane ręcznie.' });
    expect(edited.pages[1]?.text).toBe('zmienić § 5 ust. 2 Umowy');
    expect(edited.pages[2]?.text).toBe('Wpisane ręcznie.');
    expect(edited.ocrPages).toEqual([2, 3]);
    expect(edited.pagesWithoutText).toEqual([]);
    expect(machine[0]?.text).toBe('zmienić $ 5 ust. 2 Umowy'); // machine text kept for reset
    const cleared = applyOcr(doc, machine, { 2: '   ' });
    expect(cleared.pagesWithoutText).toEqual([2, 3]);
    expect(cleared.ocrPages).toEqual([]);
  }); // prettier-ignore

  it('nothing is replaced automatically: an unedited genuine "$ 5" stays as recognised', () => {
    const merged = applyOcr(doc, [ok(2, 'Opłata wynosi $ 5 netto.')]);
    expect(merged.pages[1]?.text).toBe('Opłata wynosi $ 5 netto.');
  });

  it('a page render that finishes after a timeout is still released', async () => {
    vi.useFakeTimers();
    try {
      const late = deferred<{ canvas: HTMLCanvasElement; release: () => void }>();
      const release = vi.fn();
      const { deps } = fakeDeps({});
      const opened = await deps.openPdf(blob, new AbortController().signal);
      const run = recognizePages(blob, [2], new AbortController().signal, () => undefined, {
        ...deps,
        openPdf: () => Promise.resolve({ ...opened, render: () => late.promise }),
      });
      const assertion = expect(run).rejects.toMatchObject({ reason: 'timeout' });
      await vi.advanceTimersByTimeAsync(OCR_LIMITS.pageTimeoutMs + 1);
      await assertion;
      late.resolve({ canvas, release });
      await vi.advanceTimersByTimeAsync(0);
      expect(release).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancel aborts PDF loading through its signal before the document resolves', async () => {
    let loadSignal: AbortSignal | undefined;
    const { deps } = fakeDeps({});
    const controller = new AbortController();
    const run = recognizePages(blob, [2], controller.signal, () => undefined, {
      ...deps,
      openPdf: (_source, signal) => {
        loadSignal = signal;
        return new Promise(() => undefined);
      },
    });
    controller.abort();
    await expect(run).rejects.toMatchObject({ reason: 'cancelled' });
    expect(loadSignal?.aborted).toBe(true);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}
