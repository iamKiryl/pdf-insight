import type { AnalysisResult } from './schema';

/** The exact string shown in the JSON preview and saved to disk. */
export function serializeResult(result: AnalysisResult): string {
  return `${JSON.stringify(result, null, 2)}\n`;
}

export function downloadFileName(sourceName: string): string {
  const base = sourceName.replace(/\.pdf$/iu, '').replace(/[^\p{L}\p{N}._-]+/gu, '_');
  return `${base.slice(0, 80) || 'dokument'}-analiza.json`;
}

export function downloadJson(result: AnalysisResult): void {
  const blob = new Blob([serializeResult(result)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = downloadFileName(result.document.fileName);
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}
