// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { HISTORY_KEY, createEntry, type HistoryStorage } from './lib/history';
import { AnalysisResultSchema } from './lib/schema';
import { acceptedResult } from './test/fixtures';

const result = AnalysisResultSchema.parse(acceptedResult());

function stored(...titles: string[]) {
  const entries = titles.map((title, i) =>
    createEntry(
      { ...result, document: { ...result.document, title } },
      { fileBytes: 2048, durationMs: 21_000 },
      new Date(Date.UTC(2026, 9, 6, 9, i)),
    ),
  );
  localStorage.setItem(HISTORY_KEY, JSON.stringify({ version: 1, entries }));
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('App with local history', () => {
  it('reopens a saved result in the result view without any request', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    stored('Umowa A', 'Umowa B');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz: Umowa A' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Umowa A' })).toBeTruthy();
    expect(screen.getByText(/otwarto z historii, bez ponownej analizy/u)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Pobierz JSON' })).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Analizuj inny dokument' }));
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
  });

  it('deletes one entry and clears all after confirmation', () => {
    stored('Umowa A', 'Umowa B', 'Umowa C');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Usuń z historii: Umowa B' }));
    expect(screen.queryByText('Umowa B')).toBeNull();
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '') as { entries: unknown[] };
    expect(saved.entries).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Wyczyść historię' }));
    expect(localStorage.getItem(HISTORY_KEY)).not.toBeNull(); // nothing removed before confirming
    fireEvent.click(screen.getByRole('button', { name: 'Tak, usuń całą historię' }));
    expect(localStorage.getItem(HISTORY_KEY)).toBeNull();
    expect(screen.getByText('Brak zapisanych analiz.')).toBeTruthy();
  });

  it('keeps the upload usable with corrupted history and reports skipped entries', () => {
    localStorage.setItem(HISTORY_KEY, '{broken');
    render(<App />);
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
    expect(screen.getByText(/Pominięto uszkodzone lub nieaktualne wpisy: 1/u)).toBeTruthy();
  });

  it('works without storage and says history is unavailable', () => {
    const blocked: HistoryStorage = {
      getItem: () => {
        throw new DOMException('denied', 'SecurityError');
      },
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    render(<App historyStorage={blocked} />);
    const panel = screen.getByRole('region', { name: 'Ostatnie analizy' });
    expect(within(panel).getByText(/Historia jest niedostępna/u)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
  });
});
