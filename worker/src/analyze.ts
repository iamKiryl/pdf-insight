/**
 * One compact analysis: candidates, one model call, at most ONE corrective retry for invalid
 * output, one overall deadline (analyze_compact in backend compact.py). Provider timeouts, quota
 * and availability errors are never retried. Logs carry numbers and fixed labels only.
 */
import { TooManyCandidates, extractCandidates, type Candidate } from './candidates';
import {
  assemble,
  buildMessages,
  correctionMessage,
  parseSelection,
  type Message,
} from './compact';
import {
  COMPACT_MAX_CHARS,
  totalChars,
  type AnalysisResult,
  type AnalyzeRequest,
} from './contract';
import type { Settings } from './config';
import { AIProviderError, ApiError, InvalidModelOutput } from './errors';
import { logModelCall } from './logs';
import { OUTPUT_SCHEMA } from './prompt';

export const MAX_ATTEMPTS = 2;
export const MIN_RETRY_SECONDS = 5;
const SUPPORTED_MODELS = new Set(['@cf/meta/llama-3.3-70b-instruct-fp8-fast']);

export interface AIClient {
  run(model: string, inputs: Record<string, unknown>): Promise<unknown>;
}

export class ModelUsage {
  started = 0;
  completed = 0;
  usageReported = 0;
  promptTokens = 0;
  completionTokens = 0;

  complete(raw: unknown): void {
    this.completed += 1;
    const usage = isRecord(raw) ? raw.usage : undefined;
    if (!isRecord(usage)) return;
    const values = [usage.prompt_tokens, usage.completion_tokens];
    if (!values.every((v) => typeof v === 'number' && Number.isInteger(v) && v >= 0)) return;
    this.usageReported += 1;
    this.promptTokens += values[0] as number;
    this.completionTokens += values[1] as number;
  }

  logFields() {
    return {
      modelCallsStarted: this.started,
      modelCallsCompleted: this.completed,
      usageReportedCalls: this.usageReported,
      usageComplete: this.started === this.usageReported,
      reportedPromptTokens: this.promptTokens,
      reportedCompletionTokens: this.completionTokens,
    };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Workers AI "workers" style response: {"response": object | JSON string}. */
export function parsePayload(raw: unknown): Record<string, unknown> {
  let payload: unknown = isRecord(raw) && 'response' in raw ? raw.response : raw;
  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload);
    } catch {
      throw new InvalidModelOutput(['response is not valid JSON']);
    }
  }
  if (!isRecord(payload)) throw new InvalidModelOutput(['response must be a JSON object']);
  return payload;
}

function callDetails(raw: unknown): Record<string, number | string> {
  const details: Record<string, number | string> = {};
  if (!isRecord(raw)) return details;
  if (isRecord(raw.usage)) {
    if (Number.isInteger(raw.usage.prompt_tokens))
      details.promptTokens = raw.usage.prompt_tokens as number;
    if (Number.isInteger(raw.usage.completion_tokens))
      details.completionTokens = raw.usage.completion_tokens as number;
  }
  if (typeof raw.finish_reason === 'string') details.finishReason = raw.finish_reason;
  if ('response' in raw && (typeof raw.response === 'string' || isRecord(raw.response))) {
    details.outputBytes = JSON.stringify(raw.response).length;
  }
  return details;
}

class CallTimeout extends Error {}

function withTimeout<T>(promise: Promise<T>, seconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new CallTimeout()), Math.max(0, seconds) * 1000);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  });
}

export async function analyzeCompact(
  request: AnalyzeRequest,
  ai: AIClient,
  settings: Settings,
  usage: ModelUsage = new ModelUsage(),
  clock: () => number = () => performance.now() / 1000,
): Promise<{ result: AnalysisResult; attempts: number }> {
  if (!SUPPORTED_MODELS.has(settings.aiModel)) throw new ApiError('SERVICE_MISCONFIGURED');
  if (totalChars(request) > COMPACT_MAX_CHARS) throw new ApiError('DOCUMENT_TOO_LONG');
  let candidates: Candidate[];
  try {
    candidates = extractCandidates(request);
  } catch (error) {
    if (error instanceof TooManyCandidates) throw new ApiError('TOO_MANY_CANDIDATES');
    throw error;
  }
  const byId = new Map(candidates.map((c) => [c.id, c]));
  const base = buildMessages(request, candidates);
  let messages: Message[] = base;
  const deadline = clock() + settings.aiTotalBudgetSeconds;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const remaining = deadline - clock();
    if (attempt > 1 && remaining < MIN_RETRY_SECONDS) throw new ApiError('AI_TIMEOUT');
    const inputs = {
      messages,
      response_format: { type: 'json_schema', json_schema: OUTPUT_SCHEMA },
      max_tokens: settings.aiMaxTokens,
      temperature: 0.1,
    };
    usage.started += 1;
    const started = performance.now();
    let record: Record<string, number | string> = { label: 'compact', attempt };
    const done = (outcome: string, problems?: string[]) =>
      logModelCall(problems, { outcome, ms: Math.round(performance.now() - started), ...record });
    let rawText = '';
    let problems: string[];
    try {
      const raw = await withTimeout(
        ai.run(settings.aiModel, inputs),
        Math.min(settings.aiTimeoutSeconds, remaining),
      );
      usage.complete(raw);
      record = { ...record, ...callDetails(raw) };
      const payload = parsePayload(raw);
      rawText = JSON.stringify(payload);
      const selection = parseSelection(payload, byId, request);
      if (selection.output.insufficientContent) {
        done('insufficient_content');
        throw new ApiError('INSUFFICIENT_CONTENT');
      }
      const result = assemble(request, selection);
      done('ok');
      return { result, attempts: attempt };
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof CallTimeout) {
        done('timeout');
        throw new ApiError('AI_TIMEOUT');
      }
      if (error instanceof AIProviderError) {
        if (error.code !== null) record.providerCode = error.code;
        done(`provider_${error.kind}`);
        if (error.kind === 'quota') throw new ApiError('AI_QUOTA_EXCEEDED');
        if (error.kind !== 'invalid_output') throw new ApiError('AI_UNAVAILABLE');
        problems = ['the model could not produce JSON matching the schema'];
      } else if (error instanceof InvalidModelOutput) {
        problems = error.problems;
        done('invalid_output', problems);
      } else {
        throw error;
      }
    }
    if (attempt < MAX_ATTEMPTS) {
      const history: Message[] = rawText
        ? [{ role: 'assistant', content: rawText.slice(0, 8000) }]
        : [];
      messages = [...base, ...history, correctionMessage(problems)];
    }
  }
  throw new ApiError('AI_INVALID_OUTPUT');
}
