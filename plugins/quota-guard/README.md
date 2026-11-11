# Quota Guard

Quota Guard shows Claude your 5-hour and 7-day subscription quota on each prompt.
It warns Claude when the quota is low. It asks you before Claude starts sub-agents or workflows when the quota is almost used.

## What it does

| Hook | Action |
|------|--------|
| `SessionStart`, `UserPromptSubmit` | Adds one line to the context, for example `Quota: 5h 72% (resets 14:05, ~13:40 at current pace) \| 7d 41% (resets Thu 09:00) [statusline, 40s old]`. Adds a warning line at the warn threshold, or when the current pace runs out the quota before the reset. |
| `PreToolUse` on `Agent`, `Task`, `Workflow` | At the gate threshold, or when the quota runs out in less than 30 minutes at the current pace, asks you to approve the tool. It asks one time for each 5% band in a window. |

When no quota data is available, Quota Guard adds `Quota: unknown` one time at session start. It adds nothing to later prompts until data is available.

All hooks fail open. If a hook has an error, it prints nothing and the prompt or tool continues.

## Data sources

Claude Code sends the exact quota (`rate_limits`) to the status line only. Hooks do not get it. Quota Guard uses these sources:

1. **Status-line snapshot (recommended).** Your status-line script writes `rate_limits` to a file. Quota Guard reads that file.
2. **Usage endpoint (opt-in).** Set `QUOTA_GUARD_OAUTH=1`. Quota Guard then calls `https://api.anthropic.com/api/oauth/usage` in a background process with the token in `~/.claude/.credentials.json`. This endpoint is not documented and can change. It does not work on macOS, because the token is in the Keychain.

`ccusage` is not used. It estimates usage from local logs and does not know the real limits.

## Requirements

- `python3`. The plugin uses the standard library only.
- Linux or macOS. The plugin uses `fcntl`, so it does not run on Windows.
- `jq` and `bash` for the status-line lines below.
- A Claude Pro or Max subscription.

## Install

1. Add the marketplace and install the plugin:

   ```text
   /plugin marketplace add keyz182/keyz-claude-skills
   /plugin install quota-guard@keyz-claude-skills
   ```

2. Add these lines to your status-line script, after the line that reads stdin into `$input`:

   ```bash
   qg_dir="$HOME/.claude/quota-guard/snapshots"
   qg_sid="$(jq -r '.session_id // empty' <<<"$input")"
   if [[ -n "$qg_sid" ]] && jq -e '.rate_limits' <<<"$input" >/dev/null 2>&1; then
     mkdir -p "$qg_dir"
     jq -c '{rate_limits, written_at: now}' <<<"$input" >"$qg_dir/$qg_sid.json.tmp" &&
       mv "$qg_dir/$qg_sid.json.tmp" "$qg_dir/$qg_sid.json"
   fi
   ```

3. Start a new session. Send one prompt. The next prompt shows the `Quota:` line.

Claude Code sends `rate_limits` only to Pro and Max subscribers, and only after the first API response in a session.

## Settings

Set these environment variables, for example in `settings.json` under `env`.

| Variable | Default | Meaning |
|----------|---------|---------|
| `QUOTA_GUARD_WARN_5H` / `QUOTA_GUARD_WARN_7D` | `80` / `85` | Percent that adds the warning line. |
| `QUOTA_GUARD_GATE_5H` / `QUOTA_GUARD_GATE_7D` | `90` / `95` | Percent that gates `Agent`, `Task` and `Workflow`. |
| `QUOTA_GUARD_GATE_MODE` | `ask` | `ask`, `deny` or `off`. In headless `claude -p`, `ask` blocks the tool, also with `--permission-mode bypassPermissions`. |
| `QUOTA_GUARD_OAUTH` | unset | `1` turns on the usage-endpoint fallback. |
| `QUOTA_GUARD_DIR` | `~/.claude/quota-guard` | State directory. |
| `QUOTA_GUARD_DEBUG` | unset | `1` writes errors to `debug.log` in the state directory. Tokens are never written. |

## How the numbers are merged

Each session writes its own snapshot. A snapshot is only as new as the last API response in that session. Quota Guard does not use the last file written. For each window it:

1. Ignores readings whose reset time has passed.
2. Keeps the readings from the newest window (10-minute tolerance on the reset time).
3. Uses the highest percent, because usage only increases in a window.

The current pace comes from a least-squares fit of recent readings: the last hour for 5h, the last 24 hours for 7d.

## Tests

```bash
python3 -m unittest discover plugins/quota-guard/tests
bash plugins/quota-guard/tests/smoke.sh
```

## Known limits

- The usage endpoint is not documented. Its terms-of-service position is not clear. It is a fallback only and is off by default.
- Father Time 1.9 also calls the usage endpoint. Both cache the result, so the extra calls are few.
- Data older than 15 minutes is not shown.
