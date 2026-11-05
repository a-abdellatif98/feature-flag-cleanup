# feature-flag-cleanup

A plugin that finds feature flags in code, lists every call site per flag, marks the likely-stale ones, and writes a safe removal plan for each: which branch to keep, which tests to update, and the flag record to delete last.

It works from code only. It never calls a flag service API and never reads flag service credentials. It pairs with [db-migration-guard](https://github.com/a-abdellatif98/db-migration-guard), [backfill-planner](https://github.com/a-abdellatif98/backfill-planner) and [n-plus-one-hunter](https://github.com/a-abdellatif98/n-plus-one-hunter).

## What it covers

| System | Recognised in code |
|---|---|
| Flipper (Rails) | `Flipper.enabled?`, `Flipper[:x]`, `Flipper.add`, `Flipper.enable`, `Flipper.remove` |
| django-waffle | `flag_is_active`, `switch_is_active`, `sample_is_active`, decorators, `{% flag %}` tags, `override_flag` |
| Laravel Pennant | `Feature::define`, `Feature::active`, `@feature`, class-based features, `Feature::purge` |
| LaunchDarkly, Unleash, OpenFeature (Node) | `variation`, `isEnabled`, `getBooleanValue` and the React hooks |

## Likely-stale signals

- `STALE-CONSTANT`: code fixes the flag to one value, so only one branch is reachable
- `STALE-SINGLE-REF`: referenced in one non-test place
- `STALE-UNUSED`: defined or toggled in code but never checked
- `STALE-UNDEFINED`: checked but never defined (only where flags are registered in code)

Each is a lead. The live value sits in the flag store, which this plugin does not read, so every plan starts with a confirmation step for the flag owner.

## Installation

```
/plugin install feature-flag-cleanup@claude-plugins-official
```

## Usage

### Slash command

```
/cleanup-flags
/cleanup-flags new_checkout
/cleanup-flags app/services
```

It reads the code with read-only tools and outputs a flag table, the stale reasons and a removal plan per flag, ordered so each step can ship alone and the flag record goes last.

### Skill

The `flag-cleanup` skill activates when you talk about stale flags, flag debt or removing a flag. References:

| Reference | Covers |
|---|---|
| `flipper.md` | Flipper call shapes, constant enables, removing the record |
| `django-waffle.md` | flags, switches, samples, templates, `waffle_delete` |
| `laravel-pennant.md` | closures, class-based features, `Name` attribute, `pennant:purge` |
| `node-sdks.md` | LaunchDarkly, Unleash, OpenFeature, what the scanner cannot see |
| `stale-heuristics.md` | what each stale code means and its false positives |
| `removal-plan.md` | the removal steps and a plan template |

### Scanner

```
python3 scripts/flag_scan.py <project root> [--json] [--framework flipper]
```

Standard library only. It reads source files, skips `.env*`, key and credential files, dot and dependency directories and symlinks, and opens no network connection. Exit code 1 when a flag is marked stale, 2 for a bad path. It matches literal flag names only and reports non-literal names as dynamic sites.

## Development

```
python3 -m pytest -q tests
python3 -m pyflakes scripts tests
```

## License

MIT
