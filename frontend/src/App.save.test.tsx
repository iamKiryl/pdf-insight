// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { HISTORY_KEY, createEntry } from './lib/history';
import { AnalysisResultSchema } from './lib/schema';
import { acceptedResult } from './test/fixtures';

const SOURCE_MARKER = 'TEKST-ŹRÓDŁOWY-NIE-ZAPISYWAĆ';
const text = `${SOURCE_MARKER} Umowa została zawarta pomiędzy stronami w Warszawie. `.repeat(8);

vi.mock('./lib/pdf', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/pdf')>()),
  extractPdf: () =>
    Promise.resolve({
      fileName: 'umowa.pdf',
      fileBytes: 4321,
      pageCount: 1,
      pages: [{ page: 1, text }],
      pagesWithoutText: [],
    }),
}));

const result = AnalysisResultSchema.parse({
  ...acceptedResult(),
  analysis: { complete: true, pagesWithoutText: [], titleFallback: false },
});
vi.mock('./api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/client')>()),
  analyzeDocument: () => Promise.resolve(result),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('saving a finished analysis', () => {
  it('stores the validated result and file metadata once, never the extracted text', async () => {
    render(<App />);
    const pdf = new File(['%PDF-1.7'], 'umowa.pdf', { type: 'application/pdf' });
    fireEvent.drop(screen.getByRole('region', { name: 'Przeciągnij plik PDF tutaj' }), {
      dataTransfer: { files: [pdf] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Analizuj z AI' }));
    await screen.findByText(/zapisano w historii na tym urządzeniu/u);

    const raw = localStorage.getItem(HISTORY_KEY) ?? '';
    const saved = JSON.parse(raw) as { entries: { fileBytes: number }[] };
    expect(saved.entries).toHaveLength(1);
    expect(saved.entries[0]?.fileBytes).toBe(4321);
    expect(raw).not.toContain(SOURCE_MARKER);
  });

  it('with full storage a new analysis still renders and the saved entry is kept', async () => {
    const old = createEntry(
      { ...result, document: { ...result.document, title: 'Stara umowa' } },
      { fileBytes: 100, durationMs: 1000 },
      new Date(Date.UTC(2026, 9, 5)),
    );
    localStorage.setItem(HISTORY_KEY, JSON.stringify({ version: 1, entries: [old] }));
    const before = localStorage.getItem(HISTORY_KEY);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    render(<App />);
    expect(screen.getByText('Stara umowa')).toBeTruthy();
    const pdf = new File(['%PDF-1.7'], 'umowa.pdf', { type: 'application/pdf' });
    fireEvent.drop(screen.getByRole('region', { name: 'Przeciągnij plik PDF tutaj' }), {
      dataTransfer: { files: [pdf] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Analizuj z AI' }));
    expect(
      await screen.findByRole('heading', { level: 2, name: result.document.title }),
    ).toBeTruthy();
    expect(screen.queryByText(/zapisano w historii na tym urządzeniu/u)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Analizuj inny dokument' }));
    expect(screen.getByText('Stara umowa')).toBeTruthy();
    expect(screen.getByText(/Nie udało się zapisać zmiany w historii/u)).toBeTruthy();
    expect(localStorage.getItem(HISTORY_KEY)).toBe(before);
  });
});
