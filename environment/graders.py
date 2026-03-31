"""

Graders for the SRE Triage Pipeline environment.

Each grader takes the agent's submitted diagnosis and the scenario's
ground truth, and returns a score between 0.0 and 1.0 with a breakdown.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _keyword_overlap_score(text: str, keywords: List[str]) -> float:
    """Score how many ground-truth keywords appear in the agent's text."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return hits / len(keywords)


def _service_overlap_score(
    predicted: List[str], ground_truth: List[str]
) -> float:
    """Jaccard similarity between predicted and ground truth service lists."""
    if not ground_truth:
        return 1.0
    pred_set = {s.lower() for s in (predicted or [])}
    truth_set = {s.lower() for s in ground_truth}
    intersection = pred_set & truth_set
    union = pred_set | truth_set
    if not union:
        return 0.0
    return len(intersection) / len(union)


def grade(
    diagnosis: Dict[str, Any],
    ground_truth: Dict[str, Any],
    state_info: Dict[str, Any],
) -> Tuple[float, Dict[str, float], str]:
    """
    Grade the agent's final diagnosis.

    Parameters
    ----------
    diagnosis : dict
        The agent's submitted diagnosis fields:
          - root_cause (str)
          - affected_services (list[str])
          - severity_assessment (str)
          - escalation_decision (str)
          - runbook_followed (str, optional)
    ground_truth : dict
        The scenario's ground truth (from scenarios.py).
    state_info : dict
        Episode state info:
          - step_count (int)
          - queried_logs (list[str])
          - queried_metrics (list[str])
          - queried_deployments (list[str])
          - queried_runbook (bool)

    Returns
    -------
    (total_score, breakdown, feedback)
    """
    breakdown: Dict[str, float] = {}
    feedback_parts: List[str] = []

    # ------------------------------------------------------------------
    # 1. Root cause accuracy (35%)
    #    Does the agent's root_cause text contain the key keywords?
    # ------------------------------------------------------------------
    root_cause_text = diagnosis.get("root_cause", "") or ""
    rc_score = _keyword_overlap_score(
        root_cause_text, ground_truth["root_cause_keywords"]
    )
    breakdown["root_cause_accuracy"] = round(rc_score, 3)
    if rc_score >= 0.6:
        feedback_parts.append("Root cause correctly identified.")
    elif rc_score >= 0.3:
        feedback_parts.append("Root cause partially identified — missing key details.")
    else:
        feedback_parts.append("Root cause not identified or significantly incorrect.")

    # ------------------------------------------------------------------
    # 2. Affected services (20%)
    #    Jaccard similarity with ground truth service list
    # ------------------------------------------------------------------
    svc_score = _service_overlap_score(
        diagnosis.get("affected_services", []),
        ground_truth["affected_services"],
    )
    breakdown["affected_services"] = round(svc_score, 3)
    if svc_score >= 0.8:
        feedback_parts.append("Affected services correctly identified.")
    else:
        feedback_parts.append(
            f"Affected services incomplete. Expected: {ground_truth['affected_services']}"
        )

    # ------------------------------------------------------------------
    # 3. Severity assessment (15%)
    #    Exact match = 1.0, one level off = 0.5, more = 0.0
    # ------------------------------------------------------------------
    severity_order = ["P4", "P3", "P2", "P1"]
    predicted_sev = diagnosis.get("severity_assessment", "") or ""
    correct_sev = ground_truth["correct_severity"]
    if predicted_sev == correct_sev:
        sev_score = 1.0
        feedback_parts.append("Severity correctly assessed.")
    elif predicted_sev in severity_order and correct_sev in severity_order:
        diff = abs(severity_order.index(predicted_sev) - severity_order.index(correct_sev))
        sev_score = max(0.0, 1.0 - diff * 0.5)
        feedback_parts.append(
            f"Severity off by {diff} level(s). Expected {correct_sev}, got {predicted_sev}."
        )
    else:
        sev_score = 0.0
        feedback_parts.append(f"Severity missing or invalid. Expected {correct_sev}.")
    breakdown["severity_assessment"] = round(sev_score, 3)

    # ------------------------------------------------------------------
    # 4. Escalation decision (20%)
    #    Exact match = 1.0, else 0.0
    # ------------------------------------------------------------------
    predicted_esc = diagnosis.get("escalation_decision", "") or ""
    correct_esc = ground_truth["correct_escalation"]
    esc_score = 1.0 if predicted_esc == correct_esc else 0.0
    breakdown["escalation_decision"] = esc_score
    if esc_score == 1.0:
        feedback_parts.append("Correct escalation decision.")
    else:
        feedback_parts.append(
            f"Wrong escalation. Expected '{correct_esc}', got '{predicted_esc}'."
        )

    # ------------------------------------------------------------------
    # 5. Investigation thoroughness (10%)
    #    Did the agent query the required data sources?
    # ------------------------------------------------------------------
    required = set(ground_truth.get("required_queries", []))
    performed = set()
    if state_info.get("queried_logs"):
        performed.add("query_logs")
    if state_info.get("queried_metrics"):
        performed.add("query_metrics")
    if state_info.get("queried_deployments"):
        performed.add("query_deployments")
    if state_info.get("queried_runbook"):
        performed.add("query_runbook")

    if required:
        thoroughness = len(required & performed) / len(required)
    else:
        thoroughness = 1.0
    breakdown["investigation_thoroughness"] = round(thoroughness, 3)
    if thoroughness == 1.0:
        feedback_parts.append("All required investigation steps performed.")
    else:
        missing = required - performed
        feedback_parts.append(f"Missing investigation steps: {missing}")

    # ------------------------------------------------------------------
    # Penalties
    # ------------------------------------------------------------------
    penalty = 0.0

    # Penalty: submitted diagnosis without querying anything (lazy agent)
    total_queries = (
        len(state_info.get("queried_logs", []))
        + len(state_info.get("queried_metrics", []))
        + len(state_info.get("queried_deployments", []))
    )
    if total_queries == 0:
        penalty += 0.15
        feedback_parts.append("PENALTY: Submitted diagnosis without querying any data.")

    # Penalty: too many steps (> 15 = inefficient/looping)
    step_count = state_info.get("step_count", 0)
    if step_count > 15:
        excess = step_count - 15
        loop_penalty = min(0.10, excess * 0.01)
        penalty += loop_penalty
        feedback_parts.append(f"PENALTY: Excessive steps ({step_count}). Penalty: {loop_penalty:.2f}")

    # ------------------------------------------------------------------
    # Weighted total
    # ------------------------------------------------------------------
    weights = {
        "root_cause_accuracy":        0.35,
        "affected_services":          0.20,
        "severity_assessment":        0.15,
        "escalation_decision":        0.20,
        "investigation_thoroughness": 0.10,
    }
    total = sum(breakdown[k] * w for k, w in weights.items())
    total = max(0.0, min(1.0, total - penalty))
    breakdown["penalty"] = round(penalty, 3)
    breakdown["total"] = round(total, 3)

    feedback = " | ".join(feedback_parts)
    return round(total, 3), breakdown, feedback
