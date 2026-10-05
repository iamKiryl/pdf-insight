// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { serializeResult } from '../lib/download';
import { AnalysisResultSchema } from '../lib/schema';
import { acceptedResult } from '../test/fixtures';
import { ResultView } from './ResultView';

afterEach(cleanup);

describe('ResultView', () => {
  const result = AnalysisResultSchema.parse(acceptedResult());

  it('renders structured data as text with a partial-analysis warning', () => {
    render(<ResultView result={result} durationMs={12_300} onReset={() => undefined} />);
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(result.document.title);
    expect(screen.getByRole('note').textContent).toContain('Strona 11 (z 12)');
    expect(screen.getByText(result.summary)).toBeTruthy();
    const amounts = screen.getByRole('table', { name: 'Kwoty wymienione w dokumencie' });
    expect(within(amounts).getAllByRole('row')).toHaveLength(result.amounts.length + 1);
    expect(screen.getByText('Kwadrat Software S.A.')).toBeTruthy();
  });

  it('shows the same JSON that is downloaded', () => {
    const { container } = render(
      <ResultView result={result} durationMs={1000} onReset={() => undefined} />,
    );
    expect(container.querySelector('pre code')?.textContent).toBe(serializeResult(result));
  });

  it('renders injected markup literally instead of as HTML', () => {
    const hostile = { ...result, keyPoints: ['<img src=x onerror=alert(1)>', 'Drugi.', 'Trzeci.'] };
    const { container } = render(
      <ResultView result={hostile} durationMs={1000} onReset={() => undefined} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeTruthy();
  });
});
