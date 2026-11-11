# keyz-claude-skills

This repository is a plugin marketplace for [Claude Code](https://claude.com/claude-code).

## Install

1. Add the marketplace:

   ```text
   /plugin marketplace add keyz182/keyz-claude-skills
   ```

2. Install a plugin:

   ```text
   /plugin install <plugin-name>@keyz-claude-skills
   ```

## Plugins

| Plugin | Description |
|--------|-------------|
| [adversarial-review](plugins/adversarial-review/README.md) | Adds a skill that looks for the reasons a plan, design, diff or decision will fail. Rates each concern against a fixed severity bar. Ends with one verdict: PROCEED, AMEND or RETHINK. |
| [quota-guard](plugins/quota-guard/README.md) | Shows Claude your 5-hour and 7-day subscription quota on each prompt. Warns when the quota is low. Asks before Claude starts sub-agents or workflows when the quota is almost used. |

## Tests

Run the tests from the repository root.

```bash
python3 -m unittest discover plugins/quota-guard/tests
bash plugins/quota-guard/tests/smoke.sh
```

## Licence

MIT. See [LICENSE](LICENSE).
