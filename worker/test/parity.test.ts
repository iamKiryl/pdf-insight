/**
 * Parity with the reviewed Python compact path. Golden files are produced by
 * backend/tools/parity_fixtures.py from PYTHON (never regenerated from TypeScript):
 * candidates (exact contexts), the full prompt with markers, and per-scenario assembled results or
 * invalid-output problem paths. The recruitment sample stays local (.local/parity/sample.json).
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { TooManyCandidates, extractCandidates } from '../src/candidates';
import { assemble, buildMessages, parseSelection } from '../src/compact';
import { AnalyzeRequestSchema } from '../src/contract';
import { InvalidModelOutput } from '../src/errors';
import { COMPACT_PROMPT_VERSION, OUTPUT_SCHEMA, SYSTEM_PROMPT } from '../src/prompt';

const here = dirname(fileURLToPath(import.meta.url));
const load = (path: string): unknown => JSON.parse(readFileSync(path, 'utf-8'));

interface Scenario {
  label: string;
  payload: Record<string, unknown>;
  result?: unknown;
  invalid?: string[];
  insufficientContent?: boolean;
}
interface Case {
  name: string;
  request: unknown;
  tooManyCandidates?: boolean;
  candidates?: { id: number; kind: string; page: number; value: number | null; currency: string | null; date: string | null; context: string }[]; // prettier-ignore
  userMessage?: string;
  scenarios?: Scenario[];
}

const adversarial = load(join(here, 'parity/adversarial.json')) as Case[];
const offer = load(join(here, 'parity/offer.json')) as Case;
const samplePath = join(here, '../../.local/parity/sample.json');
const cases: Case[] = [
  ...adversarial,
  offer,
  ...(existsSync(samplePath) ? [load(samplePath) as Case] : []),
];

function runScenario(scenario: Scenario, request: ReturnType<typeof AnalyzeRequestSchema.parse>) {
  const candidates = extractCandidates(request);
  const byId = new Map(candidates.map((c) => [c.id, c]));
  try {
    const selection = parseSelection(structuredClone(scenario.payload), byId, request);
    if (selection.output.insufficientContent) return { insufficientContent: true };
    return { result: JSON.parse(JSON.stringify(assemble(request, selection))) as unknown };
  } catch (error) {
    if (!(error instanceof InvalidModelOutput)) throw error;
    return { invalid: [...new Set(error.problems.map((p) => p.split(':')[0] ?? ''))].sort() };
  }
}

describe('prompt and schema are the Python ones', () => {
  it('matches system prompt, output schema and version byte for byte', () => {
    const python = load(join(here, 'parity/prompt.json')) as Record<string, unknown>;
    expect(SYSTEM_PROMPT).toBe(python.systemPrompt);
    expect(OUTPUT_SCHEMA).toEqual(python.outputSchema);
    expect(COMPACT_PROMPT_VERSION).toBe(python.promptVersion);
  });
});

describe.each(cases.map((c) => [c.name, c] as const))('parity: %s', (_name, golden) => {
  const request = AnalyzeRequestSchema.parse(golden.request);

  if (golden.tooManyCandidates) {
    it('rejects too many candidates explicitly', () => {
      expect(() => extractCandidates(request)).toThrow(TooManyCandidates);
    });
    return;
  }

  it('produces the same candidates with exact contexts', () => {
    const got = extractCandidates(request).map(({ id, kind, page, value, currency, date, context }) => ({
      id, kind, page, value, currency, date, context,
    })); // prettier-ignore
    expect(got).toEqual(golden.candidates);
  });

  it('builds the same marked prompt', () => {
    const messages = buildMessages(request, extractCandidates(request));
    expect(messages[1]?.content).toBe(golden.userMessage);
  });

  for (const scenario of golden.scenarios ?? []) {
    it(`scenario ${scenario.label}`, () => {
      const got = runScenario(scenario, request);
      if (scenario.invalid) expect(got).toEqual({ invalid: scenario.invalid });
      else if (scenario.insufficientContent) expect(got).toEqual({ insufficientContent: true });
      else expect(got).toEqual({ result: scenario.result });
    });
  }
});
