import { useEffect, useRef, useState } from 'react';
import { FileDropzone } from './components/FileDropzone';
import { FlowSteps } from './components/FlowSteps';
import { HistoryPanel } from './components/HistoryPanel';
import { OcrReview, RecognizingStatus } from './components/OcrPanels';
import { ResultView } from './components/ResultView';
import { AnalyzingStatus, ErrorPanel, ReadingStatus, ReadyPanel } from './components/StatusPanels';
import { finishedSteps, flowSteps } from './lib/flowSteps';
import type { HistoryEntry } from './lib/history';
import { AI_NOTICE } from './lib/messages';
import type { AnalysisResult } from './lib/schema';
import { newOcrPages, useAnalysisFlow } from './lib/useAnalysisFlow';
import { useHistory, type HistoryStorageOption } from './lib/useHistory';

export function App({ historyStorage }: { historyStorage?: HistoryStorageOption } = {}) {
  const flow = useAnalysisFlow();
  const { state, selectFile, start, cancel, reset, startOcr, acceptOcr, discardOcr } = flow;
  const history = useHistory(historyStorage);
  const [opened, setOpened] = useState<HistoryEntry | null>(null);
  const saved = useRef<AnalysisResult | null>(null);
  const { add } = history;

  // A finished analysis is saved once (validated result + file metadata only).
  useEffect(() => {
    if (state.phase !== 'done' || saved.current === state.result) return;
    saved.current = state.result;
    add(state.result, { fileBytes: state.doc.fileBytes, durationMs: state.durationMs });
  }, [state, add]);

  const steps = opened ? finishedSteps() : flowSteps(state);
  const current = steps.find((step) => step.current);

  return (
    <div className="page">
      <header className="masthead">
        <span className="masthead__digit" aria-hidden="true">
          {current?.number ?? '04'}
        </span>
        <p className="label label--accent label--rule">Analiza dokumentów</p>
        <h1 className="masthead__title">PDF Insight</h1>
        <p className="masthead__lead">
          Wgraj plik PDF, a otrzymasz <strong>krótkie podsumowanie</strong> i{' '}
          <strong>uporządkowane dane</strong>: kwoty, daty, podmioty i słowa kluczowe — gotowe do
          pobrania jako JSON.
        </p>
      </header>

      <FlowSteps steps={steps} />

      <main id="main" className="content">
        <section className="notice" role="note" aria-labelledby="notice-title">
          <p id="notice-title" className="label label--accent">
            Informacja o danych
          </p>
          <p className="notice__text">{AI_NOTICE}</p>
        </section>

        <div aria-live="polite" className="visually-hidden">
          {state.phase === 'analyzing' && 'Trwa analiza dokumentu.'}
          {state.phase === 'done' && 'Analiza zakończona.'}
        </div>

        {opened && (
          <ResultView
            result={opened.result}
            durationMs={opened.durationMs}
            savedAt={opened.savedAt}
            onReset={() => {
              setOpened(null);
            }}
          />
        )}
        {!opened && state.phase === 'idle' && (
          <>
            <FileDropzone onFile={(file) => void selectFile(file)} />
            <HistoryPanel
              entries={history.entries}
              status={history.status}
              skipped={history.skipped}
              onOpen={setOpened}
              onRemove={history.remove}
              onClear={history.clear}
            />
          </>
        )}
        {!opened && state.phase === 'reading' && (
          <ReadingStatus
            fileName={state.fileName}
            page={state.page}
            total={state.total}
            onCancel={cancel}
          />
        )}
        {!opened && state.phase === 'ready' && (
          <ReadyPanel
            doc={state.doc}
            readiness={state.readiness}
            onAnalyze={start}
            onReset={reset}
            onOcr={
              state.doc.pagesWithoutText.length > 0 && state.doc.source
                ? () => void startOcr()
                : null
            }
          />
        )}
        {!opened && state.phase === 'recognizing' && (
          <RecognizingStatus
            fileName={
              state.origin.phase === 'ready' ? state.origin.doc.fileName : state.origin.ocr.fileName
            }
            done={state.done}
            total={state.total}
            page={state.page}
            problem={state.problem}
            onCancel={discardOcr}
            onRetry={() => void startOcr()}
          />
        )}
        {!opened && state.phase === 'ocr-review' && (
          <OcrReview
            results={state.results}
            edits={state.edits}
            readiness={state.readiness}
            recovered={newOcrPages(state)}
            onEdit={flow.editOcr}
            onResetPage={flow.resetOcrPage}
            onAccept={acceptOcr}
            onDiscard={discardOcr}
          />
        )}
        {!opened && state.phase === 'analyzing' && (
          <AnalyzingStatus
            fileName={state.doc.fileName}
            startedAt={state.startedAt}
            onCancel={cancel}
          />
        )}
        {!opened && state.phase === 'error' && (
          <ErrorPanel
            message={state.message}
            onRetry={state.retry ? start : null}
            onReset={reset}
            onOcr={state.ocr ? () => void startOcr() : null}
          />
        )}
        {!opened && state.phase === 'done' && (
          <ResultView
            result={state.result}
            durationMs={state.durationMs}
            savedToHistory={history.entries.some((entry) => entry.result === state.result)}
            onReset={reset}
          />
        )}
      </main>

      <footer className="footer">
        <p>
          Wyniki generuje model AI i mogą zawierać błędy — sprawdź kluczowe informacje w dokumencie.
        </p>
        <p className="label">PDF Insight // analiza dokumentów</p>
      </footer>
    </div>
  );
}
