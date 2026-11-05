# Laravel Pennant

Features are defined in code (closures registered with `Feature::define`, or classes) and resolved values are stored by a driver (database by default).

## Call shapes the scanner reads

| Role | Shape |
|---|---|
| define | `Feature::define('x', fn (User $user) => ...)`, and class-based features in `app/Features` |
| check | `Feature::active('x')`, `inactive`, `value`, `when`, `unless`, with or without `Feature::for($user)->` |
| check | `Feature::allAreActive([...])`, `someAreActive([...])` |
| check | Blade `@feature('x')`, `@featureany([...])` |
| check | `EnsureFeaturesAreActive::using('x', 'y')` as route middleware |
| toggle | `Feature::activate`, `deactivate`, `activateForEveryone`, `deactivateForEveryone`, `forget` |
| remove | `Feature::purge('x')`, `Feature::purge([...])` |

These names are in the Pennant docs.

## Class-based features

By default Pennant stores the fully qualified class name. A `Name` attribute on the class stores a custom name instead. The scanner treats a class in a `Features` directory as the definition, uses the `Name` attribute when it finds one, and maps `Feature::active(NewApi::class)` to the same flag. A class referenced only by its stored string, or generated at runtime, is not linked.

## What to look for

- `Feature::define('x', fn () => true)` or `false`: constant flag, one branch unreachable (`STALE-CONSTANT`). `Feature::activateForEveryone('x')` in a migration means the stored values are fixed for everyone, but a closure can still decide for new scopes.
- Checks in Blade, route middleware and policies as well as controllers.
- Features defined in a service provider and checked nowhere (`STALE-UNUSED`), or checked and defined nowhere (`STALE-UNDEFINED`). For an undefined feature, read the Pennant docs for your version to see what a check does.
- Rich values (`Feature::value('x')` returning strings): keep the branch for the value production resolves, not just true or false.

## Removing the record

Two parts, in this order. First remove the definition (the `Feature::define` call or the feature class) and the checks, and deploy. Then purge the stored values: Pennant provides `Feature::purge('x')` and the `php artisan pennant:purge x` command, which the docs describe for features removed from the application. Purge is a production data change: the owner approves and runs it, this plugin does not.
