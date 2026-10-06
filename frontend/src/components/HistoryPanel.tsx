import { useState } from 'react';
import { formatDate, formatSavedAt } from '../lib/format';
import type { HistoryEntry, HistoryStatus } from '../lib/history';
import { DOCUMENT_TYPE_LABELS } from '../lib/messages';

interface Props {
  entries: readonly HistoryEntry[];
  status: HistoryStatus;
  skipped: number;
  onOpen: (entry: HistoryEntry) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

export function HistoryPanel({ entries, status, skipped, onOpen, onRemove, onClear }: Props) {
  const [confirming, setConfirming] = useState(false);
  return (
    <section className="panel history" aria-labelledby="history-title">
      <p className="label label--accent">Historia · to urządzenie</p>
      <h2 id="history-title" className="panel__title">
        Ostatnie analizy
      </h2>
      <p className="muted history__notice">
        Historia jest zapisana tylko w tej przeglądarce na tym urządzeniu i może zawierać dane z
        dokumentów (podsumowania, kwoty, cytaty). Pliki PDF ani ich pełny tekst nie są zapisywane.
        Otwarcie wpisu nie wysyła niczego do AI.
      </p>

      {status === 'unavailable' && (
        <p className="history__status" role="status">
          Historia jest niedostępna w tej przeglądarce (np. tryb prywatny lub zablokowany zapis).
          Analiza działa bez niej.
        </p>
      )}
      {status === 'full' && (
        <p className="history__status" role="status">
          Za mało miejsca: nie wszystkie wyniki zmieściły się w historii (pominięto najstarsze lub
          zbyt duże wpisy).
        </p>
      )}
      {skipped > 0 && (
        <p className="history__status" role="status">
          Pominięto uszkodzone lub nieaktualne wpisy: {skipped}.
        </p>
      )}

      {status !== 'unavailable' && entries.length === 0 && (
        <p className="muted">Brak zapisanych analiz.</p>
      )}

      {entries.length > 0 && (
        <>
          <ol className="history__list">
            {entries.map((entry) => {
              const doc = entry.result.document;
              return (
                <li key={entry.id} className="history__item">
                  <div className="history__text">
                    <span className="history__title">{doc.title}</span>
                    <span className="history__meta">
                      {DOCUMENT_TYPE_LABELS[doc.type]} · {doc.fileName}
                      {doc.date ? ` · ${formatDate(doc.date)}` : ''}
                    </span>
                    <span className="label">
                      Zapisano <time dateTime={entry.savedAt}>{formatSavedAt(entry.savedAt)}</time>
                    </span>
                  </div>
                  <div className="history__actions">
                    <button
                      type="button"
                      className="button"
                      aria-label={`Otwórz: ${doc.title}`}
                      onClick={() => {
                        onOpen(entry);
                      }}
                    >
                      Otwórz
                    </button>
                    <button
                      type="button"
                      className="button button--quiet"
                      aria-label={`Usuń z historii: ${doc.title}`}
                      onClick={() => {
                        onRemove(entry.id);
                      }}
                    >
                      Usuń
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="actions">
            {confirming ? (
              <>
                <button
                  type="button"
                  className="button button--danger"
                  onClick={() => {
                    setConfirming(false);
                    onClear();
                  }}
                >
                  Tak, usuń całą historię
                </button>
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setConfirming(false);
                  }}
                >
                  Anuluj
                </button>
              </>
            ) : (
              <button
                type="button"
                className="button button--quiet"
                onClick={() => {
                  setConfirming(true);
                }}
              >
                Wyczyść historię
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
