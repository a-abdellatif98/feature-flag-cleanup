# LaunchDarkly, Unleash and OpenFeature in Node

These are service-backed: the flag is created and set in a hosted or self-hosted service, and code only evaluates it. Code therefore can never show a definition or the live value. The scanner reads JavaScript and TypeScript sources (`.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.vue`, `.svelte`) and never contacts the service.

## Call shapes the scanner reads

| System | Shape |
|---|---|
| LaunchDarkly | `client.variation('key', context, default)`, `variationDetail`, and the typed variants `boolVariation`, `stringVariation`, `numberVariation`, `jsonVariation` (typed variants exist in newer SDK versions: confirm for yours) |
| Unleash | `unleash.isEnabled('name', context)`, `getVariant('name')`, and the React hooks `useFlag('name')`, `useVariant('name')` |
| OpenFeature | `client.getBooleanValue('key', default)`, `getStringValue`, `getNumberValue`, `getObjectValue`, and the `...Details` forms; React hooks such as `useBooleanFlagValue('key', default)` (confirm the hook names in your React SDK version) |

The method names are matched on any receiver, so a method with the same name in an unrelated library is a false positive. Calls whose first argument is a variable are listed as dynamic names for LaunchDarkly and OpenFeature.

## Not covered by the scanner

- LaunchDarkly React `useFlags()`, where flags are read as properties of the returned object. Grep for the destructured names by hand (the SDK exposes keys in camelCase by default: confirm in its docs).
- Wrapper functions around the SDK call, and flag keys held in constants or enums.
- Server-rendered templates that read the flag through a helper.

## Removal notes

- Remove the code first, deploy, then archive or delete the flag in the service. Archiving or deleting in the service is done by the flag owner there. This plugin never calls the service API.
- Several services or client builds can evaluate the same flag key. Before the service-side step, the owner confirms nothing else still asks for it. An evaluation of a missing flag falls back to the default value in the call, so the default shows which branch a client would take; check the SDK docs for your version.
- The `default` argument is the branch taken when the service is unreachable. When the flag is fully on, keep the branch production serves, not the one in the default.
