#!/usr/bin/env bash
# quota-guard smoke check: run the hook scripts the way Claude Code does,
# against a throwaway state dir. Run: bash plugins/quota-guard/tests/smoke.sh

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$(mktemp -d)"
trap 'rm -rf "$STATE"' EXIT
export QUOTA_GUARD_DIR="$STATE"
unset QUOTA_GUARD_OAUTH QUOTA_GUARD_GATE_MODE
mkdir -p "$STATE/snapshots"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

snap() { # snap <session> <five_pct> <five_reset_offset_s>
  local now
  now="$(date +%s)"
  printf '{"rate_limits":{"five_hour":{"used_percentage":%s,"resets_at":%s},"seven_day":{"used_percentage":12,"resets_at":%s}},"written_at":%s}' \
    "$2" "$((now + $3))" "$((now + 259200))" "$now" >"$STATE/snapshots/$1.json"
}

inject() { echo '{"hook_event_name":"UserPromptSubmit"}' | python3 "$PLUGIN_DIR/scripts/inject.py"; }
gate() { echo '{"tool_name":"Agent"}' | python3 "$PLUGIN_DIR/scripts/gate.py"; }

# 1. No data -> unknown once at SessionStart, silent on prompts, gate silent.
echo '{"hook_event_name":"SessionStart"}' | python3 "$PLUGIN_DIR/scripts/inject.py" | grep -q '^Quota: unknown' ||
  fail "expected unknown line at SessionStart"
[[ -z "$(inject)" ]] || fail "prompts should be silent with no data"
[[ -z "$(gate)" ]] || fail "gate should be silent with no data"

# 2. Expired 97% window from an idle session + current 40% -> 40%, no gate.
snap idle 97 -60
snap live 40 7200
inject | grep -q '^Quota: 5h 40%' || fail "merge should pick live 40%"
[[ -z "$(gate)" ]] || fail "gate should be silent at 40%"

# 3. 93% -> warning injected, gate asks once per 5% band.
snap live 93 7200
inject | grep -q '^Quota warning' || fail "expected warning at 93%"
gate | grep -q '"permissionDecision": "ask"' || fail "expected ask at 93%"
[[ -z "$(gate)" ]] || fail "second ask in same band should be silent"

# 4. deny mode always denies.
QUOTA_GUARD_GATE_MODE=deny gate | grep -q '"permissionDecision": "deny"' || fail "expected deny"

# 5. Fail-open on garbage stdin.
out="$(echo 'garbage' | python3 "$PLUGIN_DIR/scripts/gate.py")" || fail "gate exited non-zero"
[[ -z "$out" ]] || fail "gate should print nothing on bad input"

# 6. Context line from the transcript named in the hook payload.
printf '{"type":"assistant","message":{"usage":{"input_tokens":2,"cache_read_input_tokens":99000,"cache_creation_input_tokens":998}}}\n' >"$STATE/t.jsonl"
printf '{"hook_event_name":"UserPromptSubmit","transcript_path":"%s"}' "$STATE/t.jsonl" |
  python3 "$PLUGIN_DIR/scripts/inject.py" | grep -q '^Context: 50% used (100k/200k' || fail "expected context line"

echo "smoke OK"
