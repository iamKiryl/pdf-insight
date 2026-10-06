import { useEffect, useRef } from 'react';
import { hasLetter } from '../lib/contract';
import { formatPageList } from '../lib/format';
import { OCR_NOTICE, readinessMessage, type UserMessage } from '../lib/messages';
import type { OcrEdits, OcrPageResult } from '../lib/ocr';
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

/** Page image via an object URL that lives only while the preview is mounted. */
function PagePreview({ image, page }: { image: Blob; page: number }) {
  const linkRef = useRef<HTMLAnchorElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(image);
    if (linkRef.current) linkRef.current.href = url;
    if (imgRef.current) imgRef.current.src = url;
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [image]);
  return (
    <a ref={linkRef} className="ocr-page__preview" target="_blank" rel="noreferrer">
      <img ref={imgRef} alt={`Obraz strony ${String(page)} z pliku PDF (do porównania)`} />
      <span className="label">Otwórz obraz strony {page} w pełnym rozmiarze</span>
    </a>
  );
}

function OcrPageEditor(props: {
  result: OcrPageResult;
  text: string;
  edited: boolean;
  onEdit: (text: string) => void;
  onReset: () => void;
}) {
  const { result, text, edited } = props;
  const id = `ocr-text-${result.page}`;
  const noText = !hasLetter(text);
  return (
    <div className="ocr-page">
      <label className="label" htmlFor={id}>
        Strona {result.page} — tekst do sprawdzenia i poprawy
      </label>
      <p className="muted ocr-page__meta">
        {edited
          ? 'Poprawiono ręcznie (pewność OCR dotyczyła tylko tekstu maszynowego).'
          : result.status === 'unreadable'
            ? 'OCR nie rozpoznał tekstu — możesz go wpisać, porównując z obrazem strony.'
            : `Tekst maszynowy, pewność OCR ${String(result.confidence)}/100 (orientacyjnie).`}{' '}
        {text.length.toLocaleString('pl-PL')} znaków
        {noText ? ' · strona pozostanie nieprzeanalizowana' : ''}
      </p>
      <div className="ocr-page__compare">
        {result.preview && <PagePreview image={result.preview} page={result.page} />}
        <textarea
          id={id}
          className="ocr-page__text"
          value={text}
          spellCheck={false}
          onChange={(event) => {
            props.onEdit(event.target.value);
          }}
        />
      </div>
      {edited && (
        <button type="button" className="button button--quiet" onClick={props.onReset}>
          Przywróć tekst rozpoznany przez OCR
        </button>
      )}
    </div>
  );
}

export function OcrReview(props: {
  results: readonly OcrPageResult[];
  edits: OcrEdits;
  readiness: Readiness;
  /** Pages this review would add as OCR text. */
  recovered: readonly number[];
  onEdit: (page: number, text: string) => void;
  onResetPage: (page: number) => void;
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const { results, edits, readiness, recovered } = props;
  const problem = readiness.problem ? readinessMessage(readiness.problem) : null;
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  return (
    <section className="panel" aria-labelledby="ocr-review-title">
      <p className="label label--accent">02 · Wynik OCR do sprawdzenia</p>
      <h2 id="ocr-review-title" ref={headingRef} tabIndex={-1} className="panel__title">
        Sprawdź i popraw rozpoznany tekst
      </h2>
      <p className="notice__text">{OCR_NOTICE}</p>
      <p className="muted">
        Porównaj tekst z obrazem strony i popraw błędy (np. „$” zamiast „§”, „0” zamiast „o”,
        pominięty nagłówek). Nic nie jest zmieniane automatycznie.
      </p>
      {results.map((result) => (
        <OcrPageEditor
          key={result.page}
          result={result}
          text={edits[result.page] ?? result.text}
          edited={edits[result.page] !== undefined && edits[result.page] !== result.text}
          onEdit={(text) => {
            props.onEdit(result.page, text);
          }}
          onReset={() => {
            props.onResetPage(result.page);
          }}
        />
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
          Użyj tego tekstu
        </button>
        <button type="button" className="button" onClick={props.onDiscard}>
          Odrzuć OCR
        </button>
      </div>
    </section>
  );
}
