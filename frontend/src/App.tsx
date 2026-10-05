import { FileDropzone } from './components/FileDropzone';
import { ResultView } from './components/ResultView';
import { AnalyzingStatus, ErrorPanel, ReadingStatus, ReadyPanel } from './components/StatusPanels';
import { AI_NOTICE } from './lib/messages';
import { useAnalysisFlow } from './lib/useAnalysisFlow';

export function App() {
  const { state, selectFile, start, cancel, reset } = useAnalysisFlow();

  return (
    <div className="page">
      <header className="masthead">
        <h1>PDF Insight</h1>
        <p>Podsumowanie i dane strukturalne z dokumentu PDF.</p>
      </header>

      <main id="main" className="content">
        <p className="notice" role="note">
          <strong>Informacja o danych:</strong> {AI_NOTICE}
        </p>

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
        Wyniki generuje model AI i mogą zawierać błędy — sprawdź kluczowe informacje w dokumencie.
      </footer>
    </div>
  );
}
