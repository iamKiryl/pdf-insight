import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClientError, analyzeDocument } from '../api/client';
import {
  apiErrorMessage,
  extractionMessage,
  fileProblemMessage,
  readinessMessage,
  type UserMessage,
} from './messages';
import { PdfExtractionError, checkFile, extractPdf, type ExtractedDocument } from './pdf';
import { prepareRequest, type Readiness } from './request';
import type { AnalysisResult } from './schema';

export type FlowState =
  | { phase: 'idle' }
  | { phase: 'reading'; fileName: string; page: number; total: number }
  | { phase: 'ready'; doc: ExtractedDocument; readiness: Readiness }
  | { phase: 'analyzing'; doc: ExtractedDocument; readiness: Readiness; startedAt: number }
  | { phase: 'done'; doc: ExtractedDocument; result: AnalysisResult; durationMs: number }
  | {
      phase: 'error';
      message: UserMessage;
      retry: { doc: ExtractedDocument; readiness: Readiness } | null;
    };

type Analyze = typeof analyzeDocument;
type Extract = typeof extractPdf;

/**
 * Upload → extract → analyze flow. Every operation gets a run id and an AbortController; results
 * from an older run (after cancel, reset or a new file) are ignored, so a slow stale response can
 * never replace a newer state.
 */
export function useAnalysisFlow(deps: { analyze?: Analyze; extract?: Extract } = {}) {
  const analyze = deps.analyze ?? analyzeDocument;
  const extract = deps.extract ?? extractPdf;
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
        setState({ phase: 'error', message: fileProblemMessage(problem), retry: null });
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
          setState({ phase: 'error', message: readinessMessage(readiness.problem), retry: null });
          return;
        }
        setState({ phase: 'ready', doc, readiness });
      } catch (error) {
        if (!run.isCurrent()) return;
        const reason = error instanceof PdfExtractionError ? error.reason : 'corrupt';
        setState({ phase: 'error', message: extractionMessage(reason), retry: null });
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
        setState({ phase: 'error', message, retry: message.retryable ? { doc, readiness } : null });
      }
    },
    [analyze, startRun],
  );

  const start = useCallback(() => {
    if (state.phase === 'ready') void runAnalysis(state.doc, state.readiness);
    else if (state.phase === 'error' && state.retry)
      void runAnalysis(state.retry.doc, state.retry.readiness);
  }, [runAnalysis, state]);

  const cancel = useCallback(() => {
    startRun(); // aborts the in-flight request and invalidates its result
    setState((current) =>
      current.phase === 'analyzing'
        ? { phase: 'ready', doc: current.doc, readiness: current.readiness }
        : { phase: 'idle' },
    );
  }, [startRun]);

  const reset = useCallback(() => {
    startRun();
    setState({ phase: 'idle' });
  }, [startRun]);

  return { state, selectFile, start, cancel, reset };
}
