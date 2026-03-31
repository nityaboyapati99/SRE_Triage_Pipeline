# SRE Triage Pipeline — OpenEnv Environment

An OpenEnv-compliant AI evaluation environment where agents diagnose production incidents by investigating simulated logs, metrics, and deployment history — then submit a structured diagnosis.

---

## Motivation

Every engineering team running production services faces incidents. Today, junior engineers spend 20–40 minutes triaging P1 alerts manually — correlating logs, checking metrics dashboards, reviewing recent deployments, and deciding whether to rollback, page someone, or auto-resolve.

This environment trains and evaluates AI agents on exactly this skill: **structured incident investigation and decision-making under pressure**.

---

## Environment Description

The agent receives a **production alert** (title, description, severity, affected services) and must investigate using four tools before submitting a diagnosis.

### Action Space

| Action Type | Parameters | Description |
|---|---|---|
| `query_logs` | `service_name` (optional) | Get log entries for a service |
| `query_metrics` | `service_name` (optional) | Get metric snapshots for a service |
| `query_deployments` | `service_name` (optional) | Get recent deployment records |
| `query_runbook` | — | Get the incident runbook |
| `submit_diagnosis` | `root_cause`, `affected_services`, `severity_assessment`, `escalation_decision` | Submit final diagnosis (terminates episode) |

**Escalation decisions:** `auto_resolve` · `page_on_call` · `rollback` · `scale_up` · `notify_only`

**Severity levels:** `P1` (critical) · `P2` (high) · `P3` (medium) · `P4` (low)

### Observation Space

| Field | Type | Description |
|---|---|---|
| `alert_title` | string | Alert headline |
| `alert_description` | string | Full alert description |
| `alert_severity` | enum | P1–P4 |
| `triggered_at` | ISO timestamp | When alert fired |
| `services_in_scope` | list[str] | Services in the alert |
| `logs` | list[LogEntry] | Log lines (after query_logs) |
| `metrics` | list[MetricSnapshot] | Metric data points (after query_metrics) |
| `deployments` | list[DeploymentRecord] | Deployment history (after query_deployments) |
| `runbook_steps` | list[RunbookEntry] | Step-by-step runbook |
| `done` | bool | Episode ended |
| `reward` | float | Score (only on submit_diagnosis) |
| `score_breakdown` | dict | Per-component scores |
| `grader_feedback` | string | Human-readable feedback |

---

## Tasks

### Task 1 — Basic Incident Triage (Easy)
- **Alert:** payment-service 500 error rate 28%
- **Root cause:** Database connection pool exhausted due to connection timeouts
- **Required:** Query payment-service logs → identify DB timeouts → page on-call
- **Pass threshold:** 0.70

### Task 2 — Cross-Service Cascading Failure (Medium)
- **Alert:** checkout-service P99 latency 18s, order completion rate 35%
- **Root cause:** Redis cache crashed → inventory-service falls back to slow DB queries → checkout-service times out
- **Required:** Correlate logs AND metrics across checkout-service and inventory-service
- **Pass threshold:** 0.65

### Task 3 — Platform-Wide Outage with Red Herrings (Hard)
- **Alert:** API gateway 503s, auth failures, data pipeline stalled, notification failures
- **Root cause:** key-store-service redeployed with wrong port → auth-service can't refresh JWKS → all auth fails → cascading failures
- **Required:** Trace dependency chain through 4 services + identify the deployment that caused it. Red herring: reporting-service OOM error is unrelated.
- **Pass threshold:** 0.55

---

## Reward Function

Scores are computed on `submit_diagnosis` (0.0–1.0):

| Component | Weight | Description |
|---|---|---|
| Root cause accuracy | 35% | Keyword overlap with ground truth root cause |
| Affected services | 20% | Jaccard similarity with correct service list |
| Severity assessment | 15% | Exact match = 1.0, one level off = 0.5 |
| Escalation decision | 20% | Exact match only |
| Investigation thoroughness | 10% | Did agent query the required data sources? |

**Partial rewards:** +0.025 for each unique data source type queried (max 0.10 bonus)

**Penalties:**
- -0.15 for submitting diagnosis without querying any data
- -0.01 per step over 15 (loop penalty)

---

## Setup & Usage

### Local

```bash
git clone https://github.com/nityaboyapati99/SRE_Triage_Pipeline
cd SRE_Triage_Pipeline
pip install -r requirements.txt

# Start the environment server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# In another terminal, run the baseline agent
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="meta-llama/Llama-3.3-70B-Instruct"
export HF_TOKEN="your-hf-token"
python inference.py
```

### Docker

```bash
docker build -t sre-triage-pipeline .
docker run -p 7860:7860 sre-triage-pipeline

# Run inference against the container
export ENV_BASE_URL="http://localhost:7860"
python inference.py
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/tasks` | List all tasks |
| POST | `/reset` | Start new episode `{"task_id": "task_easy"}` |
| POST | `/step` | Take action `{"action": {...}}` |
| GET | `/state` | Current episode state |
| POST | `/grader` | Standalone grader |

---

## Baseline Scores

Baseline agent: `meta-llama/Llama-3.3-70B-Instruct` via HF Inference API

| Task | Score | Pass? |
|---|---|---|
| task_easy | ~0.72 | ✅ |
| task_medium | ~0.65 | ✅ |
| task_hard | ~0.54 | ✅ |
| **Average** | **~0.64** | |

---

## Environment Variables

| Variable | Description |
|---|---|
| `API_BASE_URL` | LLM API endpoint |
| `MODEL_NAME` | Model identifier |
| `HF_TOKEN` | Hugging Face / API key |
| `ENV_BASE_URL` | Environment server URL (default: `http://localhost:7860`) |
