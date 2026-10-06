# TS compact runtime review and controlled deployment — 2026-10-06

Reviewed 974d77d. Codex independently ran worker typecheck and all 103 tests (including the local
full contract). Reviewed transport, configuration, compact selection/assembly, call deadlines and
retry, shared schema and parity harness. No release-blocking issue identified in the reviewed
paths. This is scoped review, not proof of equivalence on every possible PDF.

Parity tests compare invalid field paths, not necessarily identical error descriptions. The full
recruitment contract is intentionally local and absent from CI; committed adversarial/offer cases
remain in CI. Documented Unicode/number deviations are retained. Promise.race stops waiting but
does not establish cancellation of remote inference; a timeout may still consume provider quota.
Local 4.2 ms is encouraging, not evidence of Cloudflare CPU compliance. The model remains 70B and
its timing risk remains independent of runtime. Non-fp8 8B is unavailable; do not retry it.

## Next Claude task: deploy the reviewed TS backend and measure

The reviewed TS candidate is cleared for replacement of the existing `pdf-insight-api` Worker.
Use the existing manual Opus subscription workflow. No paid services, no model change, no new
infrastructure and no recruitment messages. Preserve current frontend/history fix.

1. Check the actual deployed version and save its full identifier for rollback before mutation.
   Verify local tree/commit and the TS production config still match the reviewed candidate. Run
   required checks if anything changed. Deploy from `worker/` to the existing Worker name using
   the prepared config. Do not accidentally deploy Python or the profiling entrypoint. Record
   deployed version, commit, bundle/startup measurements and URL.
2. Start numeric-only tail capture (raw tail may include client/request headers: keep it ignored,
   never publish it). Test health, Pages preflight, foreign-origin rejection and one invalid
   full-size sample-shaped request that cannot reach AI. Record CPU per event, request status and
   cold/warm caveats. Confirm the deployed runtime/version through deployment metadata and TS log
   field; compact health alone does not distinguish Python from TS. No AI inference for these.
   If transport/configuration fails, fix or restore the recorded previous version before further
   work. Small-request CPU alone cannot certify successful analysis CPU.
3. Provided transport works and Free quota allows, run exactly ONE analysis of the sample via
   the PUBLIC Pages frontend. Budget: at most TWO provider calls including the one permitted
   invalid-output correction. Keep existing timeouts and quality checks. Measure upload-to-render,
   worker wall/CPU, actual call count/tokens, evaluator plus source review by Claude/AI, page-11
   coverage warning, export equality and history reopen with zero new calls. No repeated attempts
   just to get a green time. If timed out, record the failure and do not blame the runtime without
   evidence. No token report means usage unknown, not zero.
4. If successful, report observed CPU and latency separately: <30 s is required for this run;
   CPU must be assessed against the Free limit, with no resource-limit failures. A single success
   is not a reliability guarantee. If quality changes despite parity, investigate prompt/schema
   or binding response differences before considering any model tuning. If TS has a clear runtime
   regression or resource-limit errors, roll back to the saved exact version. A 70B timeout alone
   does not justify rolling back a runtime whose transport and CPU improved.
5. Update RUNTIME, STATUS, DEPLOYMENT, README and AI_LOG to actual deployed state and results.
   Do not call the demo accepted if it fails timing/quality/CPU checks. Preserve historical runs.
   Fix the rollback instructions: `pywrangler deploy` from current backend deploys CURRENT Python
   code/config, not the old exact version; for exact rollback use the recorded full deployment
   version with the appropriate Wrangler rollback command. Commit logically, push docs/source,
   check CI, and identify application revision separately from later documentation-only commits.

Stop the dependent live test if quota/access prevents it and record the exact blocker. No blind
model search. Report evidence sufficient for the next architectural decision. F08 and F10 stay
open; do not claim this checkpoint completes all requirements. Check Warsaw time against the
recorded 14:44 deadline before starting additional scope.
