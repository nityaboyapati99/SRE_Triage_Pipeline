"""
SRE Triage Pipeline — FastAPI Server
======================================
Exposes the OpenEnv HTTP interface:
  POST /reset          — start a new episode
  POST /step           — take an action
  GET  /state          — get current state
  GET  /tasks          — list available tasks
  POST /grader         — standalone grader endpoint
  GET  /               — health check
  GET  /health         — health check
"""

from __future__ import annotations

import sys
import os

# Ensure root is on path so imports work inside the container
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data.scenarios import ALL_TASKS
from environment.environment import SRETriageEnvironment
from environment.graders import grade
from models import TriageAction, TriageObservation, TriageState

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SRE Triage Pipeline",
    description=(
        "OpenEnv-compliant environment where AI agents diagnose production incidents. "
        "Three tasks of increasing difficulty: single-service failure, "
        "cross-service cascading failure, and platform-wide outage with red herrings."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One environment instance per process (single-session server)
_env: Optional[SRETriageEnvironment] = None


def get_env() -> SRETriageEnvironment:
    global _env
    if _env is None:
        _env = SRETriageEnvironment(task_id="task_easy")
    return _env


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    task_id: str = "task_easy"
    episode_id: Optional[str] = None


class StepRequest(BaseModel):
    action: Dict[str, Any]


class GraderRequest(BaseModel):
    task_id: str
    diagnosis: Dict[str, Any]
    state_info: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"])
@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": "sre-triage-pipeline", "version": "1.0.0"}


@app.get("/tasks", tags=["tasks"])
def list_tasks():
    """Return metadata for all available tasks."""
    return {
        "tasks": [
            {
                "task_id":    "task_easy",
                "name":       "Basic Incident Triage",
                "difficulty": "easy",
                "description": (
                    "Single service (payment-service) is returning 500 errors. "
                    "Root cause is clearly visible in logs. "
                    "Requires: query logs, identify DB connection exhaustion, page on-call."
                ),
                "services": ["payment-service"],
                "pass_threshold": 0.70,
            },
            {
                "task_id":    "task_medium",
                "name":       "Cross-Service Cascading Failure",
                "difficulty": "medium",
                "description": (
                    "checkout-service is timing out due to a failing upstream inventory-service. "
                    "Redis cache has crashed, causing CPU spike. "
                    "Requires: correlate logs + metrics across two services."
                ),
                "services": ["checkout-service", "inventory-service"],
                "pass_threshold": 0.65,
            },
            {
                "task_id":    "task_hard",
                "name":       "Platform-Wide Outage with Red Herrings",
                "difficulty": "hard",
                "description": (
                    "Multiple services failing simultaneously. "
                    "Root cause is a misconfigured key-store-service deployment "
                    "breaking auth chain. Red herring errors in unrelated services. "
                    "Requires: trace dependency chain across 4 services + check deployments."
                ),
                "services": ["api-gateway", "auth-service", "data-pipeline", "notification-service"],
                "pass_threshold": 0.55,
            },
        ]
    }


@app.post("/reset", tags=["env"])
def reset(req: Optional[ResetRequest] = Body(default=None)):
    """Reset the environment and start a new episode."""
    if req is None:
        req = ResetRequest()
    global _env
    if req.task_id not in ALL_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task_id '{req.task_id}'. Valid: {list(ALL_TASKS.keys())}"
        )
    _env = SRETriageEnvironment(task_id=req.task_id)
    obs = _env.reset(episode_id=req.episode_id)
    return {
        "observation": obs.model_dump(),
    }


@app.post("/step", tags=["env"])
def step(req: StepRequest):
    """Execute one action in the environment."""
    env = get_env()
    try:
        action = TriageAction(**req.action)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid action: {e}")
    obs = env.step(action)
    return {
        "observation": obs.model_dump(),
        "reward": obs.reward,
        "done": obs.done,
        "info": obs.metadata,
    }


@app.get("/state", response_model=TriageState, tags=["env"])
def get_state():
    """Return the current episode state."""
    return get_env().state


@app.post("/grader", tags=["grader"])
def run_grader(req: GraderRequest):
    """
    Standalone grader endpoint.
    Grade a diagnosis against a task's ground truth without running an episode.
    """
    if req.task_id not in ALL_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task_id '{req.task_id}'."
        )
    scenario = ALL_TASKS[req.task_id]
    state_info = req.state_info or {}
    score, breakdown, feedback = grade(
        req.diagnosis,
        scenario["ground_truth"],
        state_info,
    )
    return {
        "task_id":   req.task_id,
        "score":     score,
        "breakdown": breakdown,
        "feedback":  feedback,
    }
