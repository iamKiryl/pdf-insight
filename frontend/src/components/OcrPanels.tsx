import { useEffect, useRef } from 'react';
import { formatPageList } from '../lib/format';
import { OCR_NOTICE, readinessMessage, type UserMessage } from '../lib/messages';
import type { OcrPageResult } from '../lib/ocr';
import type { Readiness } from '../lib/request';

/** Provenance note wherever OCR text was used (before analysis and on the result). */
export function OcrWarning({
  pages,
  before = false,
}: {
  pages: readonly number[];
  before?: boolean;
}) {
  const label = pages.length === 1 ? 'strony' : 'stron';
  return (
    <div className="warning" role="note">
      <span className="warning__symbol" aria-hidden="true">
        ⚠
      </span>
      <strong>Tekst z OCR.</strong> Treść {label} {formatPageList(pages)}{' '}
      {before ? 'pochodzi' : 'pochodziła'} z automatycznego rozpoznawania obrazu w przeglądarce i
      może zawierać błędy (kwoty, nazwiska, daty). Sprawdź te dane w oryginalnym dokumencie.
    </div>
  );
}

export function RecognizingStatus(props: {
  fileName: string;
  done: number;
  total: number;
  page: number;
  problem: UserMessage | null;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const { problem } = props;
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (problem) headingRef.current?.focus();
  }, [problem]);
  if (problem)
    return (
      <section className="panel panel--error" role="alert" aria-labelledby="ocr-error-title">
        <p className="label label--error">
          <span aria-hidden="true">✕ </span>OCR
        </p>
        <h2 id="ocr-error-title" ref={headingRef} tabIndex={-1} className="panel__title">
          {problem.title}
        </h2>
        <p>{problem.detail}</p>
        <div className="actions">
          {problem.retryable && (
            <button type="button" className="button button--primary" onClick={props.onRetry}>
              Spróbuj OCR ponownie
            </button>
          )}
          <button type="button" className="button" onClick={props.onCancel}>
            Wróć bez OCR
          </button>
        </div>
      </section>
    );
  const status =
    props.done === 0 && props.page === 0
      ? 'przygotowanie'
      : `strona ${props.page} (${props.done + 1 > props.total ? props.total : props.done + 1} z ${props.total})`;
  return (
    <section className="panel panel--active" aria-busy="true">
      <p className="label label--accent">02 · OCR w przeglądarce</p>
      <h2 className="panel__title">Rozpoznawanie tekstu ze skanów…</h2>
      <p className="muted break">
        {props.fileName} — {status}
      </p>
      <progress
        className="progress"
        max={props.total}
        value={props.done}
        aria-label="Postęp rozpoznawania tekstu"
      />
      <p className="muted">
        Pierwsze uruchomienie pobiera moduł OCR i dane językowe (ok. 10 MB) z tej strony.
      </p>
      <button type="button" className="button" onClick={props.onCancel}>
        Anuluj OCR
      </button>
    </section>
  );
}

export function OcrReview(props: {
  results: readonly OcrPageResult[];
  readiness: Readiness;
  recovered: readonly number[];
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const { results, readiness, recovered } = props;
  const unreadable = results.filter((r) => r.status === 'unreadable').map((r) => r.page);
  const problem = readiness.problem ? readinessMessage(readiness.problem) : null;
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  return (
    <section className="panel" aria-labelledby="ocr-review-title">
      <p className="label label--accent">02 · Wynik OCR do sprawdzenia</p>
      <h2 id="ocr-review-title" ref={headingRef} tabIndex={-1} className="panel__title">
        Sprawdź rozpoznany tekst
      </h2>
      <p className="notice__text">{OCR_NOTICE}</p>
      {unreadable.length > 0 && (
        <div className="warning" role="note">
          <span className="warning__symbol" aria-hidden="true">
            ⚠
          </span>
          <strong>Nie rozpoznano tekstu:</strong> {unreadable.length === 1 ? 'strona' : 'strony'}{' '}
          {formatPageList(unreadable)} — pozostanie oznaczona jako nieprzeanalizowana.
        </div>
      )}
      {results
        .filter((r) => r.status === 'recognized')
        .map((r) => (
          <div key={r.page} className="ocr-page">
            <p className="label">
              Strona {r.page} · pewność OCR {r.confidence}/100 ·{' '}
              {r.text.length.toLocaleString('pl-PL')} znaków
            </p>
            <pre className="ocr-page__text" tabIndex={0} aria-label={`Tekst OCR strony ${r.page}`}>
              {r.text}
            </pre>
          </div>
        ))}
      {problem && (
        <div className="warning" role="alert">
          <strong>{problem.title}.</strong> {problem.detail}
        </div>
      )}
      <div className="actions">
        <button
          type="button"
          className="button button--primary"
          onClick={props.onAccept}
          disabled={recovered.length === 0 || problem !== null}
        >
          Użyj rozpoznanego tekstu
        </button>
        <button type="button" className="button" onClick={props.onDiscard}>
          Odrzuć OCR
        </button>
      </div>
    </section>
  );
}
