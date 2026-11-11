"""Unit tests for plugins/quota-guard/scripts/quota_lib.py and the hook scripts.

No network: the OAuth fetch is never exercised here, only the parsing of
its response shape and the cache read path.

Run: python3 -m unittest discover plugins/quota-guard/tests
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import quota_lib as q  # noqa: E402

NOW = 1_800_000_000.0
HOUR = 3600


def rl(five_pct, five_reset, week_pct=10.0, week_reset=NOW + 3 * 86400):
    return {
        "five_hour": {"used_percentage": five_pct, "resets_at": five_reset},
        "seven_day": {"used_percentage": week_pct, "resets_at": week_reset},
    }


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        (self.dir / "snapshots").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_snap(self, sid, rate_limits, written_at):
        path = self.dir / "snapshots" / f"{sid}.json"
        path.write_text(json.dumps({"rate_limits": rate_limits, "written_at": written_at}))


class NormaliseTests(unittest.TestCase):
    def test_statusline_epoch(self):
        out = q.normalise_statusline(rl(42.5, NOW + HOUR))
        self.assertEqual(out["five_hour"], {"pct": 42.5, "resets_at": NOW + HOUR})
        self.assertEqual(out["seven_day"]["pct"], 10.0)

    def test_statusline_missing_window_is_skipped(self):
        out = q.normalise_statusline({"five_hour": {"used_percentage": 5, "resets_at": NOW}})
        self.assertNotIn("seven_day", out)

    def test_oauth_iso_reset(self):
        resp = {
            "five_hour": {"utilization": 71.0, "resets_at": "2027-01-15T08:00:00+00:00"},
            "seven_day": {"utilization": 30.0, "resets_at": "2027-01-20T08:00:00Z"},
        }
        out = q.normalise_oauth(resp)
        self.assertEqual(out["five_hour"]["pct"], 71.0)
        self.assertEqual(out["five_hour"]["resets_at"], 1800000000.0)
        self.assertEqual(out["seven_day"]["resets_at"], 1800432000.0)

    def test_oauth_limits_array_preferred(self):
        resp = {
            "five_hour": {"utilization": 1.0, "resets_at": "2027-01-15T08:00:00Z"},
            "limits": [
                {"kind": "session", "percent": 55, "resets_at": "2027-01-15T08:00:00Z"},
                {"kind": "weekly_all", "percent": 20, "resets_at": "2027-01-20T08:00:00Z"},
                {"kind": "weekly_scoped", "percent": 99, "resets_at": "2027-01-20T08:00:00Z"},
            ],
        }
        out = q.normalise_oauth(resp)
        self.assertEqual(out["five_hour"]["pct"], 55)
        self.assertEqual(out["seven_day"]["pct"], 20)

    def test_garbage_returns_empty(self):
        self.assertEqual(q.normalise_statusline("nope"), {})
        self.assertEqual(q.normalise_oauth({"five_hour": None}), {})


class MergeTests(TmpDirCase):
    def test_expired_window_is_ignored(self):
        # H1: an idle session still holding a 97% reading from a window that already reset.
        self.write_snap("old", rl(97, NOW - 60), NOW - 5)
        self.write_snap("new", rl(40, NOW + 2 * HOUR), NOW - 30)
        model = q.load_snapshots(self.dir, NOW)
        self.assertEqual(model["five_hour"]["pct"], 40)

    def test_max_pct_within_same_window(self):
        self.write_snap("a", rl(60, NOW + HOUR), NOW - 5)
        self.write_snap("b", rl(64, NOW + HOUR + 30), NOW - 200)  # jitter on resets_at
        model = q.load_snapshots(self.dir, NOW)
        self.assertEqual(model["five_hour"]["pct"], 64)
        self.assertEqual(model["written_at"], NOW - 5)

    def test_newest_window_wins(self):
        self.write_snap("a", rl(90, NOW + 10 * 60), NOW - 5)
        self.write_snap("b", rl(5, NOW + 4 * HOUR + 50 * 60), NOW - 5)
        model = q.load_snapshots(self.dir, NOW)
        self.assertEqual(model["five_hour"]["pct"], 5)

    def test_corrupt_and_old_files(self):
        (self.dir / "snapshots" / "bad.json").write_text("{not json")
        old = self.dir / "snapshots" / "ancient.json"
        old.write_text(json.dumps({"rate_limits": rl(50, NOW + HOUR), "written_at": NOW - 2 * 86400}))
        os.utime(old, (NOW - 2 * 86400, NOW - 2 * 86400))
        self.assertIsNone(q.load_snapshots(self.dir, NOW))
        self.assertFalse(old.exists())

    def test_no_snapshots(self):
        self.assertIsNone(q.load_snapshots(self.dir, NOW))


class LoadTests(TmpDirCase):
    def test_fresh_snapshot(self):
        self.write_snap("a", rl(30, NOW + HOUR), NOW - 20)
        model = q.load(self.dir, NOW, env={})
        self.assertEqual(model["source"], "statusline")
        self.assertEqual(model["age_s"], 20)

    def test_stale_snapshot_without_oauth_still_used_until_limit(self):
        self.write_snap("a", rl(30, NOW + HOUR), NOW - 600)
        self.assertEqual(q.load(self.dir, NOW, env={})["source"], "statusline")
        self.write_snap("a", rl(30, NOW + HOUR), NOW - 1000)
        self.assertIsNone(q.load(self.dir, NOW, env={}))

    def test_oauth_cache_used_when_snapshot_stale(self):
        self.write_snap("a", rl(30, NOW + HOUR), NOW - 600)
        cache = {"fetched_at": NOW - 10, "data": {"five_hour": {"utilization": 77, "resets_at": "2027-01-15T09:00:00Z"}}}
        (self.dir / "oauth_cache.json").write_text(json.dumps(cache))
        model = q.load(self.dir, NOW, env={"QUOTA_GUARD_OAUTH": "1"}, spawn_refresh=lambda: None)
        self.assertEqual(model["source"], "oauth")
        self.assertEqual(model["five_hour"]["pct"], 77)

    def test_refresh_spawned_when_cache_stale(self):
        calls = []
        q.load(self.dir, NOW, env={"QUOTA_GUARD_OAUTH": "1"}, spawn_refresh=lambda: calls.append(1))
        self.assertEqual(calls, [1])

    def test_no_refresh_when_oauth_disabled(self):
        calls = []
        q.load(self.dir, NOW, env={}, spawn_refresh=lambda: calls.append(1))
        self.assertEqual(calls, [])


class ProjectionTests(unittest.TestCase):
    def test_linear_burn_hits_before_reset(self):
        reset = NOW + 2 * HOUR
        hist = [{"ts": NOW - 1800 + i * 300, "five_hour": [50 + i * 5, reset]} for i in range(7)]
        # 5% per 5 min = 1%/min; now at 80% -> 20 min to 100%.
        eta = q.project(hist, "five_hour", reset, NOW, lookback=HOUR)
        self.assertAlmostEqual(eta, NOW + 20 * 60, delta=5)

    def test_needs_span_and_positive_slope(self):
        reset = NOW + HOUR
        short = [{"ts": NOW - 60, "five_hour": [10, reset]}, {"ts": NOW, "five_hour": [11, reset]}]
        self.assertIsNone(q.project(short, "five_hour", reset, NOW, lookback=HOUR))
        flat = [{"ts": NOW - 1200, "five_hour": [10, reset]}, {"ts": NOW, "five_hour": [10, reset]}]
        self.assertIsNone(q.project(flat, "five_hour", reset, NOW, lookback=HOUR))

    def test_points_from_previous_window_ignored(self):
        reset = NOW + HOUR
        hist = [
            {"ts": NOW - 1800, "five_hour": [90, NOW - 100]},
            {"ts": NOW - 1200, "five_hour": [1, reset]},
            {"ts": NOW, "five_hour": [2, reset]},
        ]
        eta = q.project(hist, "five_hour", reset, NOW, lookback=HOUR)
        self.assertIsNotNone(eta)
        self.assertGreater(eta, reset)  # slow burn: will not run out


class HistoryTests(TmpDirCase):
    def test_append_rate_limited_and_trimmed(self):
        model = {"five_hour": {"pct": 10, "resets_at": NOW + HOUR}}
        q.record_history(self.dir, model, NOW - 9 * 86400)
        q.record_history(self.dir, model, NOW)
        q.record_history(self.dir, model, NOW + 30)
        rows = q.read_history(self.dir)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ts"], NOW)


class AssessTests(unittest.TestCase):
    def model(self, five, week=10):
        return {
            "five_hour": {"pct": five, "resets_at": NOW + HOUR},
            "seven_day": {"pct": week, "resets_at": NOW + 3 * 86400},
            "source": "statusline",
            "age_s": 12,
        }

    def test_levels(self):
        self.assertEqual(q.assess(self.model(50), [], NOW, {})["level"], "ok")
        self.assertEqual(q.assess(self.model(82), [], NOW, {})["level"], "warn")
        self.assertEqual(q.assess(self.model(91), [], NOW, {})["level"], "gate")
        self.assertEqual(q.assess(self.model(10, week=96), [], NOW, {})["level"], "gate")

    def test_env_thresholds(self):
        env = {"QUOTA_GUARD_WARN_5H": "40"}
        self.assertEqual(q.assess(self.model(50), [], NOW, env)["level"], "warn")

    def test_projection_gate_when_exhaustion_imminent(self):
        reset = NOW + HOUR
        hist = [{"ts": NOW - 1800 + i * 300, "five_hour": [45 + i * 5, reset]} for i in range(7)]
        a = q.assess(self.model(75), hist, NOW, {})
        self.assertEqual(a["level"], "gate")  # 1%/min -> 25 min to 100, reset in 60

    def test_format_line(self):
        line = q.format_line(self.model(72), q.assess(self.model(72), [], NOW, {}), NOW)
        self.assertTrue(line.startswith("Quota: 5h 72%"))
        self.assertIn("7d 10%", line)
        self.assertIn("statusline, 12s old", line)


class GateDecisionTests(TmpDirCase):
    def decide(self, pct, env=None):
        model = {"five_hour": {"pct": pct, "resets_at": NOW + HOUR}, "source": "statusline", "age_s": 5}
        return q.gate_decision(self.dir, model, [], NOW, env or {}, tool="Agent")

    def test_below_threshold_no_decision(self):
        self.assertIsNone(self.decide(50))

    def test_ask_once_per_band(self):
        first = self.decide(91)
        self.assertEqual(first["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn("91%", first["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.decide(92))  # same 90-95 band
        self.assertIsNotNone(self.decide(96))  # next band

    def test_deny_mode_always(self):
        env = {"QUOTA_GUARD_GATE_MODE": "deny"}
        self.assertEqual(self.decide(91, env)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.decide(91, env)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_off_mode(self):
        self.assertIsNone(self.decide(99, {"QUOTA_GUARD_GATE_MODE": "off"}))


def assistant(inp, read, create, sidechain=False):
    usage = {"input_tokens": inp, "cache_read_input_tokens": read, "cache_creation_input_tokens": create}
    return {"type": "assistant", "isSidechain": sidechain, "message": {"usage": usage}}


def write_transcript(directory, entries):
    path = pathlib.Path(directory) / "transcript.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


class ContextTests(TmpDirCase):
    def test_uses_last_main_thread_assistant(self):
        path = write_transcript(self.dir, [
            assistant(10, 1000, 0),
            assistant(2, 120_000, 500),
            {"type": "user", "message": {"content": "hi"}},
            assistant(1, 999_000, 0, sidechain=True),
            assistant(0, 0, 0),  # synthetic error entry
            "not json",
        ])
        self.assertEqual(q.context_usage(str(path), {}), {"used": 120_502, "size": 200_000})

    def test_large_window_inferred_above_200k(self):
        path = write_transcript(self.dir, [assistant(0, 250_000, 0)])
        self.assertEqual(q.context_usage(str(path), {})["size"], 1_000_000)

    def test_window_override(self):
        path = write_transcript(self.dir, [assistant(0, 50_000, 0)])
        usage = q.context_usage(str(path), {"QUOTA_GUARD_CONTEXT_WINDOW": "1000000"})
        self.assertEqual(usage["size"], 1_000_000)
        self.assertEqual(q.context_usage(str(path), {"QUOTA_GUARD_CONTEXT_WINDOW": "junk"})["size"], 200_000)

    def test_disabled_missing_or_empty(self):
        path = write_transcript(self.dir, [assistant(0, 50_000, 0)])
        self.assertIsNone(q.context_usage(str(path), {"QUOTA_GUARD_CONTEXT": "0"}))
        self.assertIsNone(q.context_usage(str(self.dir / "missing.jsonl"), {}))
        self.assertIsNone(q.context_usage(None, {}))
        self.assertIsNone(q.context_usage(str(write_transcript(self.dir, [])), {}))

    def test_tail_skips_partial_first_line(self):
        path = write_transcript(self.dir, [assistant(0, 7, 0)] * 50)
        lines = q._tail_lines(path, limit=200)
        self.assertTrue(lines)
        for line in lines:
            json.loads(line)

    def test_format(self):
        line = q.format_context_line({"used": 450_000, "size": 1_000_000})
        self.assertEqual(line, "Context: 45% used (450k/1M tokens, as of the last response)")


class HookScriptTests(TmpDirCase):
    """End-to-end: run the hook scripts as Claude Code would."""

    def run_hook(self, script, payload, extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("QUOTA_GUARD_")}
        env["QUOTA_GUARD_DIR"] = str(self.dir)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script)],
            input=payload, capture_output=True, text=True, env=env, timeout=10,
        )

    def test_inject_outputs_line(self):
        now = time.time()
        self.write_snap("s", rl(33, now + HOUR), now - 3)
        out = self.run_hook("inject.py", json.dumps({"session_id": "s", "hook_event_name": "UserPromptSubmit"}))
        self.assertEqual(out.returncode, 0)
        self.assertIn("Quota: 5h 33%", out.stdout)

    def test_inject_unknown_only_at_session_start(self):
        out = self.run_hook("inject.py", json.dumps({"hook_event_name": "SessionStart"}))
        self.assertEqual(out.returncode, 0)
        self.assertIn("Quota: unknown", out.stdout)
        out = self.run_hook("inject.py", json.dumps({"hook_event_name": "UserPromptSubmit"}))
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        out = self.run_hook("inject.py", "not json")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")

    def test_gate_asks_at_93(self):
        now = time.time()
        self.write_snap("s", rl(93, now + HOUR), now - 3)
        out = self.run_hook("gate.py", json.dumps({"tool_name": "Agent"}))
        self.assertEqual(out.returncode, 0)
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_inject_context_line_without_quota_data(self):
        path = write_transcript(self.dir, [assistant(1000, 80_000, 5000)])
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "transcript_path": str(path)})
        out = self.run_hook("inject.py", payload)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "Context: 43% used (86k/200k tokens, as of the last response)")

    def test_inject_bad_transcript_path_is_silent(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "transcript_path": "/nonexistent/x.jsonl"})
        out = self.run_hook("inject.py", payload)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")

    def test_fail_open_on_bad_stdin_and_dir(self):
        out = self.run_hook("gate.py", "not json", {"QUOTA_GUARD_DIR": "/proc/forbidden/x"})
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")


if __name__ == "__main__":
    unittest.main()
