# Removal plan for one flag

Write one plan per flag. Each numbered step must leave the application correct, so steps can ship separately.

## 0. Confirm before touching code

Code cannot show the live state. Ask the owner, or ask them to look in the flag UI, for:

- The value for everyone in every environment (on, off, or a partial rollout).
- Whether the flag has been stable long enough to trust it.
- Whether other services, repositories, jobs or client builds read the same flag.

If it is a partial rollout or varies by environment, the flag is not ready for removal. Say so and stop.

## 1. Choose the branch to keep

The branch to keep is the one production runs for everyone. Flag on: keep the "enabled" branch. Flag off: keep the "disabled" branch, which usually means deleting the new feature code. State the choice as something to confirm.

## 2. Edit the call sites

For each check, list `file:line` and the edit:

- Replace the conditional with the kept branch and delete the other. Remove `else` branches, ternaries and early returns that existed only for the flag.
- Templates: keep the content of the kept side, delete the tags (`{% flag %}`, `@feature`, `<% if Flipper... %>`).
- Delete code that became unreachable: methods, classes, routes, translations, background jobs, CSS and feature-specific database columns (a column drop needs its own migration and review).
- Middleware and route guards (`EnsureFeaturesAreActive::using`, `@waffle_flag`) are removed, or the route is deleted when the kept branch is "off".

## 3. Update the tests

- Delete flag stubs and overrides (`Flipper.enable` in specs, `override_flag`, `Feature::activate`, mocked SDK clients).
- Keep the tests that cover the kept branch, without the flag setup.
- Delete the tests that only covered the removed branch.
- Check shared setup (factories, fixtures, `before` blocks, `conftest.py`, test bootstrap files) for flag setup.

## 4. Remove the code definition

Pennant `Feature::define` calls and class-based feature files, `Flipper.add` calls in initializers or seeds, waffle data migrations that create the flag. Leave old migrations that already ran in place unless the project's rule says otherwise.

## 5. Ship, then delete the flag record last

Deploy steps 2 to 4 everywhere first. Only then delete the record, in its own step. Deleting it earlier can change what code that is still running sees. Use the system's own tool (see the framework reference), and treat it as a production data change that needs the owner's go-ahead: this plugin does not run it.

For flags in a hosted service (LaunchDarkly, Unleash, or whatever OpenFeature talks to), archiving or deleting the flag happens in that service, by its owner.

## 6. Verify

- Grep the flag name again, including strings, YAML, JSON, docs, runbooks and dashboards.
- Run the specs for every touched file and their neighbours.
- Watch error rates after the deploy of step 2, and again after step 5.

## Plan template

```
Flag: <name> (<system>)
Confirm: value for everyone is <on/off>? other readers? (owner)
Keep: <enabled/disabled> branch
1. <file:line> keep <branch>, delete <other>
2. Tests: <files> remove setup / delete cases
3. Remove definition: <file:line>
4. Deploy
5. Delete flag record: <system-specific step>, owner approval
```
