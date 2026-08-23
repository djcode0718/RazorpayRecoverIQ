# RecoverIQ - Razorpay Buildathon Demo (Track 03)

RecoverIQ is an AI-assisted, policy-bounded revenue recovery system for failed payments.

Core product narrative:

`FAILED PAYMENT -> AI UNDERSTANDING -> POLICY DECISION -> BOUNDED RECOVERY -> VERIFIED MONEY RECOVERED`

## What This Project Delivers

- FastAPI backend with SQLite persistence and auditable workflow events.
- React + TypeScript Command Center UI driven entirely by backend APIs.
- Deterministic simulation flow and explicit `razorpay_test` mode visibility.
- AI diagnosis with strict schema validation and safe fallback behavior.
- Deterministic policy gates that can block AI recommendations.
- Guardrailed recovery execution with verified outcome accounting.
- Persisted evaluation center (baseline vs RecoverIQ) with financial/operational metrics.
- Failure demos for security and resilience evidence.

## High-Level Architecture

- `backend/app/main.py`: app bootstrapping, exception handlers, request tracing.
- `backend/app/api/routes.py`: all product APIs used by frontend and demo workflow.
- `backend/app/webhooks.py`: webhook verification, idempotency, processing.
- `backend/app/recovery_intelligence.py`: opportunity-level AI/rule decision creation.
- `backend/app/policy_engine.py`: deterministic pass/fail checks and reason codes.
- `backend/app/recovery_executor.py`: bounded execution and payment link actions.
- `backend/app/outcome_verifier.py`: verification and recovered revenue accounting.
- `backend/app/evaluation.py`: synthetic held-out datasets, baseline + RecoverIQ metrics.
- `frontend/src/App.tsx`: Command Center, Opportunity Detail, Evaluation Center, Failure Demos, Readiness.

## Product Workflow

1. Failed payment signal enters via webhook (`payment.failed`) or simulation seed.
2. Opportunity is created and quantified (`revenue_at_risk`, `expected_recovery`, `expected_net`).
3. AI diagnosis generates evidence and recommendation.
4. Policy checks independently gate execution:
   - confidence check
   - amount check
   - expected recovery check
   - retry limit check
   - duplicate check
   - Test Mode check
5. If allowed, recovery action executes through adapter path.
6. Outcome is verified (`VERIFIED_SUCCESS` / safe failure states).
7. Metrics and audit events update command center + detail timeline.

## Command Center Coverage

Primary dashboard metrics:
- Revenue At Risk
- Recoverable Revenue
- Recovery Attempts
- Gross Recovered
- Net Recovered
- Recovery Rate
- Active Opportunities

Operational policy outcomes:
- ALLOWED
- BLOCKED
- ESCALATED

Mode visibility:
- `SIMULATION MODE`
- `RAZORPAY TEST MODE`

## Opportunity Screens

Opportunity list columns (API-backed):
- Opportunity
- Customer
- Amount
- Failure
- Probability
- Expected Recovery
- Policy
- Action
- Status

Opportunity detail (judge-primary screen):
- Payment
- Customer history
- Failure
- AI diagnosis
- Evidence
- Confidence
- Economic calculation
- Policy checks (PASS/FAIL)
- Recovery action
- Razorpay Payment Link
- Payment status
- Verified outcome
- Audit trail
- Recovery state progression (Opportunity -> Recommended -> Approved -> Payment Link Created -> Pending -> Successful -> Verified -> Recovered)

## Evaluation Center

Uses persisted evaluation runs and deterministic synthetic datasets.

Shows:
- Baseline vs RecoverIQ
- Precision, Recall, F1, False Positive Rate
- False-positive cost (count, exposure, intervention cost)
- Revenue recovered (gross/net)
- Operational counters (allowed/blocked/escalated/failed)

## Failure Demos

Built-in scenarios:
- invalid webhook signature
- invalid evaluation request
- missing opportunity
- AI invalid output
- AI unavailable
- policy blocked
- recovery failure
- duplicate webhook

Each scenario returns a deterministic safe envelope with `expected_behavior` and `actual_behavior`.

## API Surface (Primary)

Health and readiness:
- `GET /health`
- `GET /ready`

