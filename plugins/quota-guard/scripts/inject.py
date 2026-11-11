"""UserPromptSubmit / SessionStart hook: add quota and context-window status lines.

Fails open: any error prints nothing and exits 0.
"""
from __future__ import annotations

import json
import os
import sys
import time

import quota_lib as q

WARNING = (
    "Quota warning: the user's subscription quota is running low. Prefer cheap tools, "
    "avoid sub-agent fan-out and large reads, and checkpoint progress (commit or note "
    "state) so work can resume after the reset."
)
UNKNOWN = "Quota: unknown (no fresh status-line snapshot; see quota-guard README)"


def parse_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> None:
    payload = parse_payload(sys.stdin.read())
    print_quota(payload.get("hook_event_name"))
    known = q.snapshot_context_size(q.state_dir(), payload.get("session_id"))
    usage = q.context_usage(payload.get("transcript_path"), os.environ, known)
    if usage:
        print(q.format_context_line(usage))


def print_quota(event: str | None) -> None:
    now = time.time()
    state = q.state_dir()
    model = q.load(state, now, os.environ)
    if model is None:
        if event == "SessionStart":  # say it once per session, not on every prompt
            print(UNKNOWN)
        return
    q.record_history(state, model, now)
    assessment = q.assess(model, q.read_history(state), now, os.environ)
    print(q.format_line(model, assessment, now))
    if assessment["level"] != "ok":
        print(WARNING)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001 - a hook bug must never block the prompt
        q.debug(f"inject crashed: {type(err).__name__}: {err}")
    sys.exit(0)
