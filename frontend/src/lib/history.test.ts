import { describe, expect, it } from 'vitest';
import { acceptedResult } from '../test/fixtures';
import {
  HISTORY_KEY,
  HISTORY_LIMITS,
  boundEntries,
  clearHistory,
  createEntry,
  loadHistory,
  saveHistory,
  type HistoryEntry,
  type HistoryStorage,
} from './history';
import { AnalysisResultSchema, type AnalysisResult } from './schema';

/** In-memory Storage; optional quota in characters throws like a full browser storage. */
class MemoryStorage implements HistoryStorage {
  data = new Map<string, string>();
  constructor(private readonly quota = Infinity) {}
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    if (value.length > this.quota) throw new DOMException('full', 'QuotaExceededError');
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

const throwing: HistoryStorage = {
  getItem: () => {
    throw new DOMException('denied', 'SecurityError');
  },
  setItem: () => {
    throw new DOMException('denied', 'SecurityError');
  },
  removeItem: () => {
    throw new DOMException('denied', 'SecurityError');
  },
};

const result = AnalysisResultSchema.parse(acceptedResult());

function entry(index: number, overrides: Partial<AnalysisResult> = {}): HistoryEntry {
  const titled = { ...result, ...overrides };
  titled.document = { ...result.document, title: `Dokument ${String(index)}` };
  return createEntry(
    titled,
    { fileBytes: 1000 + index, durationMs: 1500 },
    new Date(Date.UTC(2026, 9, 6, 8, index)),
  );
}

describe('local history storage', () => {
  it('round-trips validated entries, newest first, with result and file metadata only', () => {
    const storage = new MemoryStorage();
    const saved = saveHistory(storage, [entry(1), entry(3), entry(2)]);
    expect(saved.status).toBe('ok');
    const loaded = loadHistory(storage);
    expect(loaded.entries.map((e) => e.result.document.title)).toEqual([
      'Dokument 3',
      'Dokument 2',
      'Dokument 1',
    ]);
    expect(loaded.skipped).toBe(0);
    const stored = JSON.parse(storage.getItem(HISTORY_KEY) ?? '') as { entries: object[] };
    expect(Object.keys(stored.entries[0] ?? {}).sort()).toEqual([
      'durationMs',
      'fileBytes',
      'id',
      'result',
      'savedAt',
    ]);
  });

  it('keeps at most ten entries, dropping the oldest', () => {
    const storage = new MemoryStorage();
    const many = Array.from({ length: 12 }, (_, i) => entry(i));
    const saved = saveHistory(storage, many);
    expect(saved.entries).toHaveLength(HISTORY_LIMITS.maxEntries);
    expect(saved.entries.at(-1)?.result.document.title).toBe('Dokument 2');
    expect(loadHistory(storage).entries).toHaveLength(10);
  });

  it('enforces the serialized size bound and never stores an oversize entry', () => {
    const amounts = Array.from({ length: 4000 }, () => ({
      value: 1,
      currency: 'PLN',
      context: 'x'.repeat(400),
    }));
    const huge = entry(9, { amounts }); // ~1.7 million characters
    expect(boundEntries([huge])).toEqual([]);
    const kept = boundEntries([huge, entry(1)]);
    expect(kept.map((e) => e.result.document.title)).toEqual(['Dokument 1']);
  });

  it('skips corrupted JSON, an old format and invalid entries without failing', () => {
    const storage = new MemoryStorage();
    storage.setItem(HISTORY_KEY, '{not json');
    expect(loadHistory(storage)).toEqual({ entries: [], skipped: 1, status: 'ok' });

    storage.setItem(HISTORY_KEY, JSON.stringify([{ result }]));
    expect(loadHistory(storage)).toEqual({ entries: [], skipped: 1, status: 'ok' });

    const bad = { ...entry(1), result: { ...result, summary: 'Za krótko.' } };
    const injected = { ...entry(2), extra: '<img src=x>' };
    storage.setItem(
      HISTORY_KEY,
      JSON.stringify({ version: 1, entries: [bad, entry(3), injected, 'x'] }),
    );
    const loaded = loadHistory(storage);
    expect(loaded.entries.map((e) => e.result.document.title)).toEqual(['Dokument 3']);
    expect(loaded.skipped).toBe(3);
  });

  it('reports unavailable storage instead of throwing', () => {
    expect(loadHistory(null).status).toBe('unavailable');
    expect(loadHistory(throwing)).toEqual({ entries: [], skipped: 0, status: 'unavailable' });
    expect(saveHistory(throwing, [entry(1)])).toEqual({ entries: [], status: 'unavailable' });
    expect(clearHistory(throwing)).toBe('unavailable');
  });

  it('drops the oldest entries when the browser quota is exceeded', () => {
    const one = JSON.stringify({ version: 1, entries: [entry(5)] }).length;
    const storage = new MemoryStorage(one * 2 + 50); // room for about two entries
    const saved = saveHistory(storage, [entry(1), entry(2), entry(3), entry(4), entry(5)]);
    expect(saved.status).toBe('full');
    expect(saved.entries.map((e) => e.result.document.title)).toEqual(['Dokument 5', 'Dokument 4']);
    expect(loadHistory(storage).entries).toHaveLength(2);
  });

  it('never removes stored history when not even one entry can be written', () => {
    const storage = new MemoryStorage();
    saveHistory(storage, [entry(1), entry(2)]);
    const before = storage.getItem(HISTORY_KEY);
    storage.setItem = () => {
      throw new DOMException('full', 'QuotaExceededError');
    };
    expect(saveHistory(storage, [entry(3), entry(1), entry(2)])).toEqual({
      entries: [],
      status: 'unavailable',
    });
    expect(storage.getItem(HISTORY_KEY)).toBe(before);
  });

  it('clears the stored history', () => {
    const storage = new MemoryStorage();
    saveHistory(storage, [entry(1)]);
    expect(clearHistory(storage)).toBe('ok');
    expect(storage.getItem(HISTORY_KEY)).toBeNull();
    expect(saveHistory(storage, []).entries).toEqual([]);
  });
});
