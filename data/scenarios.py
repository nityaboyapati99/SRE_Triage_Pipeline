"""
Pre-built incident scenarios for the SRE Triage Pipeline environment.

Each scenario contains:
- The initial alert
- Simulated log/metric/deployment data the agent can query
- Ground truth for grading
"""

from __future__ import annotations
from typing import Any, Dict

# ---------------------------------------------------------------------------
# TASK EASY — Single service, root cause obvious in logs
# ---------------------------------------------------------------------------
TASK_EASY: Dict[str, Any] = {
    "task_id": "task_easy",
    "alert": {
        "title": "P2 — payment-service HTTP 500 error rate spiking",
        "description": (
            "payment-service is returning HTTP 500 errors at 28% of requests. "
            "Users are unable to complete checkout. Alert fired at 2024-03-15T14:32:00Z."
        ),
        "severity": "P2",
        "triggered_at": "2024-03-15T14:32:00Z",
        "services_in_scope": ["payment-service"],
    },
    "logs": {
        "payment-service": [
            {"timestamp": "2024-03-15T14:30:01Z", "level": "INFO",  "service": "payment-service", "message": "Processing payment request for order #10231", "trace_id": "abc001"},
            {"timestamp": "2024-03-15T14:30:45Z", "level": "ERROR", "service": "payment-service", "message": "Database connection timeout after 30s — host: postgres-primary:5432", "trace_id": "abc002"},
            {"timestamp": "2024-03-15T14:31:02Z", "level": "ERROR", "service": "payment-service", "message": "Database connection timeout after 30s — host: postgres-primary:5432", "trace_id": "abc003"},
            {"timestamp": "2024-03-15T14:31:18Z", "level": "ERROR", "service": "payment-service", "message": "Database connection timeout after 30s — host: postgres-primary:5432", "trace_id": "abc004"},
            {"timestamp": "2024-03-15T14:31:30Z", "level": "CRITICAL","service": "payment-service", "message": "Connection pool exhausted — all 20 connections in use", "trace_id": "abc005"},
            {"timestamp": "2024-03-15T14:31:55Z", "level": "ERROR", "service": "payment-service", "message": "HTTP 500 returned to client — upstream DB unavailable", "trace_id": "abc006"},
            {"timestamp": "2024-03-15T14:32:10Z", "level": "ERROR", "service": "payment-service", "message": "HTTP 500 returned to client — upstream DB unavailable", "trace_id": "abc007"},
        ]
    },
    "metrics": {
        "payment-service": [
            {"timestamp": "2024-03-15T14:28:00Z", "service": "payment-service", "metric_name": "error_rate",    "value": 0.8,  "unit": "percent"},
            {"timestamp": "2024-03-15T14:29:00Z", "service": "payment-service", "metric_name": "error_rate",    "value": 4.2,  "unit": "percent"},
            {"timestamp": "2024-03-15T14:30:00Z", "service": "payment-service", "metric_name": "error_rate",    "value": 14.7, "unit": "percent"},
            {"timestamp": "2024-03-15T14:31:00Z", "service": "payment-service", "metric_name": "error_rate",    "value": 28.3, "unit": "percent"},
            {"timestamp": "2024-03-15T14:31:00Z", "service": "payment-service", "metric_name": "latency_p99",   "value": 28500,"unit": "ms"},
            {"timestamp": "2024-03-15T14:31:00Z", "service": "payment-service", "metric_name": "db_pool_used",  "value": 100.0,"unit": "percent"},
        ]
    },
    "deployments": {
        "payment-service": [
            {"deployed_at": "2024-03-14T09:00:00Z", "service": "payment-service", "version": "v2.3.1", "deployed_by": "ci-bot", "change_summary": "Minor UI copy changes", "rolled_back": False},
        ]
    },
    "runbook": {
        "alert_type": "database_connection_exhaustion",
        "steps": [
            {"step": 1, "instruction": "Check payment-service logs for database errors",          "expected_outcome": "Identify DB connection timeouts"},
            {"step": 2, "instruction": "Check DB connection pool metrics",                         "expected_outcome": "Confirm pool is exhausted"},
            {"step": 3, "instruction": "Restart payment-service to release stale connections",     "expected_outcome": "Error rate drops below 1%"},
            {"step": 4, "instruction": "Page DB on-call if pool exhaustion persists after restart","expected_outcome": "DB team investigates root cause"},
        ]
    },
    "ground_truth": {
        "root_cause_keywords": ["database", "connection", "timeout", "pool", "exhausted", "postgres"],
        "affected_services": ["payment-service"],
        "correct_severity": "P2",
        "correct_escalation": "page_on_call",
        "required_queries": ["query_logs"],   # minimum to get full score
    }
}


