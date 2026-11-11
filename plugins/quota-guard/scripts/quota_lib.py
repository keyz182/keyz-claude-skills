"""quota-guard core: read, merge and assess Claude subscription quota.

Data sources, in order:
  1. Per-session status-line snapshots in <state>/snapshots/<session_id>.json,
     written by the user's status-line script from Claude Code's documented
     `rate_limits` field.
  2. Opt-in (QUOTA_GUARD_OAUTH=1): the undocumented
     api.anthropic.com/api/oauth/usage endpoint, refreshed in a detached
     background process and read from <state>/oauth_cache.json.

Stdlib only. Run `python3 quota_lib.py --refresh` to refresh the OAuth cache.
"""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable, Mapping

WINDOWS = ("five_hour", "seven_day")
LABELS = {"five_hour": "5h", "seven_day": "7d"}
DEFAULTS = {
    "five_hour": {"warn": 80.0, "gate": 90.0},
    "seven_day": {"warn": 85.0, "gate": 95.0},
}
ENV_SUFFIX = {"five_hour": "5H", "seven_day": "7D"}
LOOKBACK = {"five_hour": 3600.0, "seven_day": 86400.0}

FRESH_S = 300  # snapshot younger than this: no fallback needed
STALE_MAX_S = 900  # data older than this is not shown at all
SNAPSHOT_PRUNE_S = 86400
OAUTH_TTL_S = 180
HISTORY_MIN_GAP_S = 60
HISTORY_KEEP_S = 8 * 86400
WINDOW_JITTER_S = 600
MIN_SPAN_S = 600
GATE_HORIZON_S = 1800
BAND = 5

CONTEXT_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
CONTEXT_DEFAULT = 200_000
CONTEXT_LARGE = 1_000_000
TRANSCRIPT_TAIL_BYTES = 512 * 1024

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"

Model = dict[str, Any]


def state_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    env = os.environ if env is None else env
    override = env.get("QUOTA_GUARD_DIR")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".claude" / "quota-guard"


def debug(msg: str) -> None:
    """Append to debug.log when QUOTA_GUARD_DEBUG=1. Never pass secrets here."""
    if os.environ.get("QUOTA_GUARD_DEBUG") != "1":
        return
    try:
        d = state_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "debug.log", "a") as fh:
            fh.write(f"{time.strftime('%F %T')} {msg}\n")
    except OSError:
        pass


