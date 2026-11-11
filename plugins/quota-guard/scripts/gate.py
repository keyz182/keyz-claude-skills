"""PreToolUse hook (Agent|Task|Workflow): ask or deny when quota is nearly used up.

Fails open: any error prints nothing and exits 0, so the tool runs as normal.
"""
from __future__ import annotations

import json
import os
import sys
import time

import quota_lib as q


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool = payload.get("tool_name") or "This tool"
    now = time.time()
    state = q.state_dir()
    model = q.load(state, now, os.environ)
    if model is None:
        return
    decision = q.gate_decision(state, model, q.read_history(state), now, os.environ, tool)
    if decision:
        print(json.dumps(decision))


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001 - a hook bug must never block the tool
        q.debug(f"gate crashed: {type(err).__name__}: {err}")
    sys.exit(0)
