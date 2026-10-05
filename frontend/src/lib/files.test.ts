import { describe, expect, it } from 'vitest';
import { acceptedResult } from '../test/fixtures';
import { downloadFileName, serializeResult } from './download';
import { checkFile, hasPdfSignature } from './pdf';
import { AnalysisResultSchema } from './schema';

describe('file checks', () => {
  const file = (name: string, size: number, type = 'application/pdf') =>
    ({ name, size, type }) as File;

  it('accepts PDFs up to exactly 10 MB', () => {
    expect(checkFile(file('a.pdf', 10 * 1024 * 1024))).toBeNull();
    expect(checkFile(file('a.pdf', 10 * 1024 * 1024 + 1))).toBe('too-large');
  });

  it('rejects other types and empty files', () => {
    expect(checkFile(file('a.docx', 10, 'application/msword'))).toBe('not-pdf');
    expect(checkFile(file('a.pdf', 0))).toBe('empty');
    expect(checkFile(file('A.PDF', 10, ''))).toBeNull();
  });

  it('checks the PDF signature, not only the extension', () => {
    expect(hasPdfSignature(new TextEncoder().encode('%PDF-1.7\n...'))).toBe(true);
    expect(hasPdfSignature(new TextEncoder().encode('PK\u0003\u0004 zip'))).toBe(false);
  });
});

describe('JSON download', () => {
  it('serializes exactly what validates and round-trips', () => {
    const result = AnalysisResultSchema.parse(acceptedResult());
    const text = serializeResult(result);
    expect(AnalysisResultSchema.parse(JSON.parse(text))).toEqual(result);
  });

  it('derives a safe file name', () => {
    expect(downloadFileName('Umowa 14/2026.pdf')).toBe('Umowa_14_2026-analiza.json');
    expect(downloadFileName('.pdf')).toBe('dokument-analiza.json');
  });
});
