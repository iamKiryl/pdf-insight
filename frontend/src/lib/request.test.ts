import { describe, expect, it } from 'vitest';
import type { ExtractedDocument } from './pdf';
import { prepareRequest } from './request';

const sentence = 'Umowa ramowa została zawarta pomiędzy stronami w Warszawie. ';

function doc(pages: string[]): ExtractedDocument {
  return {
    fileName: 'umowa.pdf',
    fileBytes: 1000,
    pageCount: pages.length,
    pages: pages.map((text, i) => ({ page: i + 1, text })),
    pagesWithoutText: pages.flatMap((text, i) => (/\p{L}/u.test(text) ? [] : [i + 1])),
  };
}

describe('prepareRequest', () => {
  it('builds the request with page numbers and missing-text pages', () => {
    const ready = prepareRequest(doc([sentence.repeat(5), '', sentence.repeat(5)]));
    expect(ready.problem).toBeNull();
    expect(ready.request.pagesWithoutText).toEqual([2]);
    expect(ready.request.pages.map((p) => p.page)).toEqual([1, 2, 3]);
  });

  it('rejects a fully scanned document', () => {
    expect(prepareRequest(doc(['', '11'])).problem).toBe('no-text-layer');
  });

  it('rejects too little content', () => {
    expect(prepareRequest(doc(['Strona tytułowa.'])).problem).toBe('insufficient-content');
  });

  it('reports instead of truncating long documents', () => {
    const ready = prepareRequest(doc(Array.from({ length: 3 }, () => 'a'.repeat(19_000))));
    expect(ready.problem).toBe('document-too-long');
    expect(ready.request.pages[0]?.text).toHaveLength(19_000);
    expect(prepareRequest(doc(['a'.repeat(20_001)])).problem).toBe('page-too-long');
  });
});
