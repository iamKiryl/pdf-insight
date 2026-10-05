import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

/** Reads the shared contract fixtures (the same files pytest validates). Vitest runs from frontend/. */
export const contractsDir = resolve(process.cwd(), '../contracts');
const fixturesDir = join(contractsDir, 'fixtures');

export interface Fixture {
  name: string;
  description: string;
  data: unknown;
}

export function loadFixtures(kind: 'accepted' | 'rejected'): Fixture[] {
  const dir = join(fixturesDir, 'output', kind);
  return readdirSync(dir)
    .filter((file) => file.endsWith('.json'))
    .sort()
    .map((file) => {
      const parsed = JSON.parse(readFileSync(join(dir, file), 'utf-8')) as {
        description: string;
        data: unknown;
      };
      return { name: file.replace(/\.json$/u, ''), ...parsed };
    });
}

/** Path relative to contracts/fixtures/; callers state the expected shape. */
export function loadJson(relative: string): unknown {
  return JSON.parse(readFileSync(join(fixturesDir, relative), 'utf-8'));
}

export function acceptedResult(): Record<string, unknown> {
  const fixture = loadFixtures('accepted').find((f) => f.name === 'contract-partial-scan');
  if (!fixture) throw new Error('missing fixture');
  return structuredClone(fixture.data) as Record<string, unknown>;
}
