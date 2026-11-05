#!/usr/bin/env python3
"""Static scan for feature flags and their call sites (Flipper, django-waffle, Laravel Pennant, Node SDKs)."""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field

SKIP_DIRS = {
    "node_modules", "vendor", "__pycache__", "tmp", "log", "storage", "dist", "build",
    "coverage", "venv", "env", "site-packages", "bower_components",
}
SKIP_SUFFIXES = (".pem", ".key", ".enc", ".p12", ".min.js")
SKIP_NAME_PARTS = ("secret", "credential", "database.yml", "database.php", "settings.py", "master.key", ".npmrc")
MAX_BYTES = 1_000_000
TEST_DIRS = {"spec", "test", "tests", "__tests__", "e2e", "cypress"}
TEST_NAME = re.compile(r"(_spec\.rb|_test\.rb|_test\.py|^test_.*\.py|^conftest\.py|\.(spec|test)\.[jt]sx?|Test\.php)$")

CHECK, DEFINE, TOGGLE, REMOVE = "check", "define", "toggle", "remove"
NEUTRAL_OPS = {"add"}
CODE_REGISTERED = {"pennant"}
REGISTERED_BY_CONVENTION = {"flipper", "waffle"}

QUOTED = r"""(?P<q>['"`])(?P<str>[^'"`\n]+)(?P=q)"""
NAME_SYM = rf"(?::(?P<sym>\w+)|{QUOTED})"
NAME_PENNANT = rf"(?:{QUOTED}|(?P<cls>[\\\w]+)::class)"
FOR_SCOPE = r"(?:for\((?:[^()]|\([^()]*\))*\)\s*->\s*)?"
DYNAMIC_START = r"(?=[A-Za-z_@$])(?![\w\\]+::class)"
OPTIONAL_REQUEST = r"(?:[A-Za-z_][\w.]*\s*,\s*)?"
GENERICS = r"(?:<[^>()]*>)?"


@dataclass
class Rule:
    framework: str
    exts: tuple
    role: str
    pattern: re.Pattern
    op: str = None
    const: bool = None
    const_fn: object = None
    dyn: re.Pattern = None
    multi: bool = False


def rule(framework, exts, role, head, name=None, tail="", op=None, const=None, const_fn=None, dyn=True):
    pattern = re.compile(head + name + tail, re.M)
    dyn_pattern = None
    if dyn is True:
        dyn_pattern = re.compile(head + DYNAMIC_START, re.M)
    elif dyn:
        dyn_pattern = re.compile(dyn, re.M)
    return Rule(framework, exts, role, pattern, op, const, const_fn, dyn_pattern)


def multi_rule(framework, exts, role, pattern, op):
    return Rule(framework, exts, role, re.compile(pattern, re.M), op, multi=True)


RB = (".rb", ".rake", ".erb", ".haml", ".slim")
PY = (".py", ".html", ".jinja", ".jinja2", ".txt")
PHP = (".php",)
JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte")
FLIPPER_CALL = r"\bFlipper\.%s\(?\s*"
FLIPPER_INDEX = r"\bFlipper\[\s*"
FLIPPER_ONLY_NAME = r"(?=[ \t]*(?:\)|$))"
FLIPPER_BARE = r"\s*\]\s*\.\s*%s(?:\(\s*\))?(?=[ \t]*(?:$|[;#]))"
TOGGLE_OP = r"(?P<op>(?:enable|disable)(?:_\w+)?)(?![\w?!])"
PENNANT_CALL = r"\bFeature::" + FOR_SCOPE
WAFFLE_VARIANT = r"(?P<variant>flag|switch|sample)"
WAFFLE_DYNAMIC = r"\bflag_is_active\(\s*[\w.]+\s*,\s*(?=[A-Za-z_])|\b(?:switch|sample)_is_active\(\s*(?=[A-Za-z_])"


def pennant_const(text, match):
    rest = text[match.end():args_end(text, match.end())]
    value = r"(true|false)"
    arrow = r"fn\s*\([^)]*\)\s*=>\s*"
    closure = r"function\s*\([^)]*\)\s*(?:use\s*\([^)]*\)\s*)?\{\s*return\s*"
    found = re.fullmatch(rf"\s*,\s*(?:{arrow}|{closure})?{value}\s*;?\s*\}}?\s*", rest, re.I)
    return None if not found else found.group(1).lower() == "true"


def waffle_const(text, match):
    args = text[match.end():args_end(text, match.end())]
    found = re.search(r"""\b(?:everyone|active)\s*=\s*(True|False)\b|['"](?:everyone|active)['"]\s*:\s*(True|False)\b""", args)
    if not found:
        return None
    return (found.group(1) or found.group(2)) == "True"


