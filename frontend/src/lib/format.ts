const languageNames = new Intl.DisplayNames(['pl'], { type: 'language' });

export function languageName(code: string): string {
  try {
    return languageNames.of(code) ?? code;
  } catch {
    return code;
  }
}

export function formatAmount(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat('pl-PL', { style: 'currency', currency }).format(value);
  } catch {
    return `${value.toLocaleString('pl-PL')} ${currency}`;
  }
}

/** ISO date rendered as a Polish calendar date, evaluated in UTC so it never shifts by a day. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number) as [number, number, number];
  return new Intl.DateTimeFormat('pl-PL', { dateStyle: 'long', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, month - 1, day)),
  );
}

export function formatPageList(pages: readonly number[]): string {
  if (pages.length <= 1) return pages.join('');
  return `${pages.slice(0, -1).join(', ')} i ${String(pages.at(-1))}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} MB`;
}

export function formatSeconds(ms: number): string {
  return `${(ms / 1000).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} s`;
}
