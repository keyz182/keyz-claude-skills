# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A public Claude Code plugin marketplace, published as GitHub `keyz182/keyz-claude-skills` (marketplace name `keyz-claude-skills`). Plugins here are ported from a private company repo. Nothing company-internal may enter this repo: no company or product names, internal hosts, ticket keys, work email addresses or CI config. Before a commit, scan the tree for such strings and show the empty result.

## Commands

Run from the repo root. There is no build step and no lint config.

```bash
python3 -m unittest discover plugins/quota-guard/tests                                    # all unit tests
python3 -m unittest discover -s plugins/quota-guard/tests -k test_expired_window_is_ignored  # one test
bash plugins/quota-guard/tests/smoke.sh                                                   # runs the real hooks against a temp state dir
claude plugin validate .                                                                  # marketplace + every plugin manifest
claude plugin validate plugins/<name>                                                     # one plugin, with directory checks
```

`claude plugin validate` must pass. The only accepted warning is the missing plugin icon.

## Layout rules

- Each plugin is self-contained in `plugins/<name>/` with its own `.claude-plugin/plugin.json`, `README.md` and, where it has code, tests. A plugin must not import or reference files outside its own directory, because it is installed on its own.
- `.claude-plugin/marketplace.json` is written by hand. Add an entry for each new plugin and keep its `description` and `displayName` the same as in the plugin's `plugin.json`.
- Manifest fields are camelCase (`displayName`). The validator flags `display_name`, and Claude Code ignores it.
- Bump `version` in `plugin.json` on every change to a plugin. Without a bump, `claude plugin update` reports that the plugin is already at the latest version.
- Add each new plugin to the table in the root `README.md`.

## quota-guard architecture

Claude Code gives the exact quota (`rate_limits`) to the status line only; hooks do not receive it. The plugin gets the quota to the hooks in four steps:

1. The user's status-line script writes `{rate_limits, written_at}` to `~/.claude/quota-guard/snapshots/<session_id>.json`. This snippet lives in the plugin README, not in the plugin; the plugin cannot install it.
2. `scripts/quota_lib.py` holds all the logic. It merges the snapshots of all sessions: for each window (5h, 7d) it drops readings whose reset time has passed, keeps readings from the newest window, and takes the highest percent. It appends to `history.jsonl` and projects the run-out time with a least-squares fit.
3. `scripts/inject.py` (hooks `SessionStart`, `UserPromptSubmit`) prints the `Quota:` line and, at the warn threshold, a warning line.
4. `scripts/gate.py` (hook `PreToolUse`, matcher `Agent|Task|Workflow`) returns a `permissionDecision` of `ask` or `deny` at the gate threshold. It asks once for each 5% band, tracked in `gate_state.json`.

`inject.py` and `gate.py` are thin entry points; put new logic in `quota_lib.py`.

Constraints to keep:

- Hooks fail open. On any error a hook prints nothing and exits 0. A broken quota hook must never block a prompt or a tool.
- Standard library only. No third-party Python packages. `fcntl` makes the plugin POSIX-only.
- `hooks/hooks.json` uses `"command": "python3"` with an `"args"` array and `${CLAUDE_PLUGIN_ROOT}`. Keep that form.
- The usage-endpoint fallback is opt-in (`QUOTA_GUARD_OAUTH=1`) and must stay off by default. It reads the token in `~/.claude/.credentials.json` and calls an undocumented endpoint in a background process. Never log the token.
- All state lives in `QUOTA_GUARD_DIR` (default `~/.claude/quota-guard`). Tests and `smoke.sh` set it to a temporary directory; new tests must do the same and must not touch the real state directory.
- Each setting is an environment variable with the prefix `QUOTA_GUARD_`. The plugin README has the full table; update it when a variable is added or a default changes.

## adversarial-review architecture

A skill-only plugin: no code, hooks or tests. `skills/adversarial-review/SKILL.md` holds the whole process (modes, lens choice, severity bar, budget, verdict, rounds). It loads the files under `references/` by relative path only when a step needs them, so keep long question banks and worked examples there and keep `SKILL.md` short.

- A file under `references/` that `SKILL.md` does not name is never loaded. When a reference file is added, renamed or removed, update `SKILL.md` and the "Skill contents" table in the plugin README.
- The skill has a `version` in its frontmatter. Keep it the same as `version` in `plugin.json`.
- The review ledger is written under `${XDG_STATE_HOME:-~/.local/state}/adversarial-review/`, not under `~/.claude/`, because Claude Code asks permission for every write there.
- The skill must not name a host-specific tool as a requirement. It uses a structured question tool if the host has one and works without it.
