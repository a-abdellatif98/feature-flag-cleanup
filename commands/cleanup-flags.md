---
description: List feature flags and their call sites, mark the likely-stale ones, and write a safe removal plan per flag
argument-hint: [flag name, path, or empty for the whole project]
allowed-tools: [Read, Glob, Grep]
---

# Clean Up Feature Flags

Find feature flags in code and plan their removal, following the `flag-cleanup` skill.

## Arguments

The user invoked this command with: $ARGUMENTS

Treat the argument as a flag name, a path, or free text. If it is empty, inspect the whole project. If it names a flag, plan only that flag.

## Instructions

1. **Detect the flag system** with Glob and Read: Flipper (`flipper` in `Gemfile`, `Flipper.` calls), django-waffle (`waffle` in `INSTALLED_APPS` or requirements, `waffle_tags` in templates), Laravel Pennant (`laravel/pennant` in `composer.json`, `Feature::`), LaunchDarkly, Unleash or OpenFeature (`package.json` dependencies).

   Never open dotfiles, `config/database.yml`, `settings.py` `DATABASES`, `config/database.php`, credential files, or anything holding keys, tokens or database URLs. This includes the SDK initialisation code that passes credentials: read the flag calls, not the client setup.

2. **List every flag and call site**: Grep with the patterns in `skills/flag-cleanup/references/` (`flipper.md`, `django-waffle.md`, `laravel-pennant.md`, `node-sdks.md`). Record `file:line`, whether it is a check, a definition, a toggle or a removal, and whether it is in a test. Note calls whose flag name is not a literal: they can reference any flag.

3. **Mark likely-stale flags** with the heuristics in `references/stale-heuristics.md`: one reachable branch, one reference, defined but unused, checked but never defined.

4. **Write the removal plan** for each stale flag, or for the flag named in the argument, with `references/removal-plan.md`: the branch to keep, the code and tests to change, and the flag record to delete last.

## Output format

### Flag cleanup: `target`

**Detected:** flag system and version hints.

**Flags:** a table of flag, system, call sites (code and test), stale reasons.

**Removal plans:** per flag, numbered steps ordered so each step can ship alone: `file:line` edits for the kept branch, tests to update, then the flag record or migration last.

**Unsure:** dynamic flag names, flags that may also be set in the flag service (code cannot show that), and anything you could not trace.

**Scanner:** mention that `python3 scripts/flag_scan.py <project root>` (run from the plugin directory by the user) gives a deterministic first pass, with `--json` and `--framework` options, exit code 1 when it marks a flag stale. It is a heuristic and never contacts a flag service: confirm each hit.

Do not run anything and do not call any flag service. Read code, produce findings and diffs only.
