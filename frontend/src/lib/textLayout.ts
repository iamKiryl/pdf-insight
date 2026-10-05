/**
 * Rebuilds reading-order text from positioned PDF text items (pure, unit-tested).
 *
 * Items are grouped into lines by their baseline (y), sorted top-to-bottom and left-to-right,
 * and a space is inserted only when there is a visible horizontal gap. This avoids the spurious
 * spaces pdf.js runs can produce inside words (e.g. around Polish diacritics). Multi-column layouts
 * are read row by row, which suits tables but may interleave true text columns.
 */

export interface PositionedItem {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
  hasEOL: boolean;
}

const LINE_TOLERANCE = 0.5; // fraction of glyph height
const SPACE_GAP = 0.18; // fraction of glyph height

export function itemsToText(items: readonly PositionedItem[]): string {
  const visible = items.filter((item) => item.str.length > 0);
  const sorted = [...visible].sort((a, b) => b.y - a.y || a.x - b.x);
  const lines: PositionedItem[][] = [];
  for (const item of sorted) {
    const line = lines.at(-1);
    const anchor = line?.[0];
    const tolerance = Math.max(item.height, anchor?.height ?? 0, 1) * LINE_TOLERANCE;
    if (line && anchor && Math.abs(anchor.y - item.y) <= tolerance) line.push(item);
    else lines.push([item]);
  }
  const text = lines
    .map((line) => joinLine([...line].sort((a, b) => a.x - b.x)))
    .map((line) => line.replace(/[ \t\u00a0]+/gu, ' ').trim())
    .filter((line) => line.length > 0)
    .join('\n');
  return text.normalize('NFC');
}

function joinLine(line: readonly PositionedItem[]): string {
  let result = '';
  let previous: PositionedItem | undefined;
  for (const item of line) {
    if (previous) {
      const gap = item.x - (previous.x + previous.width);
      const height = Math.max(item.height, previous.height, 1);
      const alreadySpaced = /\s$/u.test(result) || /^\s/u.test(item.str);
      if (!alreadySpaced && gap > height * SPACE_GAP) result += ' ';
    }
    result += item.str;
    previous = item;
  }
  return result;
}