# ---------------------------------------------------------------------------
# TASK MEDIUM — Two services, must correlate logs + metrics
# ---------------------------------------------------------------------------
TASK_MEDIUM: Dict[str, Any] = {
    "task_id": "task_medium",
    "alert": {
        "title": "P1 — checkout-service latency > 15s, order completion rate dropped 60%",
        "description": (
            "checkout-service p99 latency has spiked to 18s. "
            "Order completion dropped from 95% to 35% in the last 10 minutes. "
            "Alert fired at 2024-03-20T09:15:00Z."
        ),
        "severity": "P1",
        "triggered_at": "2024-03-20T09:15:00Z",
        "services_in_scope": ["checkout-service", "inventory-service"],
    },
    "logs": {
        "checkout-service": [
            {"timestamp": "2024-03-20T09:05:00Z", "level": "INFO",  "service": "checkout-service", "message": "Order #20451 initiated", "trace_id": "xyz001"},
            {"timestamp": "2024-03-20T09:08:12Z", "level": "WARN",  "service": "checkout-service", "message": "inventory-service response slow — waiting 4200ms", "trace_id": "xyz001"},
            {"timestamp": "2024-03-20T09:10:45Z", "level": "ERROR", "service": "checkout-service", "message": "Timeout calling inventory-service after 10000ms — order #20451 failed", "trace_id": "xyz001"},
            {"timestamp": "2024-03-20T09:11:03Z", "level": "ERROR", "service": "checkout-service", "message": "Timeout calling inventory-service after 10000ms — order #20452 failed", "trace_id": "xyz002"},
            {"timestamp": "2024-03-20T09:12:30Z", "level": "ERROR", "service": "checkout-service", "message": "CircuitBreaker OPEN for inventory-service — failing fast", "trace_id": "xyz003"},
            {"timestamp": "2024-03-20T09:14:55Z", "level": "CRITICAL","service": "checkout-service", "message": "Order completion rate < 40%", "trace_id": None},
        ],
        "inventory-service": [
            {"timestamp": "2024-03-20T09:06:00Z", "level": "INFO",  "service": "inventory-service", "message": "Stock check request received", "trace_id": "xyz001"},
            {"timestamp": "2024-03-20T09:06:45Z", "level": "WARN",  "service": "inventory-service", "message": "Redis cache miss — falling back to DB query", "trace_id": "xyz001"},
            {"timestamp": "2024-03-20T09:07:10Z", "level": "ERROR", "service": "inventory-service", "message": "Redis connection refused — host: redis-cache:6379", "trace_id": "xyz002"},
            {"timestamp": "2024-03-20T09:08:00Z", "level": "ERROR", "service": "inventory-service", "message": "Redis connection refused — host: redis-cache:6379", "trace_id": "xyz003"},
            {"timestamp": "2024-03-20T09:09:22Z", "level": "ERROR", "service": "inventory-service", "message": "DB query taking 8200ms due to full table scan (no cache)", "trace_id": "xyz004"},
            {"timestamp": "2024-03-20T09:11:00Z", "level": "CRITICAL","service": "inventory-service", "message": "All threads busy — request queue growing", "trace_id": None},
        ]
    },
    "metrics": {
        "checkout-service": [
            {"timestamp": "2024-03-20T09:10:00Z", "service": "checkout-service", "metric_name": "latency_p99",        "value": 18200, "unit": "ms"},
            {"timestamp": "2024-03-20T09:10:00Z", "service": "checkout-service", "metric_name": "order_completion_rate","value": 35.0, "unit": "percent"},
            {"timestamp": "2024-03-20T09:10:00Z", "service": "checkout-service", "metric_name": "error_rate",          "value": 62.0, "unit": "percent"},
        ],
        "inventory-service": [
            {"timestamp": "2024-03-20T09:10:00Z", "service": "inventory-service", "metric_name": "latency_p99",   "value": 9800,  "unit": "ms"},
            {"timestamp": "2024-03-20T09:10:00Z", "service": "inventory-service", "metric_name": "cache_hit_rate","value": 0.0,   "unit": "percent"},
            {"timestamp": "2024-03-20T09:10:00Z", "service": "inventory-service", "metric_name": "cpu_percent",   "value": 98.5,  "unit": "percent"},
        ]
    },
    "deployments": {
        "checkout-service": [
            {"deployed_at": "2024-03-20T08:45:00Z", "service": "checkout-service", "version": "v4.1.2", "deployed_by": "ci-bot", "change_summary": "Updated inventory-service client timeout from 30s to 10s", "rolled_back": False},
        ],
        "inventory-service": [
            {"deployed_at": "2024-03-19T22:00:00Z", "service": "inventory-service", "version": "v3.0.8", "deployed_by": "ci-bot", "change_summary": "Routine dependency update", "rolled_back": False},
        ]
    },
    "runbook": {
        "alert_type": "downstream_service_timeout",
        "steps": [
            {"step": 1, "instruction": "Check checkout-service logs for upstream timeout errors",     "expected_outcome": "Identify which upstream service is failing"},
            {"step": 2, "instruction": "Check the identified upstream service (inventory-service) logs","expected_outcome": "Find root cause in upstream service"},
            {"step": 3, "instruction": "Check inventory-service metrics — cache hit rate and CPU",     "expected_outcome": "Confirm Redis cache failure causing CPU spike"},
            {"step": 4, "instruction": "Restart Redis cache service",                                  "expected_outcome": "Cache hit rate recovers, inventory latency drops"},
            {"step": 5, "instruction": "If Redis restart fails, page on-call SRE",                    "expected_outcome": "Human investigation of Redis cluster"},
        ]
    },
    "ground_truth": {
        "root_cause_keywords": ["redis", "cache", "inventory", "timeout", "circuit", "breaker"],
        "affected_services": ["checkout-service", "inventory-service"],
        "correct_severity": "P1",
        "correct_escalation": "page_on_call",
        "required_queries": ["query_logs", "query_metrics"],
    }
}


