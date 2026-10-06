import { useState, useSyncExternalStore } from 'react';
import {
  browserStorage,
  clearHistory,
  createEntry,
  loadHistory,
  saveHistory,
  type HistoryEntry,
  type HistoryStatus,
  type HistoryStorage,
} from './history';
import type { AnalysisResult } from './schema';

export interface HistoryState {
  entries: HistoryEntry[];
  status: HistoryStatus;
  skipped: number;
}

/** Owns the stored list; every change is written first, then published to subscribers. */
class HistoryStore {
  private state: HistoryState;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly storage: HistoryStorage | null) {
    this.state = loadHistory(storage);
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = () => this.state;

  private publish(next: HistoryState) {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  private write(entries: HistoryEntry[]) {
    const outcome = saveHistory(this.storage, entries);
    if (outcome.status === 'unavailable' && this.storage) {
      // Nothing could be written: keep showing what is actually stored.
      this.publish({ ...this.state, status: 'failed' });
      return;
    }
    this.publish({ ...this.state, entries: outcome.entries, status: outcome.status });
  }

  add = (result: AnalysisResult, meta: { fileBytes: number; durationMs: number }) => {
    this.write([createEntry(result, meta), ...this.state.entries]);
  };

  remove = (id: string) => {
    this.write(this.state.entries.filter((entry) => entry.id !== id));
  };

  clear = () => {
    const status = clearHistory(this.storage);
    if (status !== 'ok' && this.storage) {
      this.publish({ ...this.state, status: 'failed' });
      return;
    }
    this.publish({ entries: [], status, skipped: 0 });
  };
}

/** undefined = the browser's localStorage; null = no storage (history unavailable). */
export type HistoryStorageOption = HistoryStorage | null;

/** Local history; storage problems are reported, never thrown into the analysis flow. */
export function useHistory(storage?: HistoryStorageOption) {
  const [store] = useState(
    () => new HistoryStore(storage === undefined ? browserStorage() : storage),
  );
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return { ...state, add: store.add, remove: store.remove, clear: store.clear };
}
