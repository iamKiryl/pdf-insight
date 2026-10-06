import { FileDropzone } from './components/FileDropzone';
import { FlowSteps } from './components/FlowSteps';
import { ResultView } from './components/ResultView';
import { AnalyzingStatus, ErrorPanel, ReadingStatus, ReadyPanel } from './components/StatusPanels';
import { flowSteps } from './lib/flowSteps';
import { AI_NOTICE } from './lib/messages';
import { useAnalysisFlow } from './lib/useAnalysisFlow';

export function App() {
  const { state, selectFile, start, cancel, reset } = useAnalysisFlow();
  const steps = flowSteps(state);
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

        {state.phase === 'idle' && <FileDropzone onFile={(file) => void selectFile(file)} />}
        {state.phase === 'reading' && (
          <ReadingStatus
            fileName={state.fileName}
            page={state.page}
            total={state.total}
            onCancel={cancel}
          />
        )}
        {state.phase === 'ready' && (
          <ReadyPanel
            doc={state.doc}
            readiness={state.readiness}
            onAnalyze={start}
            onReset={reset}
          />
        )}
        {state.phase === 'analyzing' && (
          <AnalyzingStatus
            fileName={state.doc.fileName}
            startedAt={state.startedAt}
            onCancel={cancel}
          />
        )}
        {state.phase === 'error' && (
          <ErrorPanel
            message={state.message}
            onRetry={state.retry ? start : null}
            onReset={reset}
          />
        )}
        {state.phase === 'done' && (
          <ResultView result={state.result} durationMs={state.durationMs} onReset={reset} />
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
