// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { HISTORY_KEY } from './lib/history';
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
});
