import { describe, expect, it } from 'vitest';
import { flowSteps } from './flowSteps';
import type { FlowState } from './useAnalysisFlow';
import type { ExtractedDocument } from './pdf';
import type { Readiness } from './request';
import type { AnalysisResult } from './schema';
import type { UserMessage } from './messages';

const doc = {} as ExtractedDocument;
const readiness = {} as Readiness;
const message: UserMessage = { title: 'Błąd', detail: 'x', retryable: false };

function statuses(state: FlowState) {
  return flowSteps(state).map((step) => step.status);
}

describe('flowSteps follows the real flow state', () => {
  it.each<[string, FlowState, string[]]>([
    ['idle', { phase: 'idle' }, ['waiting', 'todo', 'todo', 'todo']],
    [
      'reading',
      { phase: 'reading', fileName: 'a.pdf', page: 1, total: 3 },
      ['done', 'active', 'todo', 'todo'],
    ],
    ['ready', { phase: 'ready', doc, readiness }, ['done', 'done', 'waiting', 'todo']],
    [
      'analyzing',
      { phase: 'analyzing', doc, readiness, startedAt: 0 },
      ['done', 'done', 'active', 'todo'],
    ],
    [
      'done',
      { phase: 'done', doc, result: {} as AnalysisResult, durationMs: 1 },
      ['done', 'done', 'done', 'done'],
    ],
    [
      'upload error',
      { phase: 'error', stage: 'upload', message, retry: null },
      ['error', 'todo', 'todo', 'todo'],
    ],
    [
      'read error',
      { phase: 'error', stage: 'read', message, retry: null },
      ['done', 'error', 'todo', 'todo'],
    ],
    [
      'analysis error',
      { phase: 'error', stage: 'analyze', message, retry: null },
      ['done', 'done', 'error', 'todo'],
    ],
  ])('%s', (_name, state, expected) => {
    expect(statuses(state)).toEqual(expected);
    expect(flowSteps(state).filter((step) => step.current)).toHaveLength(1);
  });

  it('never reports a percentage, only the four named steps', () => {
    const steps = flowSteps({ phase: 'idle' });
    expect(steps.map((step) => `${step.number} ${step.title}`)).toEqual([
      '01 Wgraj PDF',
      '02 Odczyt tekstu',
      '03 Analiza AI',
      '04 Wynik',
    ]);
  });
});
