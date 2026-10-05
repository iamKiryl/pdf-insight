import { describe, expect, it } from 'vitest';
import { itemsToText, type PositionedItem } from './textLayout';

const item = (str: string, x: number, y: number, width: number, height = 10): PositionedItem => ({
  str,
  x,
  y,
  width,
  height,
  hasEOL: false,
});

describe('itemsToText', () => {
  it('orders lines top-to-bottom and items left-to-right', () => {
    const text = itemsToText([
      item('drugi', 0, 80, 30),
      item('pierwszy', 0, 100, 40),
      item('wiersz', 45, 100, 30),
    ]);
    expect(text).toBe('pierwszy wiersz\ndrugi');
  });

  it('does not insert spaces inside words split into touching runs', () => {
    const text = itemsToText([
      item('Wynagrodze', 0, 100, 50),
      item('nie', 50.5, 100, 15),
      item('zł', 70, 100, 10),
    ]);
    expect(text).toBe('Wynagrodzenie zł');
  });

  it('keeps table cells on the same row separated', () => {
    const text = itemsToText([item('Netto', 0, 50, 25), item('184 500,00 PLN', 200, 50.8, 70)]);
    expect(text).toBe('Netto 184 500,00 PLN');
  });

  it('normalizes decomposed Polish diacritics to NFC', () => {
    const decomposed = 'żółw';
    expect(itemsToText([item(decomposed, 0, 10, 20)])).toBe('żółw');
  });

  it('returns an empty string for pages without text items', () => {
    expect(itemsToText([item('', 0, 0, 0), item('   ', 0, 0, 5)])).toBe('');
  });
});
