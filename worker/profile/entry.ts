/**
 * LOCAL-ONLY profiling entry (never deployed; not part of src/ or the production build).
 * Replays POST /api/analyze N times through the real handler with a fake AI that returns the
 * run-P-shaped provider response (payload rebuilt from public run P plus its usage;
 * .local/parity/run-P-provider-response.json, git-ignored) and fake limiters,
 * so the client can time the full TS request path in workerd: body read, JSON, Zod request
 * validation, candidates, prompt, selection validation, assembly, Zod result validation, JSON.
 */
import worker from '../src/index';
import providerResponse from '../../.local/parity/run-P-provider-response.json';

const allow = { limit: () => Promise.resolve({ success: true }) };
const env = {
  ENVIRONMENT: 'production',
  ALLOWED_ORIGINS: 'https://iamkiryl.github.io',
  AI: { run: () => Promise.resolve(structuredClone(providerResponse)) }, // run-P-shaped: payload + usage
  ANALYZE_IP_LIMITER: allow,
  ANALYZE_GLOBAL_LIMITER: allow,
};

export default {
  async fetch(request: Request): Promise<Response> {
    const n = Math.min(50, Math.max(1, Number(new URL(request.url).searchParams.get('n') ?? '1')));
    const body = await request.arrayBuffer();
    let status = 0;
    let bytes = 0;
    for (let i = 0; i < n; i++) {
      const response = await worker.fetch(
        new Request('https://local/api/analyze', {
          method: 'POST',
          headers: { 'content-type': 'application/json', origin: 'https://iamkiryl.github.io' },
          body,
        }),
        env,
      );
      status = response.status;
      bytes = (await response.arrayBuffer()).byteLength;
    }
    return Response.json({ n, status, bytes });
  },
};
