// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiClientError, type analyzeDocument } from '../api/client';
import { acceptedResult } from '../test/fixtures';
import { OcrError, type OcrPageResult, type recognizePages } from './ocr';
import type { ExtractedDocument, extractPdf } from './pdf';
import { AnalysisResultSchema, type AnalysisResult } from './schema';
import { useAnalysisFlow } from './useAnalysisFlow';

const text = 'Umowa ramowa została zawarta pomiędzy stronami w Warszawie. '.repeat(6);
const extracted: ExtractedDocument = {
  fileName: 'umowa.pdf',
  fileBytes: 1000,
  pageCount: 2,
  pages: [
    { page: 1, text },
    { page: 2, text: '' },
  ],
  pagesWithoutText: [2],
};
const pdfFile = { name: 'umowa.pdf', size: 1000, type: 'application/pdf' } as File;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const extract: typeof extractPdf = () => Promise.resolve(extracted);

async function readyHook(analyze: typeof analyzeDocument) {
  const hook = renderHook(() => useAnalysisFlow({ analyze, extract }));
  await act(() => hook.result.current.selectFile(pdfFile));
  expect(hook.result.current.state.phase).toBe('ready');
  return hook;
}

describe('useAnalysisFlow', () => {
  it('ignores a stale response after cancel and a newer request', async () => {
    const first = deferred<AnalysisResult>();
    const second = deferred<AnalysisResult>();
    const analyze = vi
      .fn<typeof analyzeDocument>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = await readyHook(analyze);

    act(() => {
      result.current.start();
    });
    expect(result.current.state.phase).toBe('analyzing');
    const firstSignal = analyze.mock.calls[0]![1].signal;
    act(() => {
      result.current.cancel();
    });
    expect(firstSignal.aborted).toBe(true);
    expect(result.current.state.phase).toBe('ready');

    act(() => {
      result.current.start();
    });
    const fresh = AnalysisResultSchema.parse(acceptedResult());
    const stale = { ...fresh, summary: 'Stary wynik. Nie powinien się pojawić. Naprawdę nie.' };
    await act(async () => {
      first.resolve(stale);
      await Promise.resolve();
    });
    expect(result.current.state.phase).toBe('analyzing');
    await act(async () => {
      second.resolve(fresh);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.state.phase).toBe('done');
    });
    const state = result.current.state;
    expect(state.phase === 'done' && state.result.summary).toBe(fresh.summary);
    expect(analyze).toHaveBeenCalledTimes(2);
  });

  it('shows a retryable error and retries only on explicit user action', async () => {
    const analyze = vi
      .fn<typeof analyzeDocument>()
      .mockRejectedValueOnce(
        new ApiClientError('AI_UNAVAILABLE', 'Usługa AI jest chwilowo niedostępna.', true, 502),
      )
      .mockResolvedValueOnce(AnalysisResultSchema.parse(acceptedResult()));
    const { result } = await readyHook(analyze);
    await act(async () => {
      result.current.start();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.state.phase).toBe('error');
    });
    expect(analyze).toHaveBeenCalledTimes(1);
    await act(async () => {
      result.current.start();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.state.phase).toBe('done');
    });
    expect(analyze).toHaveBeenCalledTimes(2);
  });

  it('rejects a fully scanned PDF before contacting the API', async () => {
    const analyze = vi.fn<typeof analyzeDocument>();
    const scanned: typeof extractPdf = () =>
      Promise.resolve({
        ...extracted,
        pages: [{ page: 1, text: '' }],
        pageCount: 1,
        pagesWithoutText: [1],
      });
    const { result } = renderHook(() => useAnalysisFlow({ analyze, extract: scanned }));
    await act(() => result.current.selectFile(pdfFile));
    const state = result.current.state;
    expect(state.phase).toBe('error');
    expect(state.phase === 'error' && state.message.detail).toContain('OCR');
    expect(analyze).not.toHaveBeenCalled();
  });

  it('rejects oversized files without reading them', async () => {
    const spy = vi.fn<typeof extractPdf>();
    const { result } = renderHook(() => useAnalysisFlow({ extract: spy }));
    const huge = { name: 'duzy.pdf', size: 11 * 1024 * 1024, type: 'application/pdf' } as File;
    await act(() => result.current.selectFile(huge));
    expect(result.current.state.phase).toBe('error');
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('optional browser OCR in the flow', () => {
  const source = new Blob(['%PDF-1.7']);
  const scanned: ExtractedDocument = { ...extracted, source };
  const ocrResult: OcrPageResult[] = [
    {
      page: 2,
      text: 'Aneks nr 1. Kwota 5 000,00 zł netto.',
      confidence: 90,
      status: 'recognized',
      preview: null,
    },
  ];

  async function scannedHook(recognize: typeof recognizePages, doc = scanned) {
    const analyze = vi.fn<typeof analyzeDocument>();
    const hook = renderHook(() =>
      useAnalysisFlow({ analyze, extract: () => Promise.resolve(doc), recognize }),
    );
    await act(() => hook.result.current.selectFile(pdfFile));
    return { ...hook, analyze };
  }

  it('runs only on explicit action, shows the text for review and never calls the model', async () => {
    const recognize = vi.fn<typeof recognizePages>().mockResolvedValue(ocrResult);
    const { result, analyze } = await scannedHook(recognize);
    expect(result.current.state.phase).toBe('ready');
    expect(recognize).not.toHaveBeenCalled();
    await act(() => result.current.startOcr());
    expect(recognize.mock.calls[0]?.[1]).toEqual([2]);
    const review = result.current.state;
    expect(review.phase).toBe('ocr-review');
    if (review.phase !== 'ocr-review') return;
    expect(review.merged.ocrPages).toEqual([2]);
    expect(review.readiness.request.ocrPages).toEqual([2]);
    act(() => {
      result.current.acceptOcr();
    });
    const ready = result.current.state;
    expect(ready.phase === 'ready' && ready.readiness.request.pagesWithoutText).toEqual([]);
    expect(analyze).not.toHaveBeenCalled();
  });

  it('discarding keeps the original partial document unchanged', async () => {
    const recognize = vi.fn<typeof recognizePages>().mockResolvedValue(ocrResult);
    const { result } = await scannedHook(recognize);
    await act(() => result.current.startOcr());
    act(() => {
      result.current.discardOcr();
    });
    const state = result.current.state;
    expect(state.phase === 'ready' && state.readiness.request).toEqual({
      fileName: 'umowa.pdf',
      pageCount: 2,
      pages: extracted.pages,
      pagesWithoutText: [2],
    });
  });

  it('a cancelled run is aborted and its late result never attaches (also after a new file)', async () => {
    const late = deferred<OcrPageResult[]>();
    const recognize = vi.fn<typeof recognizePages>().mockReturnValue(late.promise);
    const { result } = await scannedHook(recognize);
    act(() => {
      void result.current.startOcr();
    });
    expect(result.current.state.phase).toBe('recognizing');
    const signal = recognize.mock.calls[0]![2];
    act(() => {
      result.current.cancel();
    });
    expect(signal.aborted).toBe(true);
    expect(result.current.state.phase).toBe('ready');
    await act(() => result.current.selectFile(pdfFile));
    await act(async () => {
      late.resolve(ocrResult);
      await Promise.resolve();
    });
    const state = result.current.state;
    expect(state.phase === 'ready' && state.doc.ocrPages).toBeUndefined();
  });

  it('a failure shows a useful message with retry and a way back without OCR', async () => {
    const recognize = vi
      .fn<typeof recognizePages>()
      .mockRejectedValueOnce(new OcrError('load-failed'))
      .mockResolvedValueOnce(ocrResult);
    const { result } = await scannedHook(recognize);
    await act(() => result.current.startOcr());
    const failed = result.current.state;
    expect(failed.phase === 'recognizing' && failed.problem?.title).toBe(
      'Nie udało się uruchomić OCR',
    );
    await act(() => result.current.startOcr());
    expect(result.current.state.phase).toBe('ocr-review');
  });

  it('an unreadable page stays flagged and cannot be accepted alone', async () => {
    const recognize = vi
      .fn<typeof recognizePages>()
      .mockResolvedValue([
        { page: 2, text: '|', confidence: 12, status: 'unreadable', preview: null },
      ]);
    const { result } = await scannedHook(recognize);
    await act(() => result.current.startOcr());
    act(() => {
      result.current.acceptOcr();
    });
    const state = result.current.state;
    expect(state.phase).toBe('ocr-review');
    expect(state.phase === 'ocr-review' && state.merged.pagesWithoutText).toEqual([2]);
  });

  it('a fully scanned PDF gets the OCR option on the no-text error', async () => {
    const allScanned: ExtractedDocument = {
      ...scanned,
      pageCount: 1,
      pages: [{ page: 1, text: '' }],
      pagesWithoutText: [1],
    };
    const text = 'Aneks nr 1 do umowy. Wynagrodzenie netto wynosi 48 750,00 zł. '.repeat(5);
    const recognize = vi
      .fn<typeof recognizePages>()
      .mockResolvedValue([{ page: 1, text, confidence: 95, status: 'recognized', preview: null }]);
    const { result } = await scannedHook(recognize, allScanned);
    const error = result.current.state;
    expect(error.phase === 'error' && error.ocr).toBeTruthy();
    await act(() => result.current.startOcr());
    act(() => {
      result.current.acceptOcr();
    });
    const ready = result.current.state;
    expect(ready.phase === 'ready' && ready.readiness.request.ocrPages).toEqual([1]);
    act(() => {
      result.current.discardOcr();
    });
  });
});

describe('OCR review fixes in the flow', () => {
  const source = new Blob(['%PDF-1.7']);
  const threePages: ExtractedDocument = {
    fileName: 'umowa.pdf',
    fileBytes: 1000,
    pageCount: 3,
    pages: [
      { page: 1, text },
      { page: 2, text: '' },
      { page: 3, text: '' },
    ],
    pagesWithoutText: [2, 3],
    source,
  };
  const result = (page: number, value: string): OcrPageResult => ({
    page,
    text: value,
    confidence: 80,
    status: /\p{L}/u.test(value) ? 'recognized' : 'unreadable',
    preview: null,
  });

  async function hook(recognize: typeof recognizePages) {
    const h = renderHook(() =>
      useAnalysisFlow({
        analyze: vi.fn<typeof analyzeDocument>(),
        extract: () => Promise.resolve(threePages),
        recognize,
      }),
    );
    await act(() => h.result.current.selectFile(pdfFile));
    return h;
  }

  it('two OCR passes send ocrPages [2, 3]; the second pass only reads the remaining page', async () => {
    const recognize = vi
      .fn<typeof recognizePages>()
      .mockResolvedValueOnce([result(2, 'Aneks nr 1.'), result(3, '')])
      .mockResolvedValueOnce([result(3, 'Załącznik nr 2.')]);
    const { result: r } = await hook(recognize);
    await act(() => r.current.startOcr());
    act(() => {
      r.current.acceptOcr();
    });
    await act(() => r.current.startOcr());
    expect(recognize.mock.calls[1]?.[1]).toEqual([3]);
    act(() => {
      r.current.acceptOcr();
    });
    const state = r.current.state;
    expect(state.phase === 'ready' && state.readiness.request.ocrPages).toEqual([2, 3]);
    expect(state.phase === 'ready' && state.readiness.request.pagesWithoutText).toEqual([]);
  });

  it('edits recompute readiness; reset restores machine text; discard restores pre-OCR data', async () => {
    const recognize = vi
      .fn<typeof recognizePages>()
      .mockResolvedValue([result(2, 'zmienić $ 5 ust. 2'), result(3, '')]);
    const { result: r } = await hook(recognize);
    await act(() => r.current.startOcr());
    act(() => {
      r.current.editOcr(2, 'zmienić § 5 ust. 2');
      r.current.editOcr(3, 'Strona wpisana ręcznie.');
    });
    let state = r.current.state;
    expect(state.phase === 'ocr-review' && state.readiness.request.pages[1]?.text).toBe(
      'zmienić § 5 ust. 2',
    );
    expect(state.phase === 'ocr-review' && state.merged.ocrPages).toEqual([2, 3]);
    expect(state.phase === 'ocr-review' && state.results[0]?.text).toBe('zmienić $ 5 ust. 2');
    act(() => {
      r.current.resetOcrPage(2);
    });
    state = r.current.state;
    expect(state.phase === 'ocr-review' && state.readiness.request.pages[1]?.text).toBe(
      'zmienić $ 5 ust. 2',
    );
    act(() => {
      r.current.editOcr(2, 'Ą'.repeat(20_001));
    });
    state = r.current.state;
    expect(state.phase === 'ocr-review' && state.readiness.problem).toBe('page-too-long');
    act(() => {
      r.current.acceptOcr(); // blocked by the limit, nothing truncated
    });
    expect(r.current.state.phase).toBe('ocr-review');
    act(() => {
      r.current.discardOcr();
    });
    state = r.current.state;
    expect(state.phase === 'ready' && state.readiness.request).toEqual({
      fileName: 'umowa.pdf',
      pageCount: 3,
      pages: threePages.pages,
      pagesWithoutText: [2, 3],
    });
  });
});
