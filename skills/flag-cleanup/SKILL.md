---
name: flag-cleanup
description: This skill should be used when the user wants to find, audit or remove feature flags or toggles, for example "feature flag cleanup", "stale flags", "dead flags", "remove a flag", "rip out the flag", "flag debt", "Flipper", "Flipper.enabled?", "waffle", "flag_is_active", "switch_is_active", "Laravel Pennant", "Feature::active", "LaunchDarkly variation", "Unleash isEnabled", "OpenFeature getBooleanValue", or when reviewing a branch that leaves a flag fully rolled out. Lists the flags and every call site, marks the likely-stale ones and writes a safe removal plan, from code only.
version: 1.0.0
---

# Feature Flag Cleanup

A flag that is fully rolled out, or abandoned, is dead weight: two code paths to read, a test matrix that doubles, and a flag record nobody dares delete. This skill finds the flags in code, shows every place each one is used, marks the ones that look stale, and plans the removal so each step can ship alone.

It works from code only. It never calls a flag service API and never reads the credentials of one. What a flag is set to in production is not visible in code: the plan always says where the owner must confirm it.

## Supported systems

| System | Call shapes the scanner recognises | Reference |
|---|---|---|
| Flipper (Rails) | `Flipper.enabled?(:x)`, `Flipper[:x].enabled?`, `Flipper.add`, `Flipper.enable`, `Flipper.remove` | `references/flipper.md` |
| django-waffle | `flag_is_active`, `switch_is_active`, `sample_is_active`, decorators, template tags, `override_flag` | `references/django-waffle.md` |
| Laravel Pennant | `Feature::define`, `Feature::active`, `@feature`, class-based features, `Feature::purge` | `references/laravel-pennant.md` |
| LaunchDarkly, Unleash, OpenFeature (Node) | `variation`, `isEnabled`, `getBooleanValue`, and the React hooks | `references/node-sdks.md` |

## Workflow

1. **Detect the system** from dependency files and imports. Several can coexist.
2. **List flags and call sites.** For each flag: every check, definition, toggle and removal with `file:line`, split into code and tests. Dynamic names (`Flipper.enabled?(name)`) are listed apart: they may touch any flag, so they weaken every "unused" conclusion.
3. **Mark likely-stale flags** with `references/stale-heuristics.md`.
4. **Plan the removal** per flag with `references/removal-plan.md`: confirm the live state, pick the branch to keep, edit the call sites, update the tests, remove the code definition, and delete the flag record last.
5. **Verify** by grepping the flag name again (including strings, YAML, docs and dashboards) and running the affected tests.

## Rules for the plan

- Never pick the branch to keep from the code alone. The branch to keep is the one production runs for everyone, and only the flag owner can confirm it. State it as a question to confirm.
- One flag per change. Order the steps so the application is correct after each one.
- The flag record goes last, in its own step, after the code that reads it is deployed everywhere.
- Say what code cannot show: the state in the flag service, other repositories or services reading the same flag, mobile or client builds still in the field.

## The scanner

`scripts/flag_scan.py` is a deterministic heuristic scan. It reads source and template files only, skips dotfiles, key and credential files, dot directories, dependency directories and symlinks, and never opens a network connection. Output is text or `--json`; `--framework` limits it to one system. Exit code 1 when it marks a flag stale.

Stale codes: `STALE-UNUSED`, `STALE-CONSTANT`, `STALE-UNDEFINED`, `STALE-SINGLE-REF`. Each is a lead, not a verdict. Limits: it matches flag names written as literals, it does not follow variables or constants, and it cannot see a flag set only in the flag service. Matching is line based: code inside Ruby `=begin` blocks, the middle of multiline comments, docstrings and string literals counts as real, and names containing both quote characters or written as `:"quoted-sym"` are missed. It skips Python settings modules (`settings.py`, `local_settings.py`, `prod_settings.py`, `settings_local.py`, files under a `settings/` directory), `database.php`, dotfiles and secret files. `references/stale-heuristics.md` explains each code and its false positives.
