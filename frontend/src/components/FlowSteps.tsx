import { STEP_STATUS_LABELS, type FlowStep } from '../lib/flowSteps';

const SYMBOLS = { done: '✓', active: '●', waiting: '→', error: '✕', todo: '' } as const;

/** Progress indicator, not navigation: steps are list items, never buttons. */
export function FlowSteps({ steps }: { steps: readonly FlowStep[] }) {
  return (
    <ol className="steps" aria-label="Etapy analizy">
      {steps.map((step) => (
        <li
          key={step.number}
          className={`step step--${step.status}`}
          aria-current={step.current ? 'step' : undefined}
        >
          <span className="label">Krok {step.number}</span>
          <span className="step__title">{step.title}</span>
          <span className="step__hint">{step.hint}</span>
          <span className="step__status">
            {SYMBOLS[step.status] && <span aria-hidden="true">{SYMBOLS[step.status]} </span>}
            {STEP_STATUS_LABELS[step.status]}
          </span>
        </li>
      ))}
    </ol>
  );
}
