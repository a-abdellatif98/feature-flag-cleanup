# Stale flag heuristics

Each heuristic is a lead from code alone. None proves the flag is stale, because the live state sits in the flag store.

## STALE-CONSTANT: only one branch is reachable

The code itself fixes the flag to one value, so one branch of every check is dead.

- Pennant: `Feature::define('x', true)` or a closure that only returns a constant, or `Feature::activateForEveryone('x')` with no deactivation anywhere.
- Flipper: `Flipper.enable(:x)` with no actor, group or percentage argument and no `disable` anywhere in non-test code (for example in a migration or seed).
- django-waffle: `Flag.objects.create(name='x', everyone=True)` (or `active=` for a switch) in a data migration with nothing that changes it.

The scanner reports it only when every non-test definition or toggle it found sets the same constant. If the flag is also changed from an admin screen or the flag service, the constant is only the initial value: confirm first.

## STALE-SINGLE-REF: referenced in one place

Exactly one non-test reference. If it is a lone check, removal is a one-file change and cheap. It is not stale by itself: a new flag behind its first check looks the same. Look at the age of the line (`git log -S`) before acting.

## STALE-UNUSED: defined but unused

The code defines, registers or toggles the flag, and no non-test code checks it. Typical causes: the check was removed and the definition was forgotten, or the flag is read by name from another place the scanner cannot see (a dynamic name, another repository, a client). When dynamic names exist for the system the scanner says so in the message.

## STALE-UNDEFINED: checked but never defined

A check with no definition or registration in the code.

- Pennant: reported whenever it happens. Behaviour for an undefined feature depends on the Pennant version, so check the docs for the version in use.
- Flipper and django-waffle: flags normally live in the database, so a missing definition is normal. The scanner reports this only when the project registers other flags in code (for example `Flipper.add` or a waffle data migration), which makes an unregistered one suspicious.
- LaunchDarkly, Unleash, OpenFeature: never reported, flags are created in the service.

## Not detected

- Flags read through a variable, a constant or string interpolation.
- Flags whose state differs between environments.
- Flags that gate nothing any more because the surrounding code was deleted.
- Checks reached through a helper that wraps the SDK call: search for the helper's callers by hand.
- Dead flags in other repositories or in client builds.
