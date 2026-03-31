"""
SRE Triage Pipeline — Pydantic Models
======================================
Defines the typed Action, Observation, and State models
for the OpenEnv-compliant SRE Triage Pipeline environment.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    P1 = "P1"   # Critical — immediate action required
    P2 = "P2"   # High — action required within 30 min
    P3 = "P3"   # Medium — action required within 2 hours
    P4 = "P4"   # Low — action required within 24 hours


class EscalationDecision(str, Enum):
    AUTO_RESOLVE  = "auto_resolve"   # Agent can fix it, no human needed
    PAGE_ON_CALL  = "page_on_call"   # Wake the on-call engineer
    ROLLBACK      = "rollback"       # Roll back the last deployment
    SCALE_UP      = "scale_up"       # Increase resource capacity
    NOTIFY_ONLY   = "notify_only"    # Send notification, no urgent action


class ActionType(str, Enum):
    QUERY_LOGS        = "query_logs"        # Pull logs for a service
    QUERY_METRICS     = "query_metrics"     # Pull metrics for a service
    QUERY_DEPLOYMENTS = "query_deployments" # Pull recent deployments
    QUERY_RUNBOOK     = "query_runbook"     # Look up runbook for alert type
    SUBMIT_DIAGNOSIS  = "submit_diagnosis"  # Final answer: root cause + action


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

class TriageAction(BaseModel):
    """
    An action the agent can take inside the SRE Triage environment.

    Investigation actions (query_*) return data in the next observation.
    submit_diagnosis is the terminal action that ends the episode.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action_type: ActionType = Field(
        description="Which action to take"
    )

    # -- Parameters for query actions --
    service_name: Optional[str] = Field(
        default=None,
        description="Target service name for log/metric/deployment queries"
    )
    time_window_minutes: Optional[int] = Field(
        default=30,
        ge=1,
        le=180,
        description="How far back to query (minutes). Default 30."
    )

    # -- Parameters for submit_diagnosis (terminal action) --
    root_cause: Optional[str] = Field(
        default=None,
        description="Free-text description of the identified root cause"
    )
    affected_services: Optional[List[str]] = Field(
        default=None,
        description="List of service names the agent believes are affected"
    )
    severity_assessment: Optional[Severity] = Field(
        default=None,
        description="Agent's assessed severity of the incident"
    )
    escalation_decision: Optional[EscalationDecision] = Field(
        default=None,
        description="What action to take to resolve the incident"
    )
    runbook_followed: Optional[str] = Field(
        default=None,
        description="Name/ID of the runbook the agent followed, if any"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    """A single log line returned from a query_logs action."""
    timestamp: str
    level: str           # INFO, WARN, ERROR, CRITICAL
    service: str
    message: str
    trace_id: Optional[str] = None


class MetricSnapshot(BaseModel):
    """A metric data point returned from a query_metrics action."""
    timestamp: str
    service: str
    metric_name: str     # e.g. error_rate, latency_p99, cpu_percent
    value: float
    unit: str            # e.g. percent, ms, requests_per_sec


class DeploymentRecord(BaseModel):
    """A deployment event returned from a query_deployments action."""
    deployed_at: str
    service: str
    version: str
    deployed_by: str
    change_summary: str
    rolled_back: bool = False


class RunbookEntry(BaseModel):
    """A runbook step returned from a query_runbook action."""
    step: int
    instruction: str
    expected_outcome: str


class TriageObservation(BaseModel):
    """
    Observation returned after each step.

    On reset: contains the initial alert that triggered the incident.
    On query actions: contains the queried data.
    On submit_diagnosis: contains the graded score and feedback.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Episode control
    done: bool = Field(default=False, description="Whether the episode has ended")
    reward: Optional[float] = Field(
        default=None,
        description="Step reward (None until terminal action)"
    )

    # Initial alert (always present)
    alert_title: Optional[str] = Field(
        default=None,
        description="Alert title, e.g. 'P1 — checkout-service 500 error rate 45%'"
    )
    alert_description: Optional[str] = Field(
        default=None,
        description="Full alert description"
    )
    alert_severity: Optional[Severity] = Field(
        default=None,
        description="Severity of the incoming alert"
    )
    triggered_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the alert fired"
    )
    services_in_scope: Optional[List[str]] = Field(
        default=None,
        description="Services mentioned in the alert"
    )

    # Query results (populated based on action_type)
    logs: Optional[List[LogEntry]] = Field(
        default=None,
        description="Log entries returned by query_logs"
    )
    metrics: Optional[List[MetricSnapshot]] = Field(
        default=None,
        description="Metric snapshots returned by query_metrics"
    )
    deployments: Optional[List[DeploymentRecord]] = Field(
        default=None,
        description="Deployment records returned by query_deployments"
    )
    runbook_steps: Optional[List[RunbookEntry]] = Field(
        default=None,
        description="Runbook steps returned by query_runbook"
    )

    # Grader feedback (only on terminal submit_diagnosis)
    score_breakdown: Optional[Dict[str, float]] = Field(
        default=None,
        description="Per-component scores from the grader"
    )
    grader_feedback: Optional[str] = Field(
        default=None,
        description="Human-readable grader feedback"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class TriageState(BaseModel):
    """
    Internal episode state for the SRE Triage environment.
    Tracks what the agent has queried so far.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    episode_id: Optional[str] = Field(default=None)
    step_count: int = Field(default=0, ge=0)
    task_id: Optional[str] = Field(
        default=None,
        description="Active task: task_easy | task_medium | task_hard"
    )
    done: bool = Field(default=False)

    # What the agent has queried this episode
    queried_logs: List[str] = Field(
        default_factory=list,
        description="Service names for which logs were queried"
    )
    queried_metrics: List[str] = Field(
        default_factory=list,
        description="Service names for which metrics were queried"
    )
    queried_deployments: List[str] = Field(
        default_factory=list,
        description="Service names for which deployments were queried"
    )
    queried_runbook: bool = Field(
        default=False,
        description="Whether the agent looked up the runbook"
    )
    diagnosis_submitted: bool = Field(
        default=False,
        description="Whether the agent has submitted a final diagnosis"
    )
    final_score: Optional[float] = Field(
        default=None,
        description="Final episode score after submit_diagnosis"
    )
