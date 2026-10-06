import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { downloadFileName, downloadJson, serializeResult } from '../lib/download';
import {
  formatAmount,
  formatDate,
  formatSavedAt,
  formatSeconds,
  languageName,
} from '../lib/format';
import { DOCUMENT_TYPE_LABELS } from '../lib/messages';
import type { AnalysisResult } from '../lib/schema';
import { PartialWarning } from './PartialWarning';

interface Props {
  result: AnalysisResult;
  durationMs: number;
  onReset: () => void;
  /** Set when the result was reopened from local history (no new AI request). */
  savedAt?: string;
  /** True when this fresh result was saved to local history. */
  savedToHistory?: boolean;
}

export function ResultView({ result, durationMs, onReset, savedAt, savedToHistory }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const json = useMemo(() => serializeResult(result), [result]);
  const { document: doc, analysis } = result;
  useEffect(() => headingRef.current?.focus(), [result]);

  return (
    <article className="result" lang={doc.language} aria-labelledby="result-title">
      <header className="panel panel--report">
        <p className="label label--accent" lang="pl">
          {savedAt ? (
            <>
              Historia · zapisano <time dateTime={savedAt}>{formatSavedAt(savedAt)}</time>
            </>
          ) : (
            '04 · Wynik analizy'
          )}
        </p>
        <p className="eyebrow" lang="pl">
          {DOCUMENT_TYPE_LABELS[doc.type]} · {languageName(doc.language)} · {doc.pages}{' '}
          {doc.pages === 1 ? 'strona' : 'str.'}
          {doc.date ? ` · ${formatDate(doc.date)}` : ''}
        </p>
        <h2 id="result-title" ref={headingRef} tabIndex={-1} className="result__title">
          {doc.title}
        </h2>
        <p className="muted break" lang="pl">
          {doc.fileName} · analiza: {formatSeconds(durationMs)}
          {analysis?.titleFallback ? ' · tytuł nie został znaleziony w dokumencie' : ''}
          {savedAt ? ' · otwarto z historii, bez ponownej analizy' : ''}
          {savedToHistory ? ' · zapisano w historii na tym urządzeniu' : ''}
        </p>
        {analysis && !analysis.complete && (
          <div lang="pl">
            <PartialWarning pages={analysis.pagesWithoutText} total={doc.pages} />
          </div>
        )}
      </header>

      <Section number="01" title="Podsumowanie">
        <p className="summary">{result.summary}</p>
      </Section>

      <Section number="02" title="Kluczowe punkty" count={result.keyPoints.length}>
        <ul className="list list--marked">
          {result.keyPoints.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Section>

      <div className="grid">
        <Section number="03" title="Organizacje" count={result.entities.organizations.length}>
          <TextList items={result.entities.organizations} />
        </Section>
        <Section number="04" title="Osoby" count={result.entities.people.length}>
          <TextList items={result.entities.people} />
        </Section>
      </div>

      <Section number="05" title="Kwoty" count={result.amounts.length}>
        {result.amounts.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-wrap">
            <table className="facts-table" role="table">
              <caption className="visually-hidden">Kwoty wymienione w dokumencie</caption>
              <thead lang="pl" role="rowgroup">
                <tr role="row">
                  <th scope="col" role="columnheader">
                    Kwota
                  </th>
                  <th scope="col" role="columnheader">
                    Kontekst
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {result.amounts.map((amount, index) => (
                  <tr role="row" key={`${String(index)}-${amount.context}`}>
                    <td role="cell" className="nowrap tabular value">
                      {formatAmount(amount.value, amount.currency)}
                    </td>
                    <td role="cell" className="context">
                      {amount.context}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section number="06" title="Daty" count={result.dates.length}>
        {result.dates.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-wrap">
            <table className="facts-table" role="table">
              <caption className="visually-hidden">Daty wymienione w dokumencie</caption>
              <thead lang="pl" role="rowgroup">
                <tr role="row">
                  <th scope="col" role="columnheader">
                    Data
                  </th>
                  <th scope="col" role="columnheader">
                    Kontekst
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {result.dates.map((date, index) => (
                  <tr role="row" key={`${String(index)}-${date.date}`}>
                    <td role="cell" className="nowrap tabular value">
                      <time dateTime={date.date}>{formatDate(date.date)}</time>
                    </td>
                    <td role="cell" className="context">
                      {date.context}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section number="07" title="Słowa kluczowe" count={result.keywords.length}>
        {result.keywords.length === 0 ? (
          <Empty />
        ) : (
          <ul className="chips">
            {result.keywords.map((keyword) => (
              <li key={keyword}>{keyword}</li>
            ))}
          </ul>
        )}
      </Section>

      <section className="panel" lang="pl" aria-labelledby="json-title">
        <h3 id="json-title" className="section__title">
          <span className="section__number" aria-hidden="true">
            08
          </span>
          Dane JSON
        </h3>
        <p className="muted">
          Plik do pobrania zawiera dokładnie ten sam JSON ({downloadFileName(doc.fileName)}).
        </p>
        <div className="actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => {
              downloadJson(result);
            }}
          >
            Pobierz JSON
          </button>
          <button type="button" className="button" onClick={onReset}>
            Analizuj inny dokument
          </button>
        </div>
        <details className="json">
          <summary>Pokaż JSON</summary>
          <pre tabIndex={0} aria-label="Podgląd JSON">
            <code>{json}</code>
          </pre>
        </details>
      </section>
    </article>
  );
}

function Section(props: { number: string; title: string; count?: number; children: ReactNode }) {
  return (
    <section className="panel">
      <h3 className="section__title" lang="pl">
        <span className="section__number" aria-hidden="true">
          {props.number}
        </span>
        {props.title}
        {props.count !== undefined && <span className="section__count"> ({props.count})</span>}
      </h3>
      {props.children}
    </section>
  );
}

function TextList({ items }: { items: readonly string[] }) {
  if (items.length === 0) return <Empty />;
  return (
    <ul className="list list--marked">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Empty() {
  return (
    <p className="muted" lang="pl">
      Brak w dokumencie.
    </p>
  );
}
