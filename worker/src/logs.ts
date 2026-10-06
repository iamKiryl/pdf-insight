/** Operational logs: whitelisted numeric/label fields only, never document text (logs.py). */

const EVENT_FIELDS = new Set([
  'event', 'outcome', 'status', 'ms', 'attempts', 'pageCount', 'pagesWithoutText', 'ocrPages',
  'textChars',
  'model', 'promptVersion', 'modelCallsStarted', 'modelCallsCompleted', 'usageReportedCalls',
  'usageComplete', 'reportedPromptTokens', 'reportedCompletionTokens', 'mode', 'runtime',
]); // prettier-ignore
const CALL_FIELDS = new Set([
  'label', 'attempt', 'outcome', 'ms', 'promptTokens', 'completionTokens', 'finishReason',
  'outputBytes', 'providerCode',
]); // prettier-ignore
const MAX_PROBLEMS = 10;

function pick(fields: Record<string, unknown>, allowed: Set<string>): Record<string, unknown> {
  const safe: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (
      allowed.has(key) &&
      (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    ) {
      safe[key] = value;
    }
  }
  return safe;
}

export function logEvent(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(pick(fields, EVENT_FIELDS)));
}

/** ``problems`` are validator field paths and fixed reasons (never quoted text). */
export function logModelCall(
  problems: string[] | undefined,
  fields: Record<string, unknown>,
): void {
  const safe: Record<string, unknown> = { event: 'model_call', ...pick(fields, CALL_FIELDS) };
  if (problems?.length) safe.problems = problems.slice(0, MAX_PROBLEMS).map((p) => p.slice(0, 160));
  console.log(JSON.stringify(safe));
}