def parse_ts(value: Any) -> float | None:
    """Epoch seconds from an epoch number or an ISO 8601 string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _window(pct: Any, resets_at: Any) -> dict[str, float] | None:
    ts = parse_ts(resets_at)
    if isinstance(pct, bool) or not isinstance(pct, (int, float)) or ts is None:
        return None
    return {"pct": float(pct), "resets_at": ts}


def normalise_statusline(rate_limits: Any) -> Model:
    if not isinstance(rate_limits, dict):
        return {}
    out: Model = {}
    for key in WINDOWS:
        raw = rate_limits.get(key)
        if isinstance(raw, dict):
            win = _window(raw.get("used_percentage"), raw.get("resets_at"))
            if win:
                out[key] = win
    return out


def normalise_oauth(resp: Any) -> Model:
    if not isinstance(resp, dict):
        return {}
    out: Model = {}
    for key in WINDOWS:
        raw = resp.get(key)
        if isinstance(raw, dict):
            win = _window(raw.get("utilization"), raw.get("resets_at"))
            if win:
                out[key] = win
    kinds = {"session": "five_hour", "weekly_all": "seven_day"}
    for item in resp.get("limits") or []:
        if isinstance(item, dict) and item.get("kind") in kinds:
            win = _window(item.get("percent"), item.get("resets_at"))
            if win:
                out[kinds[item["kind"]]] = win
    return out


def _read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _read_snapshot_entries(snap_dir: pathlib.Path, now: float) -> list[tuple[Model, float]]:
    """(normalised windows, written_at) per usable snapshot; prunes old files."""
    entries = []
    for path in snap_dir.glob("*.json"):
        doc = _read_json(path)
        written = parse_ts(doc.get("written_at")) if isinstance(doc, dict) else None
        if written is None:
            continue
        if now - written > SNAPSHOT_PRUNE_S:
            path.unlink(missing_ok=True)
            continue
        windows = normalise_statusline(doc.get("rate_limits"))
        if windows:
            entries.append((windows, written))
    return entries


def merge_window(candidates: list[tuple[dict[str, float], float]], now: float) -> tuple[dict[str, float], float] | None:
    """Pick one reading per window from several sessions.

    A session's copy is only as fresh as its own last API response, so last
    write does not win. Drop expired windows, keep the newest window (with
    jitter tolerance), and take the max pct: usage only rises inside a window.
    """
    live = [(w, ts) for w, ts in candidates if w["resets_at"] > now]
    if not live:
        return None
    newest = max(w["resets_at"] for w, _ in live)
    group = [(w, ts) for w, ts in live if w["resets_at"] >= newest - WINDOW_JITTER_S]
    pct = max(w["pct"] for w, _ in group)
    return {"pct": pct, "resets_at": newest}, max(ts for _, ts in group)


def load_snapshots(state: pathlib.Path, now: float) -> Model | None:
    entries = _read_snapshot_entries(state / "snapshots", now)
    model: Model = {}
    written_at = None
    for key in WINDOWS:
        merged = merge_window([(e[key], ts) for e, ts in entries if key in e], now)
        if merged:
            model[key], ts = merged
            written_at = ts if written_at is None else max(written_at, ts)
    if not model:
        return None
    model["written_at"] = written_at
    return model


def _load_oauth_cache(state: pathlib.Path, now: float) -> Model | None:
    doc = _read_json(state / "oauth_cache.json")
    if not isinstance(doc, dict):
        return None
    fetched = parse_ts(doc.get("fetched_at"))
    windows = normalise_oauth(doc.get("data"))
    windows = {k: w for k, w in windows.items() if w["resets_at"] > now}
    if fetched is None or not windows:
        return None
    return {**windows, "written_at": fetched}


def spawn_background_refresh() -> None:
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--refresh"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def load(
    state: pathlib.Path,
    now: float,
    env: Mapping[str, str],
    spawn_refresh: Callable[[], None] = spawn_background_refresh,
) -> Model | None:
    """Freshest usable reading, tagged with source and age_s, or None."""
    candidates = []
    snap = load_snapshots(state, now)
    if snap:
        candidates.append({**snap, "source": "statusline"})
    if env.get("QUOTA_GUARD_OAUTH") == "1" and (not snap or now - snap["written_at"] > FRESH_S):
        cache = _load_oauth_cache(state, now)
        if cache:
            candidates.append({**cache, "source": "oauth"})
        if not cache or now - cache["written_at"] > OAUTH_TTL_S:
            spawn_refresh()  # stale-while-revalidate: never wait on the network
    usable = [c for c in candidates if now - c["written_at"] <= STALE_MAX_S]
    if not usable:
        return None
    best = max(usable, key=lambda c: c["written_at"])
    best["age_s"] = now - best.pop("written_at")
    return best


# --- history and projection -------------------------------------------------


def read_history(state: pathlib.Path) -> list[dict[str, Any]]:
    try:
        lines = (state / "history.jsonl").read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("ts"), (int, float)):
            rows.append(row)
    return rows


def record_history(state: pathlib.Path, model: Model, now: float) -> None:
    rows = read_history(state)
    if rows and now - rows[-1]["ts"] < HISTORY_MIN_GAP_S:
        return
    row: dict[str, Any] = {"ts": now}
    for key in WINDOWS:
        if key in model:
            row[key] = [model[key]["pct"], model[key]["resets_at"]]
    rows = [r for r in rows if now - r["ts"] <= HISTORY_KEEP_S] + [row]
    state.mkdir(parents=True, exist_ok=True)
    tmp = state / f"history.jsonl.{os.getpid()}.tmp"
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    os.replace(tmp, state / "history.jsonl")


def project(
    history: list[dict[str, Any]],
    key: str,
    resets_at: float,
    now: float,
    lookback: float,
    pct: float | None = None,
) -> float | None:
    """Epoch when the window hits 100% at the current pace, or None.

    Least-squares slope over points from the same window within `lookback`.
    """
    pts = []
    for row in history:
        val = row.get(key)
        if not (isinstance(val, list) and len(val) == 2) or now - row["ts"] > lookback:
            continue
        if abs(val[1] - resets_at) <= WINDOW_JITTER_S:
            pts.append((row["ts"], float(val[0])))
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < MIN_SPAN_S:
        return None
    mean_t = sum(t for t, _ in pts) / len(pts)
    mean_p = sum(p for _, p in pts) / len(pts)
    var = sum((t - mean_t) ** 2 for t, _ in pts)
    slope = sum((t - mean_t) * (p - mean_p) for t, p in pts) / var
    if slope <= 0:
        return None
    current = pts[-1][1] if pct is None else pct
    return now + max(0.0, 100.0 - current) / slope


# --- assessment and output --------------------------------------------------


def threshold(env: Mapping[str, str], key: str, kind: str) -> float:
    raw = env.get(f"QUOTA_GUARD_{kind.upper()}_{ENV_SUFFIX[key]}")
    try:
        return float(raw) if raw else DEFAULTS[key][kind]
    except ValueError:
        return DEFAULTS[key][kind]


def _window_level(win: dict[str, float], eta: float | None, now: float, env: Mapping[str, str], key: str) -> str:
    runs_out = eta is not None and eta < win["resets_at"]
    if win["pct"] >= threshold(env, key, "gate") or (runs_out and eta - now <= GATE_HORIZON_S):
        return "gate"
    if win["pct"] >= threshold(env, key, "warn") or runs_out:
        return "warn"
    return "ok"


def assess(model: Model, history: list[dict[str, Any]], now: float, env: Mapping[str, str]) -> dict[str, Any]:
    order = ["ok", "warn", "gate"]
    windows = {}
    for key in WINDOWS:
        win = model.get(key)
        if not win:
            continue
        eta = project(history, key, win["resets_at"], now, LOOKBACK[key], pct=win["pct"])
        windows[key] = {**win, "eta": eta, "level": _window_level(win, eta, now, env, key)}
    level = max((w["level"] for w in windows.values()), key=order.index, default="ok")
    return {"level": level, "windows": windows}


def fmt_clock(ts: float, now: float) -> str:
    t, n = time.localtime(ts), time.localtime(now)
    same_day = (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday)
    return time.strftime("%H:%M" if same_day else "%a %H:%M", t)


def format_line(model: Model, assessment: dict[str, Any], now: float) -> str:
    parts = []
    for key, win in assessment["windows"].items():
        detail = f"resets {fmt_clock(win['resets_at'], now)}"
        if win["eta"] is not None and win["eta"] < win["resets_at"]:
            detail += f", ~{fmt_clock(win['eta'], now)} at current pace"
        parts.append(f"{LABELS[key]} {win['pct']:.0f}% ({detail})")
    return f"Quota: {' | '.join(parts)} [{model['source']}, {model['age_s']:.0f}s old]"


def _trigger(assessment: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    gated = [(k, w) for k, w in assessment["windows"].items() if w["level"] == "gate"]
    return max(gated, key=lambda kw: kw[1]["pct"])


def gate_decision(
    state: pathlib.Path,
    model: Model,
    history: list[dict[str, Any]],
    now: float,
    env: Mapping[str, str],
    tool: str,
) -> dict[str, Any] | None:
    """PreToolUse hook output, or None to stay out of the way."""
    mode = env.get("QUOTA_GUARD_GATE_MODE", "ask")
    if mode not in ("ask", "deny"):
        return None
    assessment = assess(model, history, now, env)
    if assessment["level"] != "gate":
        return None
    key, win = _trigger(assessment)
    if mode == "ask" and not _first_ask_in_band(state, key, win):
        return None
    reason = f"quota-guard: {LABELS[key]} quota at {win['pct']:.0f}% (resets {fmt_clock(win['resets_at'], now)})"
    if win["eta"] is not None and win["eta"] < win["resets_at"]:
        reason += f", projected to run out ~{fmt_clock(win['eta'], now)}"
    reason += f". {tool} can use a lot of quota."
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": mode,
            "permissionDecisionReason": reason,
        }
    }


def _first_ask_in_band(state: pathlib.Path, key: str, win: dict[str, Any]) -> bool:
    band = f"{key}:{int(win['resets_at']) // WINDOW_JITTER_S}:{int(win['pct']) // BAND}"
    path = state / "gate_state.json"
    doc = _read_json(path)
    asked = doc.get("asked", []) if isinstance(doc, dict) else []
    if band in asked:
        return False
    _write_json_atomic(path, {"asked": (asked + [band])[-50:]})
    return True


# --- context window usage ---------------------------------------------------


def _tail_lines(path: pathlib.Path, limit: int = TRANSCRIPT_TAIL_BYTES) -> list[str]:
    """Last `limit` bytes of a file as lines, without a partial first line."""
    with open(path, "rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        fh.seek(max(0, size - limit))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    return lines[1:] if size > limit else lines


def _usage_tokens(entry: Any) -> int:
    """Input tokens of a main-thread assistant transcript entry, else 0."""
    if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
        return 0
    msg = entry.get("message")
    usage = msg.get("usage") if isinstance(msg, dict) else None
    if not isinstance(usage, dict):
        return 0
    vals = (usage.get(k) for k in CONTEXT_FIELDS)
    return sum(v for v in vals if isinstance(v, int) and not isinstance(v, bool))


def snapshot_context_size(state: pathlib.Path, session_id: Any) -> int | None:
    """context_window_size the status line saved for this session, or None."""
    if not isinstance(session_id, str) or not session_id.replace("-", "").replace("_", "").isalnum():
        return None  # also blocks path traversal via a crafted session_id
    doc = _read_json(state / "snapshots" / f"{session_id}.json")
    cw = doc.get("context_window") if isinstance(doc, dict) else None
    size = cw.get("context_window_size") if isinstance(cw, dict) else None
    return size if isinstance(size, int) and not isinstance(size, bool) and size > 0 else None


def context_size(used: int, env: Mapping[str, str], known: int | None = None) -> int:
    """Window size: QUOTA_GUARD_CONTEXT_WINDOW, else the status-line value,
    else 1M once usage passes 200k."""
    try:
        override = int(env.get("QUOTA_GUARD_CONTEXT_WINDOW") or 0)
    except ValueError:
        override = 0
    if override > 0:
        return override
    if known:
        return known
    return CONTEXT_LARGE if used > CONTEXT_DEFAULT else CONTEXT_DEFAULT


def context_usage(
    transcript_path: Any, env: Mapping[str, str], known_size: int | None = None
) -> dict[str, int] | None:
    """Context in use at the last API response of this session, or None.

    It is the input side of the last assistant message: uncached input plus
    cache reads plus cache writes. Synthetic entries with zero usage are skipped.
    """
    if env.get("QUOTA_GUARD_CONTEXT") == "0" or not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        lines = _tail_lines(pathlib.Path(transcript_path))
    except OSError:
        return None
    for line in reversed(lines):
        try:
            used = _usage_tokens(json.loads(line))
        except ValueError:
            continue
        if used > 0:
            return {"used": used, "size": context_size(used, env, known_size)}
    return None


def _fmt_tokens(n: int) -> str:
    return f"{n / 1_000_000:g}M" if n >= 1_000_000 else f"{n / 1000:.0f}k"


def format_context_line(usage: dict[str, int]) -> str:
    pct = 100.0 * usage["used"] / usage["size"]
    return (
        f"Context: {pct:.0f}% used ({_fmt_tokens(usage['used'])}/{_fmt_tokens(usage['size'])} tokens, "
        "as of the last response)"
    )


# --- OAuth refresh (background process only) --------------------------------


def _read_token() -> str | None:
    doc = _read_json(pathlib.Path.home() / ".claude" / ".credentials.json")
    oauth = doc.get("claudeAiOauth") if isinstance(doc, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    return token if isinstance(token, str) and token else None


def _fetch_usage(token: str) -> tuple[int, Any, str | None]:
    req = urllib.request.Request(
        USAGE_URL,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": OAUTH_BETA},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read()), None
    except urllib.error.HTTPError as err:
        return err.code, None, err.headers.get("Retry-After")


def _backoff_seconds(retry_after: str | None) -> float:
    try:
        return max(60.0, float(retry_after)) if retry_after else 300.0
    except ValueError:
        return 300.0


def refresh(state: pathlib.Path, now: float) -> None:
    """Fetch the usage endpoint once into oauth_cache.json. Non-blocking lock."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "oauth.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        backoff = _read_json(state / "oauth_backoff.json")
        if isinstance(backoff, dict) and now < (parse_ts(backoff.get("until")) or 0):
            return
        token = _read_token()
        if not token:
            debug("refresh: no OAuth token in credentials file")
            return
        try:
            status, data, retry_after = _fetch_usage(token)
        except (OSError, ValueError) as err:
            status, data, retry_after = 0, None, None
            debug(f"refresh: request failed: {type(err).__name__}")
        if status == 200 and isinstance(data, dict):
            _write_json_atomic(state / "oauth_cache.json", {"fetched_at": now, "data": data})
            return
        debug(f"refresh: HTTP {status}, backing off")
        _write_json_atomic(state / "oauth_backoff.json", {"until": now + _backoff_seconds(retry_after)})


if __name__ == "__main__":
    if sys.argv[1:] == ["--refresh"]:
        try:
            refresh(state_dir(), time.time())
        except Exception as err:  # noqa: BLE001 - background helper must never surface errors
            debug(f"refresh crashed: {type(err).__name__}")
