"""
Inference Script — SRE Triage Pipeline
========================================
MANDATORY environment variables:
  API_BASE_URL   The API endpoint for the LLM  (e.g. https://router.huggingface.co/v1)
  MODEL_NAME     The model identifier           (e.g. meta-llama/Llama-3.3-70B-Instruct)
  HF_TOKEN       Your Hugging Face / API key

Runs the baseline agent against all 3 tasks and prints scores.
Must complete in < 20 minutes on 2 vCPU / 8 GB RAM.
"""

from __future__ import annotations

import json

from dotenv import load_dotenv
load_dotenv()
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE_URL: str = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME:   str = os.environ.get("MODEL_NAME",   "meta-llama/Llama-3.3-70B-Instruct")
HF_TOKEN:     str = os.environ.get("HF_TOKEN",     os.environ.get("API_KEY", ""))
ENV_BASE_URL: str = os.environ.get("ENV_BASE_URL", "http://localhost:7860")

MAX_STEPS_PER_TASK = 10
TEMPERATURE        = 0.2
MAX_TOKENS         = 1024

TASKS = ["task_easy", "task_medium", "task_hard"]

# ---------------------------------------------------------------------------
# OpenAI client (used for ALL LLM calls)
# ---------------------------------------------------------------------------

import httpx

client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN,
    http_client=httpx.Client(verify=False),
)

# ---------------------------------------------------------------------------
# Environment HTTP helpers
# ---------------------------------------------------------------------------