# ---------------------------------------------------------------------------
# TASK HARD — Cascading failure across 4 services, red herrings, recent deploy
# ---------------------------------------------------------------------------
TASK_HARD: Dict[str, Any] = {
    "task_id": "task_hard",
    "alert": {
        "title": "P1 — Platform-wide degradation: API gateway 503s, auth failures, data pipeline stalled",
        "description": (
            "Multiple services reporting failures simultaneously. "
            "api-gateway returning 503 on 40% of requests. "
            "auth-service JWT validation failing intermittently. "
            "data-pipeline job queue growing — no jobs completing. "
            "notification-service reporting send failures. "
            "Alert fired at 2024-04-01T03:22:00Z."
        ),
        "severity": "P1",
        "triggered_at": "2024-04-01T03:22:00Z",
        "services_in_scope": ["api-gateway", "auth-service", "data-pipeline", "notification-service"],
    },
    "logs": {
        "api-gateway": [
            {"timestamp": "2024-04-01T03:15:00Z", "level": "WARN",  "service": "api-gateway", "message": "Upstream auth-service latency > 2000ms", "trace_id": "p1-001"},
            {"timestamp": "2024-04-01T03:18:00Z", "level": "ERROR", "service": "api-gateway", "message": "auth-service health check failed — marking unhealthy", "trace_id": "p1-002"},
            {"timestamp": "2024-04-01T03:19:30Z", "level": "ERROR", "service": "api-gateway", "message": "All auth-service instances unhealthy — returning 503", "trace_id": "p1-003"},
            {"timestamp": "2024-04-01T03:20:00Z", "level": "ERROR", "service": "api-gateway", "message": "503 returned to client — no healthy upstreams", "trace_id": "p1-004"},
            {"timestamp": "2024-04-01T03:21:00Z", "level": "ERROR", "service": "api-gateway", "message": "503 returned to client — no healthy upstreams", "trace_id": "p1-005"},
            # Red herring: api-gateway config error — not the root cause
            {"timestamp": "2024-04-01T03:10:00Z", "level": "WARN",  "service": "api-gateway", "message": "Config reload: rate_limit updated from 1000 to 900 rps", "trace_id": None},
        ],
        "auth-service": [
            {"timestamp": "2024-04-01T03:12:00Z", "level": "INFO",  "service": "auth-service", "message": "JWT validation request received", "trace_id": "p1-010"},
            {"timestamp": "2024-04-01T03:13:45Z", "level": "ERROR", "service": "auth-service", "message": "Failed to fetch JWKS from key-store: connection refused — host: key-store-service:8443", "trace_id": "p1-011"},
            {"timestamp": "2024-04-01T03:14:00Z", "level": "ERROR", "service": "auth-service", "message": "Failed to fetch JWKS from key-store: connection refused — host: key-store-service:8443", "trace_id": "p1-012"},
            {"timestamp": "2024-04-01T03:15:00Z", "level": "CRITICAL","service": "auth-service", "message": "JWKS cache expired and refresh failing — all JWT validations failing", "trace_id": "p1-013"},
            {"timestamp": "2024-04-01T03:17:00Z", "level": "CRITICAL","service": "auth-service", "message": "Auth failure rate 100% — key-store-service unreachable", "trace_id": "p1-014"},
        ],
        "data-pipeline": [
            {"timestamp": "2024-04-01T03:16:00Z", "level": "ERROR", "service": "data-pipeline", "message": "Job failed: cannot authenticate with internal API — 401 Unauthorized", "trace_id": "p1-020"},
            {"timestamp": "2024-04-01T03:18:00Z", "level": "ERROR", "service": "data-pipeline", "message": "Job failed: cannot authenticate with internal API — 401 Unauthorized", "trace_id": "p1-021"},
            {"timestamp": "2024-04-01T03:20:00Z", "level": "WARN",  "service": "data-pipeline", "message": "Job queue depth: 847 jobs pending", "trace_id": None},
        ],
        "notification-service": [
            {"timestamp": "2024-04-01T03:17:00Z", "level": "ERROR", "service": "notification-service", "message": "Failed to send — auth token invalid (401 from api-gateway)", "trace_id": "p1-030"},
            {"timestamp": "2024-04-01T03:19:00Z", "level": "ERROR", "service": "notification-service", "message": "Retry failed — auth token invalid (401 from api-gateway)", "trace_id": "p1-031"},
        ],
        # Red herring service — has errors but unrelated
        "reporting-service": [
            {"timestamp": "2024-04-01T02:55:00Z", "level": "ERROR", "service": "reporting-service", "message": "Nightly report generation failed: out of memory", "trace_id": "p1-040"},
        ]
    },
    "metrics": {
        "api-gateway": [
            {"timestamp": "2024-04-01T03:20:00Z", "service": "api-gateway", "metric_name": "error_rate",         "value": 40.0, "unit": "percent"},
            {"timestamp": "2024-04-01T03:20:00Z", "service": "api-gateway", "metric_name": "upstream_healthy",   "value": 0.0,  "unit": "count"},
        ],
        "auth-service": [
            {"timestamp": "2024-04-01T03:20:00Z", "service": "auth-service", "metric_name": "auth_success_rate", "value": 0.0,   "unit": "percent"},
            {"timestamp": "2024-04-01T03:20:00Z", "service": "auth-service", "metric_name": "jwks_cache_age",    "value": 3602,  "unit": "seconds"},
            {"timestamp": "2024-04-01T03:20:00Z", "service": "auth-service", "metric_name": "cpu_percent",       "value": 12.0,  "unit": "percent"},  # Red herring: auth CPU is fine
        ],
        "data-pipeline": [
            {"timestamp": "2024-04-01T03:20:00Z", "service": "data-pipeline", "metric_name": "job_queue_depth",  "value": 847.0, "unit": "count"},
            {"timestamp": "2024-04-01T03:20:00Z", "service": "data-pipeline", "metric_name": "jobs_completed",   "value": 0.0,   "unit": "count"},
        ]
    },
    "deployments": {
        "api-gateway": [
            {"deployed_at": "2024-04-01T02:00:00Z", "service": "api-gateway", "version": "v6.2.0", "deployed_by": "ci-bot", "change_summary": "Rate limit config update — no code changes", "rolled_back": False},
        ],
        "auth-service": [
            {"deployed_at": "2024-03-31T23:00:00Z", "service": "auth-service", "version": "v5.1.0", "deployed_by": "ci-bot", "change_summary": "Routine patch — no auth logic changes", "rolled_back": False},
        ],
        # THE ROOT CAUSE: key-store-service was redeployed with a bad config
        "key-store-service": [
            {"deployed_at": "2024-04-01T03:10:00Z", "service": "key-store-service", "version": "v1.4.0", "deployed_by": "platform-team", "change_summary": "Updated TLS certificate config — changed listening port from 8443 to 9443 without updating service discovery", "rolled_back": False},
        ],
        "data-pipeline": [
            {"deployed_at": "2024-03-28T10:00:00Z", "service": "data-pipeline", "version": "v2.8.3", "deployed_by": "ci-bot", "change_summary": "Performance optimisation", "rolled_back": False},
        ]
    },
    "runbook": {
        "alert_type": "platform_wide_auth_failure",
        "steps": [
            {"step": 1, "instruction": "Check api-gateway logs — identify which upstream is unhealthy",         "expected_outcome": "Find auth-service as the unhealthy upstream"},
            {"step": 2, "instruction": "Check auth-service logs — identify what auth-service depends on",       "expected_outcome": "Find key-store-service JWKS fetch failures"},
            {"step": 3, "instruction": "Check key-store-service deployments for recent changes",                "expected_outcome": "Find recent port change in key-store-service"},
            {"step": 4, "instruction": "Roll back key-store-service to previous version",                       "expected_outcome": "Auth-service JWKS refresh succeeds, cascading failures resolve"},
            {"step": 5, "instruction": "Verify all downstream services recover after auth is restored",         "expected_outcome": "api-gateway 503s stop, data-pipeline resumes, notifications resume"},
        ]
    },
    "ground_truth": {
        "root_cause_keywords": ["key-store", "jwks", "port", "tls", "certificate", "auth", "cascade"],
        "affected_services": ["api-gateway", "auth-service", "data-pipeline", "notification-service"],
        "correct_severity": "P1",
        "correct_escalation": "rollback",
        "required_queries": ["query_logs", "query_deployments"],
    }
}


ALL_TASKS = {
    "task_easy":   TASK_EASY,
    "task_medium": TASK_MEDIUM,
    "task_hard":   TASK_HARD,
}
