import { describe, expect, it } from 'vitest';
import { loadJson } from '../test/fixtures';
import { countSentences, sentenceCountWithin } from './sentences';

interface Case {
  text: string;
  min: number;
  max: number;
  valid: boolean;
}

const { cases } = loadJson('sentences.json') as { cases: Case[] };

describe('countSentences (shared cases with backend)', () => {
  it.each(cases.map((c) => [c.text.slice(0, 40), c] as const))('%s', (_label, c) => {
    expect(countSentences(c.text)).toEqual({ min: c.min, max: c.max, valid: c.valid });
  });

  it('accepts an interval overlapping 3-5 and rejects others', () => {
    expect(sentenceCountWithin('A jest. B jest. C jest.', 3, 5)).toBe(true);
    expect(sentenceCountWithin('A jest. B jest.', 3, 5)).toBe(false);
    expect(sentenceCountWithin('A. B. C. D. E. F. G.', 3, 5)).toBe(true); // initials are ambiguous
    expect(sentenceCountWithin('Aa jest. Bb jest. Cc jest. Dd jest. Ee jest. Ff jest.', 3, 5)).toBe(
      false,
    );
  });
});
