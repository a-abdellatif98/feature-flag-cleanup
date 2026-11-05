# django-waffle

Waffle has three kinds: flags (per request, with rules such as percent and groups), switches (global on/off) and samples (a random percentage). They are database records. Names are strings and a flag and a switch can share a name; the scanner keys by name and records the kind as the site's variant.

## Call shapes the scanner reads

| Role | Shape |
|---|---|
| check | `waffle.flag_is_active(request, 'x')`, `waffle.switch_is_active('x')`, `waffle.sample_is_active('x')` |
| check | decorators `@waffle_flag('x')` and `@waffle_switch('x')` |
| check | template tags `{% flag "x" %}...{% else %}...{% endflag %}` after `{% load waffle_tags %}`, and the `switch` and `sample` tags |
| toggle | `override_flag('x', ...)`, `override_switch`, `override_sample` from waffle's test utilities |
| define | `Flag.objects.create(name='x')`, `get_or_create`, `update_or_create`, likewise `Switch` and `Sample`, usually in data migrations |

The check functions and template tags are in the waffle docs. Confirm the decorator and test utility names for your version.

## What to look for

- `everyone=True` (flags) or `active=True` (switches) in a data migration: the initial value is fixed (`STALE-CONSTANT`), but admin edits can change it later.
- Flag names in JavaScript (waffle can expose flags to the front end) and in templates: Grep `.html` files as well as Python. JavaScript reads are outside the scanner.
- Names passed through a variable: reported as dynamic names where the first argument is not a literal.
- Tests: `override_flag` usage, fixtures that load waffle records.
- Creating missing records on first check is configurable in waffle (see its settings docs): in such projects a flag can have a database row nobody created by hand.

## Removing the record

Last step, after the code is deployed everywhere. Waffle ships a `waffle_delete` management command with `--flags`, `--switches` and `--samples` options that each take names. Run it as a reviewed one-off step; this plugin does not run it. Alternatively remove the record in the Django admin, or with a data migration that is reversible only if the project needs that. Remove the migration that created the flag only if project policy allows editing history; the usual choice is to leave it.
