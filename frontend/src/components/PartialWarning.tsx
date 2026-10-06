import { formatPageList } from '../lib/format';

interface Props {
  pages: readonly number[];
  total: number;
  /** Shown before analysis (warning) or on the result (incomplete analysis). */
  before?: boolean;
}

export function PartialWarning({ pages, total, before = false }: Props) {
  const label = pages.length === 1 ? 'Strona' : 'Strony';
  const verb = pages.length === 1 ? 'nie zawiera' : 'nie zawierają';
  return (
    <div className="warning" role="note">
      <span className="warning__symbol" aria-hidden="true">
        ⚠
      </span>
      <strong>{before ? 'Analiza będzie częściowa.' : 'Analiza częściowa.'}</strong> {label}{' '}
      {formatPageList(pages)} (z {total}) {verb} tekstu — prawdopodobnie to skany lub obrazy. Bez
      OCR ich treść nie {before ? 'zostanie' : 'została'} przeanalizowana, więc wynik może pomijać
      istotne informacje (np. aneksy).
    </div>
  );
}
