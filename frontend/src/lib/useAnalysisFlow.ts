import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClientError, analyzeDocument } from '../api/client';
import {
  apiErrorMessage,
  extractionMessage,
  ocrMessage,
  fileProblemMessage,
  readinessMessage,
  type UserMessage,
} from './messages';
import { OcrError, applyOcr, recognizePages, type OcrEdits, type OcrPageResult } from './ocr';
import { PdfExtractionError, checkFile, extractPdf, type ExtractedDocument } from './pdf';
import { prepareRequest, type Readiness } from './request';
import type { AnalysisResult } from './schema';

/** Where OCR was offered: the ready panel (partial scan) or the no-text-layer error. */
export type OcrOrigin =
  | { phase: 'ready'; doc: ExtractedDocument; readiness: Readiness }
  | {
      phase: 'error';
      stage: 'read';
      message: UserMessage;
      retry: null;
      ocr: ExtractedDocument;
    };

export type FlowState =
  | { phase: 'idle' }
  | { phase: 'reading'; fileName: string; page: number; total: number }
  | { phase: 'ready'; doc: ExtractedDocument; readiness: Readiness }
  | { phase: 'analyzing'; doc: ExtractedDocument; readiness: Readiness; startedAt: number }
  | { phase: 'done'; doc: ExtractedDocument; result: AnalysisResult; durationMs: number }
  | {
      phase: 'error';
      /** Where the flow stopped (shown by the step indicator). */
      stage: 'upload' | 'read' | 'analyze';
      message: UserMessage;
      retry: { doc: ExtractedDocument; readiness: Readiness } | null;
      /** A text-less document that browser OCR may still recover. */
      ocr?: ExtractedDocument;
    }
  | {
      phase: 'recognizing';
      origin: OcrOrigin;
      done: number;
      total: number;
      page: number;
      problem: UserMessage | null;
    }
  | {
      phase: 'ocr-review';
      origin: OcrOrigin;
      /** Machine OCR output, unchanged (for reset and comparison). */
      results: OcrPageResult[];
      /** The user's corrections by page. */
      edits: OcrEdits;
      merged: ExtractedDocument;
      readiness: Readiness;
    };

type ReviewState = Extract<FlowState, { phase: 'ocr-review' }>;

function originDoc(origin: OcrOrigin): ExtractedDocument {
  return origin.phase === 'ready' ? origin.doc : origin.ocr;
}

/** Review state with the document and readiness recomputed from machine text plus edits. */
function reviewState(origin: OcrOrigin, results: OcrPageResult[], edits: OcrEdits): ReviewState {
  const merged = applyOcr(originDoc(origin), results, edits);
  return { phase: 'ocr-review', origin, results, edits, merged, readiness: prepareRequest(merged) };
}

/** Pages this review adds as OCR text (earlier accepted OCR pages excluded). */
export function newOcrPages(state: ReviewState): number[] {
  const before = new Set(originDoc(state.origin).ocrPages ?? []);
  return (state.merged.ocrPages ?? []).filter((page) => !before.has(page));
}

type Analyze = typeof analyzeDocument;
type ExtractPdf = typeof extractPdf;
type Recognize = typeof recognizePages;

/**
 * Upload → extract → analyze flow. Every operation gets a run id and an AbortController; results
 * from an older run (after cancel, reset or a new file) are ignored, so a slow stale response can
 * never replace a newer state.
 */
