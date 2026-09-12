"""LIMIT-006 downgrade streak tracker (H-1).

Counts the consecutive-pass streak of the stress-macos evidence step
("LIMIT-006 qtbot stress (evidence collection, may crash)") across recent
main-branch runs and reports it to the step summary + a notice annotation.

Decision rule (KNOWN_ISSUES.md LIMIT-006 / D-3): **5 consecutive passes**
→ remove the darwin skips; any failure resets the streak and the faulthandler
stack / .ips from that run becomes the new evidence.

Standard library only; reads the public Actions API (GITHUB_TOKEN used when
present for a higher rate limit). Runs inside the stress job, but works
locally for manual audits::

    GITHUB_REPOSITORY=Rookievegetable/PhotoArchiver python scripts/limit006_streak.py
"""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

REPO = os.environ.get("GITHUB_REPOSITORY", "Rookievegetable/PhotoArchiver")
API = f"https://api.github.com/repos/{REPO}/actions/runs"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
STRESS_JOB_NAME = "macos stress (no qtbot)"
EVIDENCE_STEP_NAME = "LIMIT-006 qtbot stress (evidence collection, may crash)"
TARGET_STREAK = 5
MAX_RUNS = 30


def _api(url: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _evidence_outcomes() -> list[tuple[int, str]]:
    """Return (run_number, outcome) for every run that has the evidence step.

    Ordered newest first. Stops at the first run whose stress job (or step)
    does not exist — anything older predates the experiment and cannot count.
    """
    payload = _api(f"{API}?branch=main&per_page={MAX_RUNS}")
    outcomes: list[tuple[int, str]] = []
    for run in payload.get("workflow_runs", []):
        if run["event"] not in ("push", "workflow_dispatch"):
            continue
        jobs = _api(run["jobs_url"])
        stress = next(
            (job for job in jobs.get("jobs", []) if job["name"] == STRESS_JOB_NAME),
            None,
        )
        if stress is None:
            break
        step = next(
            (s for s in stress.get("steps", []) if s["name"] == EVIDENCE_STEP_NAME),
            None,
        )
        if step is None:
            break
        outcomes.append((run["run_number"], step["conclusion"] or "in_progress"))
    return outcomes


def main() -> int:
    outcomes = _evidence_outcomes()

    # Current run first (the tracker runs after the evidence step inside the
    # same job — its outcome is still "in_progress" via the API, so the live
    # result arrives through the EVIDENCE_OUTCOME env var).
    current = os.environ.get("EVIDENCE_OUTCOME", "")
    current_run = os.environ.get("GITHUB_RUN_ID")
    streak = 0
    history: list[str] = []
    if current and current_run:
        history.append(f"current({current_run})={current}")
        if current == "success":
            streak += 1
        else:
            streak = -10_000  # current failure breaks the streak outright

    for run_number, conclusion in outcomes:
        if conclusion != "success":
            if current_run and str(run_number) == current_run:
                continue  # already counted via EVIDENCE_OUTCOME
            history.append(f"#{run_number}={conclusion} <- streak reset")
            break
        history.append(f"#{run_number}=success")
        streak += 1
    streak = max(streak, 0)

    verdict = (
        f"DOWNGRADE CRITERION MET ({streak} consecutive passes) — remove the darwin skips"
        if streak >= TARGET_STREAK
        else f"{streak}/{TARGET_STREAK} consecutive passes — darwin skips stay"
    )
    lines = ["| run | evidence step |", "|---|---|", *[f"| {h.split('=', 1)[0]} | {h.split('=', 1)[1]} |" for h in history]]
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("### LIMIT-006 evidence streak\n\n" + "\n".join(lines) + "\n\n")
    print("LIMIT-006 evidence history (newest first):")
    for entry in history:
        print("  ", entry)
    print(verdict)
    # notice annotation — publicly readable via the check-run annotations API.
    print(f"::notice::LIMIT-006 streak: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
