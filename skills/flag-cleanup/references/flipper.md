# Flipper (Rails)

Flags are stored by an adapter (commonly the ActiveRecord adapter) and addressed by name, symbol or string. Code usually only checks them; the record lives in the database.

## Call shapes the scanner reads

| Role | Shape |
|---|---|
| check | `Flipper.enabled?(:x)`, `Flipper.enabled?(:x, actor)`, `Flipper[:x].enabled?`, `Flipper.feature(:x).enabled?`, in Ruby and in `.erb`, `.haml`, `.slim` |
| define | `Flipper.add(:x)` registers a feature without enabling it |
| toggle | `Flipper.enable(:x)`, `Flipper.disable(:x)`, `Flipper.enable_actor(:x, actor)`, `enable_group`, `enable_percentage_of_actors`, and the `Flipper[:x].enable` forms |
| remove | `Flipper.remove(:x)`, `Flipper[:x].remove` |

`Flipper.enabled?`, `Flipper.add`, `Flipper.remove`, `Flipper.exist?` and `Flipper.disable` are described in the Flipper docs. I did not check the other shapes against a specific Flipper version: confirm them in the version in use.

## What to look for

- `Flipper.enable(:x)` with no actor, group or percentage in a migration, seed or initializer: the code fixes the flag on, so only the enabled branch is reachable (`STALE-CONSTANT`).
- Checks hidden behind helpers (`def new_checkout?; Flipper.enabled?(:new_checkout, user); end`): search for the helper's callers too.
- Flag names in YAML, constants or `Flipper.enabled?(FLAG_NAME)`: the scanner reports these as dynamic names, read them by hand.
- Group registrations (`Flipper.register(:group)`) that only served this flag.
- Specs: `Flipper.enable(:x)` in `before` blocks, shared contexts and support files.

## Removing the record

Last step, after the code is deployed everywhere. `Flipper.remove(:x)` deletes the feature and all its gate data and the Flipper docs call it destructive, while `Flipper.disable(:x)` only turns it off. Run it as a reviewed one-off step (a console session or a job the owner approves). Flipper UI may offer a delete as well: check your version. Whether a check of a missing feature reads as off should be confirmed in the docs for your version, which is one more reason to deploy the code change first.