export function useAnalysisFlow(
  deps: { analyze?: Analyze; extract?: ExtractPdf; recognize?: Recognize } = {},
) {
  const analyze = deps.analyze ?? analyzeDocument;
  const extract = deps.extract ?? extractPdf;
  const recognize = deps.recognize ?? recognizePages;
  const [state, setState] = useState<FlowState>({ phase: 'idle' });
  const runId = useRef(0);
  const controller = useRef<AbortController | null>(null);

  const startRun = useCallback(() => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    runId.current += 1;
    const id = runId.current;
    return { id, signal: next.signal, isCurrent: () => runId.current === id };
  }, []);

  useEffect(() => () => controller.current?.abort(), []);

  const selectFile = useCallback(
    async (file: File) => {
      const run = startRun();
      const problem = checkFile(file);
      if (problem) {
        setState({
          phase: 'error',
          stage: 'upload',
          message: fileProblemMessage(problem),
          retry: null,
        });
        return;
      }
      setState({ phase: 'reading', fileName: file.name, page: 0, total: 0 });
      try {
        const doc = await extract(file, run.signal, (page, total) => {
          if (run.isCurrent()) setState({ phase: 'reading', fileName: file.name, page, total });
        });
        if (!run.isCurrent()) return;
        const readiness = prepareRequest(doc);
        if (readiness.problem) {
          setState({
            phase: 'error',
            stage: 'read',
            message: readinessMessage(readiness.problem),
            retry: null,
            ...(readiness.problem === 'no-text-layer' && doc.source ? { ocr: doc } : {}),
          });
          return;
        }
        setState({ phase: 'ready', doc, readiness });
      } catch (error) {
        if (!run.isCurrent()) return;
        const reason = error instanceof PdfExtractionError ? error.reason : 'corrupt';
        setState({
          phase: 'error',
          stage: 'read',
          message: extractionMessage(reason),
          retry: null,
        });
      }
    },
    [extract, startRun],
  );

  const runAnalysis = useCallback(
    async (doc: ExtractedDocument, readiness: Readiness) => {
      const run = startRun();
      const startedAt = performance.now();
      setState({ phase: 'analyzing', doc, readiness, startedAt });
      try {
        const result = await analyze(readiness.request, { signal: run.signal });
        if (!run.isCurrent()) return;
        setState({ phase: 'done', doc, result, durationMs: performance.now() - startedAt });
      } catch (error) {
        if (!run.isCurrent()) return;
        const clientError =
          error instanceof ApiClientError ? error : new ApiClientError('NETWORK_ERROR', null, true);
        if (clientError.code === 'CANCELLED') return;
        const message = apiErrorMessage(clientError);
        const retry = message.retryable ? { doc, readiness } : null;
        setState({ phase: 'error', stage: 'analyze', message, retry });
      }
    },
    [analyze, startRun],
  );

  /** Explicit user action: recognise the scanned pages. Nothing is sent anywhere afterwards. */
  const startOcr = useCallback(async () => {
    let origin: OcrOrigin;
    if (state.phase === 'ready') origin = state;
    else if (state.phase === 'recognizing' && state.problem) origin = state.origin;
    else if (state.phase === 'error' && state.ocr)
      origin = { ...state, stage: 'read', retry: null, ocr: state.ocr };
    else return;
    const doc = originDoc(origin);
    if (!doc.source || doc.pagesWithoutText.length === 0) return;
    const run = startRun();
    const pages = doc.pagesWithoutText;
    const base = { phase: 'recognizing', origin, total: pages.length, problem: null } as const;
    setState({ ...base, done: 0, page: pages[0] ?? 0 });
    try {
      const results = await recognize(doc.source, pages, run.signal, (done, total, page) => {
        if (run.isCurrent()) setState({ ...base, total, done, page });
      });
      if (!run.isCurrent()) return;
      setState(reviewState(origin, results, {}));
    } catch (error) {
      if (!run.isCurrent()) return;
      const reason = error instanceof OcrError ? error.reason : 'failed';
      if (reason === 'cancelled') return;
      setState({ ...base, done: 0, page: 0, problem: ocrMessage(reason) });
    }
  }, [recognize, startRun, state]);

  /** The user corrects one page (never automated); readiness and missing pages are recomputed. */
  const editOcr = useCallback((page: number, text: string) => {
    setState((current) =>
      current.phase === 'ocr-review'
        ? reviewState(current.origin, current.results, { ...current.edits, [page]: text })
        : current,
    );
  }, []);

  /** Restores the machine-recognised text of one page. */
  const resetOcrPage = useCallback((page: number) => {
    setState((current) => {
      if (current.phase !== 'ocr-review') return current;
      const edits = Object.fromEntries(
        Object.entries(current.edits).filter(([key]) => Number(key) !== page),
      );
      return reviewState(current.origin, current.results, edits);
    });
  }, []);

  /** The user accepts the reviewed OCR text: back to "ready", now with OCR pages marked. */
  const acceptOcr = useCallback(() => {
    if (state.phase !== 'ocr-review' || state.readiness.problem || !newOcrPages(state).length)
      return;
    startRun();
    setState({ phase: 'ready', doc: state.merged, readiness: state.readiness });
  }, [startRun, state]);

  /** Leave OCR (cancel, failure or rejected text): the previous panel, unchanged. */
  const discardOcr = useCallback(() => {
    startRun(); // terminates a running OCR and ignores its result
    setState((current) =>
      current.phase === 'recognizing' || current.phase === 'ocr-review' ? current.origin : current,
    );
  }, [startRun]);

  const start = useCallback(() => {
    if (state.phase === 'ready') void runAnalysis(state.doc, state.readiness);
    else if (state.phase === 'error' && state.retry)
      void runAnalysis(state.retry.doc, state.retry.readiness);
  }, [runAnalysis, state]);

  const cancel = useCallback(() => {
    startRun(); // aborts the in-flight request and invalidates its result
    setState((current) => {
      if (current.phase === 'analyzing')
        return { phase: 'ready', doc: current.doc, readiness: current.readiness };
      if (current.phase === 'recognizing' || current.phase === 'ocr-review') return current.origin;
      return { phase: 'idle' };
    });
  }, [startRun]);

  const reset = useCallback(() => {
    startRun();
    setState({ phase: 'idle' });
  }, [startRun]);

  return {
    state,
    selectFile,
    start,
    cancel,
    reset,
    startOcr,
    editOcr,
    resetOcrPage,
    acceptOcr,
    discardOcr,
  };
}