Dashboard and opportunities:
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{opportunity_id}`
- `GET /api/v1/opportunities/{opportunity_id}/explanation`
- `POST /api/v1/opportunities/{opportunity_id}/evaluate`
- `POST /api/v1/opportunities/{opportunity_id}/execute`
- `GET /api/v1/opportunities/{opportunity_id}/audit`

Evaluation:
- `POST /api/v1/evaluation/run`
- `GET /api/v1/evaluation/history`
- `GET /api/v1/evaluation/{run_id}`
- `GET /api/v1/evaluation/{run_id}/comparison`
- `GET /api/v1/evaluation/{run_id}/drilldown`

Demo and readiness:
- `POST /api/v1/demo/reset-core-recovery`
- `POST /api/v1/demo/seed-core-recovery`
- `POST /api/v1/readiness/phase13/execute`

Integrations and webhooks:
- `GET /api/v1/integrations/razorpay/status`
- `POST /api/v1/webhooks/razorpay`

Safety demos:
- `GET /api/v1/failure-demos`
- `POST /api/v1/failure-demos/trigger`

## Configuration

Start from `.env.example`.

Core settings:
- `APP_NAME`
- `APP_ENV`
- `APP_MODE`
- `RECOVERIQ_DB_URL`
- `API_PREFIX`

Razorpay settings:
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `PAYMENT_ADAPTER_MODE=simulation|razorpay_test`

AI settings:
- `AI_PROVIDER=mock|local|ollama`
- `OLLAMA_MODEL`

Logging settings:
- `LOG_LEVEL`
- `LOG_SQL_QUERIES=true|false`

Notes:
- Use `razorpay_test` only for buildathon demo connectivity checks.
- Live mode is intentionally not supported for this demo workflow.

## Quick Start

### One-command startup

Windows (PowerShell):

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ
.\start.ps1
```

Linux/macOS:

```bash
cd /path/to/RazorpayRecoverIQ
chmod +x ./start.sh
./start.sh
```

Default URLs:
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

### Manual backend start (Windows)

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "C:\SourceCode\RazorpayRecoverIQ\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

### Manual frontend start (Windows)

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ\frontend
npm install
npm run dev
```

## Demo Operations

For a clean evidence run with concise logs:

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ
$env:LOG_SQL_QUERIES = "false"
.\start.ps1
```

From UI:
1. `Reset Demo`
2. `Seed Demo`
3. Inspect command center + opportunity detail
4. Run evaluation
5. Trigger failure demos


## Security Posture

- Webhook signature validation is enforced.
- Duplicate webhook deliveries are idempotent.
- AI recommendations cannot bypass policy.
- Recovery executor is bounded by allowlist + policy result.
- Safe error envelopes avoid leaking sensitive internals.
- Redaction utilities protect sensitive fields in logs/metadata paths.
- Demo and integration checks expose `test_mode` and `live_mode_detected` status.

## Testing

Full backend test suite:

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ
$env:PYTHONPATH = "C:\SourceCode\RazorpayRecoverIQ\backend"
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Focused high-signal bundle (recommended when optimizing for < 1 minute):

```powershell
Set-Location C:\SourceCode\RazorpayRecoverIQ
$env:PYTHONPATH = "C:\SourceCode\RazorpayRecoverIQ\backend"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_recovery_workflow_end_to_end.py backend\tests\test_webhook_ingestion_idempotency.py backend\tests\test_opportunity_api_contracts.py backend\tests\test_evaluation_center_api_contracts.py backend\tests\test_security_error_envelope_and_redaction.py backend\tests\test_readiness_workflow_api.py backend\tests\test_razorpay_integration_status_api.py -q
```

## Troubleshooting

- If opportunities are empty, run `Seed Demo` and refresh.
- If webhook tests fail, verify `RAZORPAY_WEBHOOK_SECRET` is set.
- If AI provider errors appear, switch to `AI_PROVIDER=mock` for deterministic behavior.
- If mode badge is unexpected, verify `PAYMENT_ADAPTER_MODE` and restart backend.
- If logs are noisy during acceptance evidence capture, set `LOG_SQL_QUERIES=false` before start.

