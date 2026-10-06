// @vitest-environment jsdom
/**
 * Real browser entry point (browserStorage → useHistory → App) when localStorage is full or
 * blocked (docs/REVIEW_STABILITY.md). Storage.prototype is patched, not a fake injected.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { HISTORY_KEY, createEntry } from './lib/history';
import { AnalysisResultSchema } from './lib/schema';
import { acceptedResult } from './test/fixtures';

const result = AnalysisResultSchema.parse(acceptedResult());

function seed(...titles: string[]) {
  const entries = titles.map((title, i) =>
    createEntry(
      { ...result, document: { ...result.document, title } },
      { fileBytes: 2048, durationMs: 20_000 },
      new Date(Date.UTC(2026, 9, 6, 9, i)),
    ),
  );
  localStorage.setItem(HISTORY_KEY, JSON.stringify({ version: 1, entries }));
}

const quota = () => {
  throw new DOMException('The quota has been exceeded.', 'QuotaExceededError');
};
const denied = () => {
  throw new DOMException('The operation is insecure.', 'SecurityError');
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('history through the default browser storage', () => {
  it('full storage (probe fails with QuotaExceededError) keeps saved analyses readable', () => {
    seed('Umowa A', 'Umowa B');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(quota);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(<App />);

    expect(screen.queryByText(/Historia jest niedostępna/u)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz: Umowa A' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Umowa A' })).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Analizuj inny dokument' }));

    // clearing only removes the key, which works on a full storage
    fireEvent.click(screen.getByRole('button', { name: 'Wyczyść historię' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tak, usuń całą historię' }));
    expect(localStorage.getItem(HISTORY_KEY)).toBeNull();
    expect(screen.getByText('Brak zapisanych analiz.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
  });

  it('a deletion that cannot be written is reported and the entry stays listed', () => {
    seed('Umowa A', 'Umowa B');
    render(<App />);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(denied);
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(denied);

    fireEvent.click(screen.getByRole('button', { name: 'Usuń z historii: Umowa B' }));
    expect(screen.getByText('Umowa B')).toBeTruthy(); // not claimed as deleted
    expect(screen.getByText(/Nie udało się zapisać zmiany w historii/u)).toBeTruthy();
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '') as { entries: unknown[] };
    expect(stored.entries).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Wyczyść historię' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tak, usuń całą historię' }));
    expect(screen.getByText('Umowa A')).toBeTruthy(); // clear failed: still listed
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
  });

  it('blocked storage (SecurityError on access) is unavailable, analysis still offered', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(denied);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(denied);
    render(<App />);
    expect(screen.getByText(/Historia jest niedostępna/u)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Wybierz plik PDF' })).toBeTruthy();
  });
});
