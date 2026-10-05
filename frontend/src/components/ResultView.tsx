import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { downloadFileName, downloadJson, serializeResult } from '../lib/download';
import { formatAmount, formatDate, formatSeconds, languageName } from '../lib/format';
import { DOCUMENT_TYPE_LABELS } from '../lib/messages';
import type { AnalysisResult } from '../lib/schema';
import { PartialWarning } from './PartialWarning';

interface Props {
  result: AnalysisResult;
  durationMs: number;
  onReset: () => void;
}

export function ResultView({ result, durationMs, onReset }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const json = useMemo(() => serializeResult(result), [result]);
  const { document: doc, analysis } = result;
  useEffect(() => headingRef.current?.focus(), [result]);

  return (
    <article className="result" lang={doc.language} aria-labelledby="result-title">
      <header className="panel">
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
        </p>
        {analysis && !analysis.complete && (
          <div lang="pl">
            <PartialWarning pages={analysis.pagesWithoutText} total={doc.pages} />
          </div>
        )}
      </header>

      <Section title="Podsumowanie">
        <p className="summary">{result.summary}</p>
      </Section>

      <Section title="Kluczowe punkty">
        <ul className="list">
          {result.keyPoints.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Section>

      <div className="grid">
        <Section title="Organizacje">
          <TextList items={result.entities.organizations} />
        </Section>
        <Section title="Osoby">
          <TextList items={result.entities.people} />
        </Section>
      </div>

      <Section title="Kwoty">
        {result.amounts.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Kwoty wymienione w dokumencie</caption>
              <thead lang="pl">
                <tr>
                  <th scope="col">Kwota</th>
                  <th scope="col">Kontekst</th>
                </tr>
              </thead>
              <tbody>
                {result.amounts.map((amount, index) => (
                  <tr key={`${String(index)}-${amount.context}`}>
                    <td className="nowrap tabular">
                      {formatAmount(amount.value, amount.currency)}
                    </td>
                    <td>{amount.context}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Daty">
        {result.dates.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Daty wymienione w dokumencie</caption>
              <thead lang="pl">
                <tr>
                  <th scope="col">Data</th>
                  <th scope="col">Kontekst</th>
                </tr>
              </thead>
              <tbody>
                {result.dates.map((date, index) => (
                  <tr key={`${String(index)}-${date.date}`}>
                    <td className="nowrap">
                      <time dateTime={date.date}>{formatDate(date.date)}</time>
                    </td>
                    <td>{date.context}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Słowa kluczowe">
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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h3 className="section__title" lang="pl">
        {title}
      </h3>
      {children}
    </section>
  );
}

function TextList({ items }: { items: readonly string[] }) {
  if (items.length === 0) return <Empty />;
  return (
    <ul className="list">
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
