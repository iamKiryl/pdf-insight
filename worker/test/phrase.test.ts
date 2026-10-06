/** The literal whole-phrase search used for person names equals the previous regex check. */
import { describe, expect, it } from 'vitest';
import { containsWholePhrase } from '../src/compact';
import { W, escapeRegExp } from '../src/text';

const viaRegex = (text: string, phrase: string) =>
  new RegExp(`(?<![${W}])${escapeRegExp(phrase)}(?![${W}])`, 'u').test(text);

describe('containsWholePhrase', () => {
  const texts = [
    'jan kowalski, prezes. zofia nowak.',
    'jana kowalskiego — członka zarządu',
    'kowalski1 jan kowalskiego jan kowalski',
    '_jan kowalski',
    'jan kowalskiż',
    'ąjan kowalski ',
    '𝒜jan kowalski',
    'jan kowalski𝒜',
    '(jan kowalski)',
    'jan kowalskijan kowalski',
    '',
  ];
  const phrases = ['jan kowalski', 'kowalski', 'jan', 'zofia nowak', 'kowal', 'a.b (c)'];
  it.each(texts.flatMap((t) => phrases.map((p) => [t, p] as const)))('%j / %j', (text, phrase) => {
    expect(containsWholePhrase(text, phrase)).toBe(viaRegex(text, phrase));
  });
});
