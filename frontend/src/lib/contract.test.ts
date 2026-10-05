import { describe, expect, it } from 'vitest';
import { loadJson } from '../test/fixtures';
import { CURRENCIES, LANGUAGES, LIMITS, countLetters, hasLetter } from './contract';

describe('shared contract data', () => {
  it('uses contracts/codes.json and limits.json', () => {
    const codes = loadJson('../codes.json') as { languages: string[]; currencies: string[] };
    expect([...LANGUAGES].sort()).toEqual([...codes.languages].sort());
    expect([...CURRENCIES].sort()).toEqual([...codes.currencies].sort());
    const limits = loadJson('../limits.json') as Record<string, unknown>;
    expect(LIMITS.maxTotalChars).toBe(limits.maxTotalChars);
    expect(LIMITS.maxFileBytes).toBe(10 * 1024 * 1024);
    expect(CURRENCIES.has('XXX')).toBe(false);
  });

  it('detects text by Unicode letters, like the backend', () => {
    expect(hasLetter('  12  ')).toBe(false);
    expect(hasLetter('— 11 —')).toBe(false);
    expect(hasLetter('Źródło')).toBe(true);
    expect(countLetters('Ąb 1 ć!')).toBe(3);
  });
});