def env_reset(task_id: str) -> Dict[str, Any]:
    resp = requests.post(
        f"{ENV_BASE_URL}/reset",
        json={"task_id": task_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def env_step(action: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.post(
        f"{ENV_BASE_URL}/step",
        json={"action": action},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def env_state() -> Dict[str, Any]:
    resp = requests.get(f"{ENV_BASE_URL}/state", timeout=10)
    resp.raise_for_status()
    return resp.json()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) triaging a production incident.

You have access to these investigation tools (call them as JSON actions):
1. query_logs        — get log entries for a service
2. query_metrics     — get metrics for a service
3. query_deployments — get recent deployments for a service
4. query_runbook     — get the runbook for this incident type
5. submit_diagnosis  — submit your final diagnosis (terminates the episode)

You MUST investigate before diagnosing. Always query logs first, then metrics and deployments as needed.

When you are ready to submit your diagnosis, use submit_diagnosis with:
  - root_cause: clear description of what caused the incident
  - affected_services: list of impacted service names
  - severity_assessment: P1 / P2 / P3 / P4
  - escalation_decision: one of [auto_resolve, page_on_call, rollback, scale_up, notify_only]

Respond ONLY with a JSON object matching one of these action schemas:

Query action:
{"action_type": "query_logs", "service_name": "<service>"}
{"action_type": "query_metrics", "service_name": "<service>"}
{"action_type": "query_deployments", "service_name": "<service>"}
{"action_type": "query_runbook"}

Diagnosis action:
{
  "action_type": "submit_diagnosis",
  "root_cause": "<your diagnosis>",
  "affected_services": ["<svc1>", "<svc2>"],
  "severity_assessment": "<P1|P2|P3|P4>",
  "escalation_decision": "<decision>"
}

Do not include any explanation outside the JSON.
"""

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def observation_to_text(obs: Dict[str, Any]) -> str:
    """Convert an observation dict to a readable text for the LLM."""
    parts: List[str] = []

    if obs.get("alert_title"):
        parts.append(f"ALERT: {obs['alert_title']}")
        parts.append(f"Description: {obs['alert_description']}")
        parts.append(f"Severity: {obs['alert_severity']}  |  Triggered: {obs['triggered_at']}")
        parts.append(f"Services in scope: {', '.join(obs.get('services_in_scope', []))}")

    if obs.get("logs"):
        parts.append("\n--- LOGS ---")
        for entry in obs["logs"]:
            parts.append(f"[{entry['timestamp']}] [{entry['level']}] {entry['service']}: {entry['message']}")

    if obs.get("metrics"):
        parts.append("\n--- METRICS ---")
        for m in obs["metrics"]:
            parts.append(f"[{m['timestamp']}] {m['service']} / {m['metric_name']}: {m['value']} {m['unit']}")

    if obs.get("deployments"):
        parts.append("\n--- DEPLOYMENTS ---")
        for d in obs["deployments"]:
            parts.append(f"[{d['deployed_at']}] {d['service']} {d['version']} — {d['change_summary']}")

    if obs.get("runbook_steps"):
        parts.append("\n--- RUNBOOK ---")
        for s in obs["runbook_steps"]:
            parts.append(f"Step {s['step']}: {s['instruction']} → {s['expected_outcome']}")

    if obs.get("grader_feedback"):
        parts.append(f"\nGRADER FEEDBACK: {obs['grader_feedback']}")

    if obs.get("metadata", {}).get("feedback"):
        parts.append(f"[{obs['metadata']['feedback']}]")

    return "\n".join(parts)


def call_llm(messages: List[Dict[str, str]]) -> str:
    """Call LLM via OpenAI client and return the response text."""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  LLM ERROR detail: {type(e).__name__}: {e}")
        raise


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON action from LLM output."""
    text = text.strip()
    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


def run_task(task_id: str) -> float:
    """Run one full episode for a task. Returns the final score."""
    print(f"\n{'='*60}")
    print(f"TASK: {task_id}")
    print(f"{'='*60}")

    # Reset environment
    obs = env_reset(task_id)
    print(f"Alert: {obs.get('alert_title', 'N/A')}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": observation_to_text(obs)},
    ]

    final_score = 0.0

    for step_num in range(1, MAX_STEPS_PER_TASK + 1):
        print(f"\n[Step {step_num}]")

        # Get LLM action
        llm_output = call_llm(messages)
        print(f"  LLM output: {llm_output[:200]}{'...' if len(llm_output) > 200 else ''}")

        action = parse_action(llm_output)
        if action is None:
            print("  Failed to parse action — using fallback: query_logs")
            action = {"action_type": "query_logs"}

        print(f"  Action: {action.get('action_type', '?')}")

        # Execute action
        obs = env_step(action)

        obs_text = observation_to_text(obs)
        messages.append({"role": "assistant", "content": llm_output})
        messages.append({"role": "user",      "content": obs_text})

        if obs.get("done"):
            final_score = obs.get("reward", 0.0) or 0.0
            breakdown = obs.get("score_breakdown", {})
            print(f"\n  Episode complete!")
            print(f"  Score: {final_score:.3f}")
            if breakdown:
                for k, v in breakdown.items():
                    print(f"    {k}: {v}")
            print(f"  Feedback: {obs.get('grader_feedback', '')}")
            break

        # Check if we're at the last step — force diagnosis
        if step_num == MAX_STEPS_PER_TASK - 1:
            messages.append({
                "role": "user",
                "content": (
                    "You have one step remaining. "
                    "You MUST now submit your diagnosis using submit_diagnosis."
                )
            })

    return final_score


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # Check env server is up
    try:
        resp = requests.get(f"{ENV_BASE_URL}/health", timeout=10)
        resp.raise_for_status()
        print(f"Environment server: {resp.json()}")
    except Exception as e:
        print(f"ERROR: Cannot reach environment server at {ENV_BASE_URL}: {e}", file=sys.stderr)
        print("Start the server with: uvicorn server.app:app --host 0.0.0.0 --port 7860", file=sys.stderr)
        sys.exit(1)

    print(f"\nModel: {MODEL_NAME}")
    print(f"API:   {API_BASE_URL}")

    scores: Dict[str, float] = {}
    start_time = time.time()

    for task_id in TASKS:
        try:
            score = run_task(task_id)
            scores[task_id] = score
        except Exception as e:
            print(f"ERROR on {task_id}: {e}", file=sys.stderr)
            scores[task_id] = 0.0

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print("BASELINE RESULTS")
    print(f"{'='*60}")
    for task_id, score in scores.items():
        status = "PASS" if score >= 0.55 else "FAIL"
        print(f"  {task_id:<20} score={score:.3f}  [{status}]")
    avg = sum(scores.values()) / len(scores) if scores else 0.0
    print(f"  {'AVERAGE':<20} score={avg:.3f}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"{'='*60}")

    # Write results to file for reproducibility
    results = {
        "model":   MODEL_NAME,
        "api":     API_BASE_URL,
        "scores":  scores,
        "average": avg,
        "elapsed": elapsed,
    }
    with open("baseline_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to baseline_results.json")


if __name__ == "__main__":
    main()
