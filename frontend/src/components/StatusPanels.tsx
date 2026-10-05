import { useEffect, useRef, useState } from 'react';
import { formatBytes, formatSeconds } from '../lib/format';
import type { UserMessage } from '../lib/messages';
import type { ExtractedDocument } from '../lib/pdf';
import type { Readiness } from '../lib/request';
import { PartialWarning } from './PartialWarning';

export function ReadingStatus(props: {
  fileName: string;
  page: number;
  total: number;
  onCancel: () => void;
}) {
  const progress = props.total ? `strona ${props.page} z ${props.total}` : 'otwieranie pliku';
  return (
    <section className="panel" aria-busy="true">
      <h2 className="panel__title">Odczytywanie dokumentu</h2>
      <p className="muted">
        {props.fileName} — {progress}
      </p>
      {props.total > 0 && (
        <progress
          className="progress"
          max={props.total}
          value={props.page}
          aria-label="Postęp odczytu"
        />
      )}
      <button type="button" className="button" onClick={props.onCancel}>
        Anuluj
      </button>
    </section>
  );
}

export function ReadyPanel(props: {
  doc: ExtractedDocument;
  readiness: Readiness;
  onAnalyze: () => void;
  onReset: () => void;
}) {
  const { doc, readiness } = props;
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => buttonRef.current?.focus(), []);
  return (
    <section className="panel" aria-labelledby="ready-title">
      <h2 id="ready-title" className="panel__title">
        Dokument gotowy do analizy
      </h2>
      <dl className="facts">
        <div>
          <dt>Plik</dt>
          <dd className="break">{doc.fileName}</dd>
        </div>
        <div>
          <dt>Rozmiar</dt>
          <dd>{formatBytes(doc.fileBytes)}</dd>
        </div>
        <div>
          <dt>Strony</dt>
          <dd>{doc.pageCount}</dd>
        </div>
        <div>
          <dt>Znaki tekstu</dt>
          <dd>{readiness.totalChars.toLocaleString('pl-PL')}</dd>
        </div>
      </dl>
      {doc.pagesWithoutText.length > 0 && (
        <PartialWarning pages={doc.pagesWithoutText} total={doc.pageCount} before />
      )}
      <div className="actions">
        <button
          ref={buttonRef}
          type="button"
          className="button button--primary"
          onClick={props.onAnalyze}
        >
          Analizuj z AI
        </button>
        <button type="button" className="button" onClick={props.onReset}>
          Wybierz inny plik
        </button>
      </div>
    </section>
  );
}

export function AnalyzingStatus(props: {
  fileName: string;
  startedAt: number;
  onCancel: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(performance.now() - props.startedAt);
    }, 250);
    return () => {
      clearInterval(timer);
    };
  }, [props.startedAt]);
  return (
    <section className="panel" aria-busy="true">
      <h2 className="panel__title">Analiza w toku…</h2>
      <p className="muted break">{props.fileName}</p>
      <div className="spinner" aria-hidden="true" />
      <p>
        Czas: <span className="tabular">{formatSeconds(elapsed)}</span>. Model AI czyta tekst i
        wyodrębnia dane; zwykle trwa to kilkanaście sekund.
      </p>
      <button type="button" className="button" onClick={props.onCancel}>
        Anuluj analizę
      </button>
    </section>
  );
}

export function ErrorPanel(props: {
  message: UserMessage;
  onRetry: (() => void) | null;
  onReset: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), [props.message]);
  return (
    <section className="panel panel--error" role="alert" aria-labelledby="error-title">
      <h2 id="error-title" ref={headingRef} tabIndex={-1} className="panel__title">
        {props.message.title}
      </h2>
      <p>{props.message.detail}</p>
      <div className="actions">
        {props.onRetry && (
          <button type="button" className="button button--primary" onClick={props.onRetry}>
            Spróbuj ponownie
          </button>
        )}
        <button type="button" className="button" onClick={props.onReset}>
          Wybierz inny plik
        </button>
      </div>
    </section>
  );
}