def args_end(text, pos):
    depth = 1
    for i in range(pos, min(len(text), pos + 2000)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return min(len(text), pos + 2000)


RULES = [
    rule("flipper", RB, CHECK, FLIPPER_CALL % r"enabled\?", NAME_SYM, op="enabled"),
    rule("flipper", RB, CHECK, FLIPPER_INDEX, NAME_SYM, r"\s*\]\s*\.\s*enabled\?", "enabled", dyn=False),
    rule("flipper", RB, CHECK, r"\bFlipper\.feature\(\s*", NAME_SYM, r"\s*\)\s*\.\s*enabled\?", "enabled", dyn=False),
    rule("flipper", RB, TOGGLE, r"\bFlipper\.enable\(?[ \t]*", NAME_SYM, FLIPPER_ONLY_NAME, "enable", const=True, dyn=False),
    rule("flipper", RB, TOGGLE, r"\bFlipper\.disable\(?[ \t]*", NAME_SYM, FLIPPER_ONLY_NAME, "disable", const=False, dyn=False),
    rule("flipper", RB, TOGGLE, FLIPPER_INDEX, NAME_SYM, FLIPPER_BARE % "enable", "enable", const=True, dyn=False),
    rule("flipper", RB, TOGGLE, FLIPPER_INDEX, NAME_SYM, FLIPPER_BARE % "disable", "disable", const=False, dyn=False),
    rule("flipper", RB, TOGGLE, r"\bFlipper\." + TOGGLE_OP + r"\(?[ \t]*", NAME_SYM, dyn=False),
    rule("flipper", RB, TOGGLE, FLIPPER_INDEX, NAME_SYM, r"\s*\]\s*\.\s*" + TOGGLE_OP, dyn=False),
    rule("flipper", RB, DEFINE, FLIPPER_CALL % "add", NAME_SYM, op="add", dyn=False),
    rule("flipper", RB, REMOVE, FLIPPER_CALL % "remove", NAME_SYM, op="remove", dyn=False),
    rule("flipper", RB, REMOVE, FLIPPER_INDEX, NAME_SYM, r"\s*\]\s*\.\s*remove\b", "remove", dyn=False),

    rule("waffle", PY, CHECK, rf"\b(?P<op>{WAFFLE_VARIANT}_is_active)\(\s*{OPTIONAL_REQUEST}", QUOTED, dyn=WAFFLE_DYNAMIC),
    rule("waffle", PY, CHECK, r"@waffle_(?P<variant>flag|switch)\(\s*", QUOTED, op="decorator", dyn=False),
    rule("waffle", PY, CHECK, r"\{%-?\s*" + WAFFLE_VARIANT + r"\s+", QUOTED, op="tag", dyn=False),
    rule("waffle", PY, TOGGLE, r"\boverride_" + WAFFLE_VARIANT + r"\(\s*", QUOTED, op="override", dyn=False),
    rule("waffle", PY, DEFINE, r"\b(?P<variant>Flag|Switch|Sample)\.objects\.(?:create|get_or_create|update_or_create)\(\s*name\s*=\s*",
         QUOTED, op="create", const_fn=waffle_const, dyn=False),

    rule("pennant", PHP, DEFINE, r"\bFeature::define\(\s*", NAME_PENNANT, op="define", const_fn=pennant_const),
    rule("pennant", PHP, CHECK, PENNANT_CALL + r"(?P<op>active|inactive|value|when|unless)\(\s*", NAME_PENNANT),
    rule("pennant", PHP, TOGGLE, PENNANT_CALL + r"activateForEveryone\(\s*", NAME_PENNANT, FLIPPER_ONLY_NAME, "activateForEveryone", const=True, dyn=False),
    rule("pennant", PHP, TOGGLE, PENNANT_CALL + r"deactivateForEveryone\(\s*", NAME_PENNANT, FLIPPER_ONLY_NAME, "deactivateForEveryone", const=False, dyn=False),
    rule("pennant", PHP, TOGGLE, PENNANT_CALL + r"(?P<op>activate|deactivate|activateForEveryone|deactivateForEveryone|forget)\(\s*", NAME_PENNANT, dyn=False),
    rule("pennant", PHP, REMOVE, r"\bFeature::purge\(\s*", NAME_PENNANT, op="purge", dyn=False),
    rule("pennant", PHP, CHECK, r"@feature\(\s*", NAME_PENNANT, op="feature", dyn=False),
    multi_rule("pennant", PHP, CHECK, r"\bFeature::" + FOR_SCOPE + r"(?P<op>allAreActive|someAreActive|allAreInactive|someAreInactive)\(\s*\[(?P<args>[^\]]*)\]", None),
    multi_rule("pennant", PHP, CHECK, r"@featureany\(\s*\[(?P<args>[^\]]*)\]", "featureany"),
    multi_rule("pennant", PHP, CHECK, r"\bEnsureFeaturesAreActive::using\((?P<args>[^)]*)\)", "middleware"),
    multi_rule("pennant", PHP, REMOVE, r"\bFeature::purge\(\s*\[(?P<args>[^\]]*)\]", "purge"),

    rule("launchdarkly", JS, CHECK,
         r"\.(?P<op>variation|variationDetail|(?:bool|string|number|json)Variation(?:Detail)?)" + GENERICS + r"\(\s*", QUOTED),
    rule("unleash", JS, CHECK, r"\.(?P<op>isEnabled|getVariant)" + GENERICS + r"\(\s*", QUOTED, dyn=False),
    rule("unleash", JS, CHECK, r"\b(?P<op>useFlag|useVariant)" + GENERICS + r"\(\s*", QUOTED, dyn=False),
    rule("openfeature", JS, CHECK, r"\.(?P<op>get(?:Boolean|String|Number|Object)(?:Value|Details))" + GENERICS + r"\(\s*", QUOTED),
    rule("openfeature", JS, CHECK, r"\b(?P<op>use(?:Boolean|String|Number|Object)Flag(?:Value|Details))" + GENERICS + r"\(\s*", QUOTED),
]

FRAMEWORKS = sorted({r.framework for r in RULES})
STALE_ORDER = ["STALE-UNUSED", "STALE-CONSTANT", "STALE-UNDEFINED", "STALE-SINGLE-REF"]


@dataclass
class Site:
    file: str
    line: int
    role: str
    op: str
    test: bool
    variant: str = None
    const: bool = None


@dataclass
class Stale:
    code: str
    message: str


@dataclass
class Flag:
    framework: str
    name: str
    sites: list = field(default_factory=list)
    stale: list = field(default_factory=list)


@dataclass
class Dynamic:
    file: str
    line: int
    framework: str


@dataclass
class Result:
    flags: list
    dynamic: list


def is_test_path(rel):
    parts = rel.split("/")
    return bool(TEST_DIRS & set(parts[:-1])) or bool(TEST_NAME.search(parts[-1]))


def is_comment(line, ext):
    text = line.strip()
    if ext in (".py", ".rb", ".rake"):
        return text.startswith("#")
    if ext in (".erb", ".haml", ".slim"):
        return text.startswith(("#", "<%#", "-#"))
    if ext in PHP:
        return text.startswith(("//", "/*", "*")) or (text.startswith("#") and not text.startswith("#["))
    if ext in JS:
        return text.startswith(("//", "/*", "*"))
    return text.startswith(("<!--", "{#"))


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def line_text(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:end if end != -1 else len(text)]


def literal_names(match):
    groups = match.groupdict()
    if groups.get("sym"):
        return [(groups["sym"], False)]
    if groups.get("str"):
        return [(groups["str"], False)]
    return [(groups["cls"].split("\\")[-1], True)]


def multi_names(args):
    found = [(m.group("str"), False) for m in re.finditer(QUOTED, args)]
    found += [(m.group(1).split("\\")[-1], True) for m in re.finditer(r"([\\\w]+)::class", args)]
    return found


def scan_file(rel, ext, text, frameworks):
    test = is_test_path(rel)
    records, dynamic = {}, []
    for r in RULES:
        if ext not in r.exts or r.framework not in frameworks:
            continue
        for m in r.pattern.finditer(text):
            if is_comment(line_text(text, m.start()), ext):
                continue
            groups = m.groupdict()
            op = r.op or groups.get("op")
            variant = (groups.get("variant") or "").lower() or None
            const = r.const if r.const is not None else (r.const_fn(text, m) if r.const_fn else None)
            names = multi_names(groups["args"]) if r.multi else literal_names(m)
            for index, (name, via_class) in enumerate(names):
                if "#{" in name or "${" in name:
                    dynamic.append(Dynamic(rel, line_of(text, m.start()), r.framework))
                    continue
                key = (m.start(), index)
                site = Site(rel, line_of(text, m.start()), r.role, op, test, variant, const)
                previous = records.get(key)
                if previous is None or (previous[1].const is None and site.const is not None):
                    records[key] = ((r.framework, name, via_class), site)
        if r.dyn:
            dynamic += [Dynamic(rel, line_of(text, m.start()), r.framework)
                        for m in r.dyn.finditer(text) if not is_comment(line_text(text, m.start()), ext)]
    return list(records.values()), dynamic


def pennant_class_definition(rel, ext, text):
    if ext != ".php" or "Features" not in rel.split("/")[:-1]:
        return None
    klass = re.search(r"^\s*(?:final\s+|abstract\s+)?class\s+(\w+)", text, re.M)
    if not klass:
        return None
    renamed = re.search(r"""#\[\s*Name\(\s*['"]([^'"]+)['"]\s*\)\s*\]""", text)
    return klass.group(1), (renamed.group(1) if renamed else klass.group(1)), line_of(text, klass.start())


def skipped_file(name):
    lower = name.lower()
    return (
        lower.startswith(".env") or lower.endswith(SKIP_SUFFIXES)
        or any(part in lower for part in SKIP_NAME_PARTS)
    )


def project_files(root):
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            path = os.path.join(current, name)
            ext = os.path.splitext(name)[1].lower()
            if skipped_file(name) or os.path.islink(path):
                continue
            if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
                continue
            yield os.path.relpath(path, root).replace(os.sep, "/"), path, ext


def scan_project(root, frameworks=None):
    frameworks = set(frameworks or FRAMEWORKS)
    collected, dynamic, aliases = [], [], {}
    for rel, path, ext in project_files(root):
        if not any(ext in r.exts for r in RULES):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        records, dyn = scan_file(rel, ext, text, frameworks)
        collected += records
        dynamic += dyn
        klass = pennant_class_definition(rel, ext, text) if "pennant" in frameworks else None
        if klass:
            aliases[klass[0]] = klass[1]
            collected.append((("pennant", klass[0], True), Site(rel, klass[2], DEFINE, "class", is_test_path(rel))))
    flags = {}
    for (framework, name, via_class), site in collected:
        if framework == "pennant" and via_class:
            name = aliases.get(name, name)
        flags.setdefault((framework, name), Flag(framework, name)).sites.append(site)
    ordered = sorted(flags.values(), key=lambda f: (f.framework, f.name))
    for f in ordered:
        f.sites.sort(key=lambda s: (s.file, s.line, s.role))
    dynamic.sort(key=lambda d: (d.file, d.line))
    mark_stale(ordered, {d.framework for d in dynamic})
    return Result(ordered, dynamic)


def mark_stale(flags, dynamic_frameworks):
    registers = {
        f.framework for f in flags for s in f.sites
        if not s.test and (s.role == DEFINE or (s.role == TOGGLE and s.const is not None))
    }
    for f in flags:
        prod = [s for s in f.sites if not s.test]
        checks = [s for s in prod if s.role == CHECK]
        setters = [s for s in prod if s.role in (DEFINE, TOGGLE)]
        found = {}
        if setters and not checks:
            found["STALE-UNUSED"] = "defined or toggled in code, but no non-test call site checks it"
        values = {s.const for s in setters if s.const is not None}
        variable = any(s.const is None and s.op not in NEUTRAL_OPS for s in setters)
        if len(values) == 1 and not variable:
            state = "on" if values == {True} else "off"
            found["STALE-CONSTANT"] = f"code only ever sets it {state}, so only the {state} branch is reachable (the flag store may differ)"
        expects_definition = f.framework in CODE_REGISTERED or (f.framework in REGISTERED_BY_CONVENTION and f.framework in registers)
        if checks and not setters and expects_definition:
            found["STALE-UNDEFINED"] = "checked in code, but no definition or registration found in code"
        if len(prod) == 1:
            found["STALE-SINGLE-REF"] = "only one non-test reference in the scanned code"
        suffix = " (dynamic flag names exist for this framework, confirm)" if f.framework in dynamic_frameworks else ""
        f.stale = [Stale(code, found[code] + suffix) for code in STALE_ORDER if code in found]


def to_dict(result):
    flags = [asdict(f) for f in result.flags]
    stale = sum(1 for f in result.flags if f.stale)
    return {
        "flags": flags,
        "dynamic_sites": [asdict(d) for d in result.dynamic],
        "summary": {"flags": len(flags), "stale": stale},
    }


def render_text(result):
    if not result.flags:
        return "No flags found.\n"
    lines = []
    for f in result.flags:
        lines.append(f"{f.name}  [{f.framework}]  {len(f.sites)} site(s)")
        for s in f.sites:
            where = "test" if s.test else "code"
            lines.append(f"  {s.file}:{s.line}  {s.role}/{s.op}  {where}")
        lines += [f"  {s.code}: {s.message}" for s in f.stale]
    for d in result.dynamic:
        lines.append(f"dynamic flag name: {d.file}:{d.line} [{d.framework}]")
    stale = sum(1 for f in result.flags if f.stale)
    lines.append(f"{len(result.flags)} flag(s), {stale} likely stale")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="List feature flags and call sites, and mark likely-stale ones.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--framework", action="append", choices=FRAMEWORKS)
    args = parser.parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    result = scan_project(args.root, set(args.framework) if args.framework else None)
    sys.stdout.write(json.dumps(to_dict(result), indent=2) + "\n" if args.json else render_text(result))
    return 1 if any(f.stale for f in result.flags) else 0


if __name__ == "__main__":
    sys.exit(main())
