// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OcrPageResult } from '../lib/ocr';
import { prepareRequest } from '../lib/request';
import { OcrReview } from './OcrPanels';

afterEach(cleanup);

const results: OcrPageResult[] = [
  { page: 11, text: 'zmienić $ 5 ust. 2', confidence: 92, status: 'recognized', preview: null },
  { page: 12, text: '', confidence: 0, status: 'unreadable', preview: null },
];
const readiness = prepareRequest({
  fileName: 'a.pdf',
  fileBytes: 1,
  pageCount: 1,
  pages: [{ page: 1, text: 'Tekst dokumentu. '.repeat(20) }],
  pagesWithoutText: [],
});

describe('OcrReview', () => {
  it('every page is an editable, labelled textarea; edits are reported, never automated', () => {
    const onEdit = vi.fn();
    render(
      <OcrReview
        results={results}
        edits={{}}
        readiness={readiness}
        recovered={[11]}
        onEdit={onEdit}
        onResetPage={vi.fn()}
        onAccept={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );
    const page11 = screen.getByLabelText<HTMLTextAreaElement>(/Strona 11 — tekst do sprawdzenia/u);
    expect(page11.value).toBe('zmienić $ 5 ust. 2');
    expect(screen.getByLabelText(/Strona 12 — tekst do sprawdzenia/u)).toBeTruthy();
    expect(screen.getByText(/OCR nie rozpoznał tekstu/u)).toBeTruthy();
    fireEvent.change(page11, { target: { value: 'zmienić § 5 ust. 2' } });
    expect(onEdit).toHaveBeenCalledWith(11, 'zmienić § 5 ust. 2');
    expect(screen.queryByRole('button', { name: /Przywróć tekst/u })).toBeNull();
  });

  it('an edited page says so (no machine confidence claim) and can be reset', () => {
    const onResetPage = vi.fn();
    render(
      <OcrReview
        results={results}
        edits={{ 11: 'zmienić § 5 ust. 2' }}
        readiness={readiness}
        recovered={[11]}
        onEdit={vi.fn()}
        onResetPage={onResetPage}
        onAccept={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );
    expect(screen.getByText(/Poprawiono ręcznie/u)).toBeTruthy();
    expect(screen.queryByText(/pewność OCR 92/u)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Przywróć tekst rozpoznany przez OCR' }));
    expect(onResetPage).toHaveBeenCalledWith(11);
  });
});
