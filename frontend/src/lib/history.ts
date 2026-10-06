import { z } from 'zod';
import { AnalysisResultSchema, type AnalysisResult } from './schema';

/**
 * Local analysis history (F-09). Only validated analysis results and file metadata are stored —
 * never the PDF or its extracted text. Everything lives in this browser's localStorage; storage
 * that is unavailable, full or corrupted never breaks a new analysis.
 */
export const HISTORY_KEY = 'pdf-insight.history.v1';
export const HISTORY_LIMITS = {
  maxEntries: 10,
  /** Serialized size bound (UTF-16 code units, as localStorage counts them). */
  maxChars: 1_000_000,
} as const;

const EntrySchema = z.strictObject({
  id: z.string().min(1).max(64),
  savedAt: z.iso.datetime(),
  fileBytes: z.number().int().nonnegative(),
  durationMs: z.number().nonnegative(),
  result: AnalysisResultSchema,
});
const StoredSchema = z.strictObject({ version: z.literal(1), entries: z.array(z.unknown()) });

export type HistoryEntry = z.infer<typeof EntrySchema>;
export type HistoryStatus = 'ok' | 'unavailable' | 'full';

/** The subset of the Web Storage API used here (tests pass in-memory fakes). */
export type HistoryStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export interface LoadedHistory {
  entries: HistoryEntry[];
  /** Stored entries skipped because they were corrupted, invalid or from an older format. */
  skipped: number;
  status: HistoryStatus;
}

/** localStorage if it can actually be written (private modes may expose a throwing object). */
export function browserStorage(): HistoryStorage | null {
  try {
    const storage = window.localStorage;
    const probe = `${HISTORY_KEY}.probe`;
    storage.setItem(probe, '1');
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}

function newest(entries: HistoryEntry[]): HistoryEntry[] {
  return [...entries].sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

export function loadHistory(storage: HistoryStorage | null): LoadedHistory {
  if (!storage) return { entries: [], skipped: 0, status: 'unavailable' };
  let raw: string | null;
  try {
    raw = storage.getItem(HISTORY_KEY);
  } catch {
    return { entries: [], skipped: 0, status: 'unavailable' };
  }
  if (raw === null) return { entries: [], skipped: 0, status: 'ok' };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { entries: [], skipped: 1, status: 'ok' };
  }
  const stored = StoredSchema.safeParse(parsed);
  if (!stored.success) return { entries: [], skipped: 1, status: 'ok' };
  const valid: HistoryEntry[] = [];
  for (const item of stored.data.entries) {
    const entry = EntrySchema.safeParse(item);
    if (entry.success) valid.push(entry.data);
  }
  const entries = newest(valid).slice(0, HISTORY_LIMITS.maxEntries);
  return { entries, skipped: stored.data.entries.length - entries.length, status: 'ok' };
}

function serialize(entries: HistoryEntry[]): string {
  return JSON.stringify({ version: 1, entries });
}

/** Newest first, at most maxEntries; an entry that alone exceeds the size bound is never kept,
 * then the oldest are dropped until the serialized list fits. */
export function boundEntries(entries: HistoryEntry[]): HistoryEntry[] {
  const fitting = entries.filter((entry) => serialize([entry]).length <= HISTORY_LIMITS.maxChars);
  const kept = newest(fitting).slice(0, HISTORY_LIMITS.maxEntries);
  while (kept.length > 0 && serialize(kept).length > HISTORY_LIMITS.maxChars) kept.pop();
  return kept;
}

export interface SaveOutcome {
  entries: HistoryEntry[];
  status: HistoryStatus;
}

/** Writes the bounded list; on a quota error drops the oldest entries until it fits. */
export function saveHistory(storage: HistoryStorage | null, entries: HistoryEntry[]): SaveOutcome {
  if (!storage) return { entries: [], status: 'unavailable' };
  let kept = boundEntries(entries);
  let trimmed = kept.length < entries.length;
  for (;;) {
    try {
      if (kept.length === 0) storage.removeItem(HISTORY_KEY);
      else storage.setItem(HISTORY_KEY, serialize(kept));
      return { entries: kept, status: trimmed ? 'full' : 'ok' };
    } catch {
      if (kept.length === 0) return { entries: [], status: 'unavailable' };
      kept = kept.slice(0, -1);
      trimmed = true;
    }
  }
}

export function clearHistory(storage: HistoryStorage | null): HistoryStatus {
  if (!storage) return 'unavailable';
  try {
    storage.removeItem(HISTORY_KEY);
    return 'ok';
  } catch {
    return 'unavailable';
  }
}

function newId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${String(Date.now())}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

/** A history entry from a validated result and file metadata — nothing else can be stored. */
export function createEntry(
  result: AnalysisResult,
  meta: { fileBytes: number; durationMs: number },
  now: Date = new Date(),
): HistoryEntry {
  return {
    id: newId(),
    savedAt: now.toISOString(),
    fileBytes: Math.max(0, Math.round(meta.fileBytes)),
    durationMs: Math.max(0, meta.durationMs),
    result,
  };
}
