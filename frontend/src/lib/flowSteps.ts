import type { FlowState } from './useAnalysisFlow';

export type StepStatus = 'done' | 'active' | 'waiting' | 'error' | 'todo';

export interface FlowStep {
  number: string;
  title: string;
  hint: string;
  status: StepStatus;
  /** The step the user is on (also when the flow has finished on the last step). */
  current: boolean;
}

const STEPS = [
  { number: '01', title: 'Wgraj PDF', hint: 'Przeciągnij lub wybierz plik' },
  { number: '02', title: 'Odczyt tekstu', hint: 'Tekst z każdej strony' },
  { number: '03', title: 'Analiza AI', hint: 'Podsumowanie i dane' },
  { number: '04', title: 'Wynik', hint: 'Widok i eksport JSON' },
] as const;

/** Index of the step the user is on, and whether it is running, waiting for them or failed. */
function position(state: FlowState): { index: number; status: StepStatus } {
  switch (state.phase) {
    case 'idle':
      return { index: 0, status: 'waiting' };
    case 'reading':
      return { index: 1, status: 'active' };
    case 'ready':
      return { index: 2, status: 'waiting' };
    case 'recognizing':
      return { index: 1, status: state.problem ? 'error' : 'active' };
    case 'ocr-review':
      return { index: 1, status: 'waiting' };
    case 'analyzing':
      return { index: 2, status: 'active' };
    case 'done':
      return { index: 3, status: 'done' };
    case 'error':
      return { index: { upload: 0, read: 1, analyze: 2 }[state.stage], status: 'error' };
  }
}

/** Step indicator derived only from the real flow state: no invented progress percentage. */
export function flowSteps(state: FlowState): FlowStep[] {
  const { index, status } = position(state);
  return STEPS.map((step, i) => ({
    ...step,
    status: i < index ? 'done' : i === index ? status : 'todo',
    current: i === index,
  }));
}

/** All four steps done, the last current: a finished result (also reopened from history). */
export function finishedSteps(): FlowStep[] {
  return flowSteps({ phase: 'idle' }).map((step, i, all) => ({
    ...step,
    status: 'done',
    current: i === all.length - 1,
  }));
}

export const STEP_STATUS_LABELS: Record<StepStatus, string> = {
  done: 'zakończono',
  active: 'w toku',
  waiting: 'teraz',
  error: 'błąd',
  todo: 'oczekuje',
};
