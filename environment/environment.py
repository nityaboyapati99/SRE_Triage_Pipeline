"""
SRE Triage Pipeline — Core Environment
========================================
Implements the OpenEnv interface:
  reset()  -> TriageObservation
  step()   -> TriageObservation
  state    -> TriageState
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from data.scenarios import ALL_TASKS
from environment.graders import grade
from models import (
    ActionType,
    DeploymentRecord,
    EscalationDecision,
    LogEntry,
    MetricSnapshot,
    RunbookEntry,
    Severity,
    TriageAction,
    TriageObservation,
    TriageState,
)


class SRETriageEnvironment:
    """
    SRE Triage Pipeline OpenEnv environment.

    The agent receives an incident alert and must:
    1. Query logs, metrics, and/or deployments to investigate
    2. Look up the runbook if needed
    3. Submit a diagnosis with root cause, affected services,
       severity, and escalation decision

    Episode ends when submit_diagnosis is called.
    """

    def __init__(self, task_id: str = "task_easy"):
        if task_id not in ALL_TASKS:
            raise ValueError(f"Unknown task_id '{task_id}'. Valid: {list(ALL_TASKS)}")
        self._task_id = task_id
        self._scenario: Dict[str, Any] = ALL_TASKS[task_id]
        self._state = TriageState(task_id=task_id)

    # ------------------------------------------------------------------
    # OpenEnv interface
    # ------------------------------------------------------------------

    def reset(self, episode_id: Optional[str] = None) -> TriageObservation:
        """Start a new episode. Returns the initial alert observation."""
        self._state = TriageState(
            episode_id=episode_id or str(uuid.uuid4()),
            task_id=self._task_id,
            step_count=0,
            done=False,
        )
        alert = self._scenario["alert"]
        return TriageObservation(
            done=False,
            reward=None,
            alert_title=alert["title"],
            alert_description=alert["description"],
            alert_severity=Severity(alert["severity"]),
            triggered_at=alert["triggered_at"],
            services_in_scope=alert["services_in_scope"],
            metadata={"task_id": self._task_id, "step": 0},
        )

    def step(self, action: TriageAction) -> TriageObservation:
        """Execute one agent action and return the resulting observation."""
        if self._state.done:
            return TriageObservation(
                done=True,
                reward=self._state.final_score,
                metadata={"error": "Episode already finished. Call reset() to start a new episode."},
            )

        self._state.step_count += 1
        action_type = action.action_type

        # -- Investigation actions --
        if action_type == ActionType.QUERY_LOGS:
            return self._handle_query_logs(action)

        elif action_type == ActionType.QUERY_METRICS:
            return self._handle_query_metrics(action)

        elif action_type == ActionType.QUERY_DEPLOYMENTS:
            return self._handle_query_deployments(action)

        elif action_type == ActionType.QUERY_RUNBOOK:
            return self._handle_query_runbook(action)

        # -- Terminal action --
        elif action_type == ActionType.SUBMIT_DIAGNOSIS:
            return self._handle_submit_diagnosis(action)

        else:
            return TriageObservation(
                done=False,
                reward=None,
                metadata={"error": f"Unknown action_type: {action_type}"},
            )

    @property
    def state(self) -> TriageState:
        """Return current episode state."""
        return self._state

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_query_logs(self, action: TriageAction) -> TriageObservation:
        service = action.service_name
        all_logs = self._scenario.get("logs", {})

        if service and service in all_logs:
            raw_entries = all_logs[service]
            log_entries = [LogEntry(**e) for e in raw_entries]
            if service not in self._state.queried_logs:
                self._state.queried_logs.append(service)
            feedback = f"Retrieved {len(log_entries)} log entries for '{service}'."
        elif service:
            log_entries = []
            feedback = f"No logs found for service '{service}'."
        else:
            # Return logs for all services
            log_entries = []
            for svc, entries in all_logs.items():
                log_entries.extend([LogEntry(**e) for e in entries])
                if svc not in self._state.queried_logs:
                    self._state.queried_logs.append(svc)
            feedback = f"Retrieved {len(log_entries)} log entries across all services."

        # Partial reward for investigating
        partial_reward = self._compute_partial_reward()

        return TriageObservation(
            done=False,
            reward=partial_reward,
            logs=log_entries,
            metadata={"step": self._state.step_count, "feedback": feedback},
        )

    def _handle_query_metrics(self, action: TriageAction) -> TriageObservation:
        service = action.service_name
        all_metrics = self._scenario.get("metrics", {})

        if service and service in all_metrics:
            raw = all_metrics[service]
            metric_entries = [MetricSnapshot(**m) for m in raw]
            if service not in self._state.queried_metrics:
                self._state.queried_metrics.append(service)
            feedback = f"Retrieved {len(metric_entries)} metric snapshots for '{service}'."
        elif service:
            metric_entries = []
            feedback = f"No metrics found for service '{service}'."
        else:
            metric_entries = []
            for svc, entries in all_metrics.items():
                metric_entries.extend([MetricSnapshot(**m) for m in entries])
                if svc not in self._state.queried_metrics:
                    self._state.queried_metrics.append(svc)
            feedback = f"Retrieved {len(metric_entries)} metric snapshots across all services."

        partial_reward = self._compute_partial_reward()

        return TriageObservation(
            done=False,
            reward=partial_reward,
            metrics=metric_entries,
            metadata={"step": self._state.step_count, "feedback": feedback},
        )

    def _handle_query_deployments(self, action: TriageAction) -> TriageObservation:
        service = action.service_name
        all_deployments = self._scenario.get("deployments", {})

        if service and service in all_deployments:
            raw = all_deployments[service]
            deploy_entries = [DeploymentRecord(**d) for d in raw]
            if service not in self._state.queried_deployments:
                self._state.queried_deployments.append(service)
            feedback = f"Retrieved {len(deploy_entries)} deployment records for '{service}'."
        elif service:
            deploy_entries = []
            feedback = f"No deployment records for service '{service}'."
        else:
            deploy_entries = []
            for svc, entries in all_deployments.items():
                deploy_entries.extend([DeploymentRecord(**d) for d in entries])
                if svc not in self._state.queried_deployments:
                    self._state.queried_deployments.append(svc)
            feedback = f"Retrieved {len(deploy_entries)} deployment records across all services."

        partial_reward = self._compute_partial_reward()

        return TriageObservation(
            done=False,
            reward=partial_reward,
            deployments=deploy_entries,
            metadata={"step": self._state.step_count, "feedback": feedback},
        )

    def _handle_query_runbook(self, action: TriageAction) -> TriageObservation:
        runbook = self._scenario.get("runbook", {})
        steps = [RunbookEntry(**s) for s in runbook.get("steps", [])]
        self._state.queried_runbook = True

        partial_reward = self._compute_partial_reward()

        return TriageObservation(
            done=False,
            reward=partial_reward,
            runbook_steps=steps,
            metadata={
                "step": self._state.step_count,
                "alert_type": runbook.get("alert_type", "unknown"),
                "feedback": f"Runbook retrieved: {len(steps)} steps.",
            },
        )

    def _handle_submit_diagnosis(self, action: TriageAction) -> TriageObservation:
        self._state.diagnosis_submitted = True

        diagnosis = {
            "root_cause":          action.root_cause,
            "affected_services":   action.affected_services or [],
            "severity_assessment": action.severity_assessment,
            "escalation_decision": action.escalation_decision,
            "runbook_followed":    action.runbook_followed,
        }

        state_info = {
            "step_count":          self._state.step_count,
            "queried_logs":        self._state.queried_logs,
            "queried_metrics":     self._state.queried_metrics,
            "queried_deployments": self._state.queried_deployments,
            "queried_runbook":     self._state.queried_runbook,
        }

        score, breakdown, feedback = grade(
            diagnosis,
            self._scenario["ground_truth"],
            state_info,
        )

        self._state.final_score = score
        self._state.done = True

        return TriageObservation(
            done=True,
            reward=score,
            score_breakdown=breakdown,
            grader_feedback=feedback,
            metadata={
                "step": self._state.step_count,
                "task_id": self._task_id,
                "final_score": score,
            },
        )

    # ------------------------------------------------------------------
    # Reward shaping
    # ------------------------------------------------------------------

    def _compute_partial_reward(self) -> float:
        """
        Give a small positive signal for each unique data source queried.
        This rewards the agent for investigating before diagnosing.
        Max partial reward = 0.15 (investigation bonus on top of grader score).
        """
        sources_queried = 0
        if self._state.queried_logs:
            sources_queried += 1
        if self._state.queried_metrics:
            sources_queried += 1
        if self._state.queried_deployments:
            sources_queried += 1
        if self._state.queried_runbook:
            sources_queried += 1
        return round(sources_queried * 0.025, 3)  # 0.025 per unique source type
