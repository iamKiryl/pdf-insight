// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiClientError, type analyzeDocument } from '../api/client';
import { acceptedResult } from '../test/fixtures';
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
