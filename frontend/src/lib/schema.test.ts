import { describe, expect, it } from 'vitest';
import { acceptedResult, loadFixtures } from '../test/fixtures';
import { AnalysisResultSchema } from './schema';

const accepted = loadFixtures('accepted');
const rejected = loadFixtures('rejected');

describe('AnalysisResultSchema (shared contract fixtures)', () => {
  it('has fixtures to check', () => {
    expect(accepted.length).toBeGreaterThanOrEqual(3);
    expect(rejected.length).toBeGreaterThanOrEqual(20);
  });

  it.each(accepted.map((f) => [f.name, f] as const))('accepts %s', (_name, fixture) => {
    const parsed = AnalysisResultSchema.safeParse(fixture.data);
    expect(parsed.error?.issues ?? []).toEqual([]);
  });

  it.each(rejected.map((f) => [f.name, f] as const))('rejects %s', (_name, fixture) => {
    expect(AnalysisResultSchema.safeParse(fixture.data).success).toBe(false);
  });
});

describe('AnalysisResultSchema edge cases', () => {
  it('rejects non-finite amounts', () => {
    for (const value of [Number.NaN, Number.POSITIVE_INFINITY]) {
      const data = acceptedResult();
      (data.amounts as { value: number }[])[0]!.value = value;
      expect(AnalysisResultSchema.safeParse(data).success).toBe(false);
    }
  });

  it('allows null main date but not a missing key', () => {
    const withNull = acceptedResult();
    (withNull.document as Record<string, unknown>).date = null;
    expect(AnalysisResultSchema.safeParse(withNull).success).toBe(true);
  });

  it('accepts boundary counts of key points (3 and 7) and rejects 2 and 8', () => {
    const counts = { 2: false, 3: true, 7: true, 8: false } as const;
    for (const [count, ok] of Object.entries(counts)) {
      const data = acceptedResult();
      data.keyPoints = Array.from({ length: Number(count) }, (_, i) => `Punkt ${String(i + 1)}.`);
      expect(AnalysisResultSchema.safeParse(data).success).toBe(ok);
    }
  });

  it('accepts empty collections', () => {
    const data = acceptedResult();
    data.amounts = [];
    data.dates = [];
    data.keywords = [];
    data.entities = { organizations: [], people: [] };
    expect(AnalysisResultSchema.safeParse(data).success).toBe(true);
  });

  it('rejects unknown nested keys', () => {
    const data = acceptedResult();
    (data.document as Record<string, unknown>).confidence = 1;
    expect(AnalysisResultSchema.safeParse(data).success).toBe(false);
  });
});
