import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "flag_scan.py"
spec = importlib.util.spec_from_file_location("flag_scan", SCRIPT)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def scan(tmp_path, files):
    return scanner.scan_project(write(tmp_path, files))


def flag(result, name, framework=None):
    matches = [f for f in result.flags if f.name == name and framework in (None, f.framework)]
    assert len(matches) == 1, (name, [(f.framework, f.name) for f in result.flags])
    return matches[0]


def definition(f):
    return next(s for s in f.sites if s.role == "define")


def codes(f):
    return {s.code for s in f.stale}


def ops(f):
    return sorted((s.role, s.op) for s in f.sites)


def test_flipper_check_forms(tmp_path):
    result = scan(tmp_path, {
        "app/models/user.rb": "Flipper.enabled?(:beta, user)\nFlipper.enabled? 'beta'\n",
        "app/views/a.html.erb": "<% if Flipper[:beta].enabled?(current_user) %>x<% end %>\n",
        "app/lib/b.rb": "Flipper.feature(:beta).enabled?\n",
    })
    f = flag(result, "beta", "flipper")
    assert [s.role for s in f.sites] == ["check"] * 4


def test_flipper_multiline_call_is_found(tmp_path):
    result = scan(tmp_path, {"app/a.rb": "x = Flipper.enabled?(\n  :wide,\n  user\n)\n"})
    f = flag(result, "wide")
    assert f.sites[0].line == 1


def test_flipper_define_toggle_and_remove(tmp_path):
    result = scan(tmp_path, {
        "db/seeds.rb": "Flipper.add(:gone)\nFlipper.enable_actor(:gone, user)\nFlipper.remove(:gone)\n",
    })
    assert ops(flag(result, "gone")) == [("define", "add"), ("remove", "remove"), ("toggle", "enable_actor")]


def test_flipper_dynamic_name_is_reported_not_attributed(tmp_path):
    result = scan(tmp_path, {"app/a.rb": "Flipper.enabled?(name)\nFlipper.enabled?(:real)\n"})
    assert [f.name for f in result.flags] == ["real"]
    assert [(d.file, d.line, d.framework) for d in result.dynamic] == [("app/a.rb", 1, "flipper")]


def test_commented_out_calls_are_ignored(tmp_path):
    result = scan(tmp_path, {
        "app/a.rb": "# Flipper.enabled?(:old)\n",
        "web/a.js": "// client.variation('old-js', false)\n * client.variation('old-js2', false)\n",
        "app/b.php": "// Feature::active('old-php');\n",
    })
    assert result.flags == []


def test_waffle_forms(tmp_path):
    result = scan(tmp_path, {
        "shop/views.py": (
            "import waffle\n"
            "if waffle.flag_is_active(request, 'new_ui'):\n    pass\n"
            "waffle.switch_is_active('kill_switch')\n"
            "sample_is_active(\"canary\")\n"
            "@waffle_flag('decorated')\ndef v(request): ...\n"
        ),
        "shop/templates/a.html": "{% load waffle_tags %}{% flag \"tpl_flag\" %}x{% else %}y{% endflag %}\n",
        "shop/migrations/0002.py": "Flag.objects.get_or_create(name='new_ui')\n",
    })
    names = sorted(f.name for f in result.flags)
    assert names == ["canary", "decorated", "kill_switch", "new_ui", "tpl_flag"]
    new_ui = flag(result, "new_ui")
    assert ops(new_ui) == [("check", "flag_is_active"), ("define", "create")]
    assert flag(result, "kill_switch").sites[0].variant == "switch"


def test_waffle_override_in_tests_is_a_test_toggle(tmp_path):
    result = scan(tmp_path, {"shop/tests/test_a.py": "with override_flag('x', active=True):\n    pass\n"})
    site = flag(result, "x").sites[0]
    assert (site.role, site.test) == ("toggle", True)


def test_waffle_constant_definition(tmp_path):
    result = scan(tmp_path, {
        "shop/migrations/0003.py": "Flag.objects.create(name='forever', everyone=True)\nSwitch.objects.create(name='off', active=False)\n",
    })
    assert codes(flag(result, "forever")) >= {"STALE-CONSTANT"}
    assert flag(result, "off").sites[0].const is False


def test_pennant_forms(tmp_path):
    result = scan(tmp_path, {
        "app/Providers/AppServiceProvider.php": "Feature::define('new-api', fn (User $u) => true);\nFeature::define('dyn', fn ($u) => $u->beta);\n",
        "app/Http/C.php": (
            "Feature::active('new-api');\nFeature::for($request->user())->active('dyn');\n"
            "Feature::for(auth()->user())->inactive('dyn');\nFeature::when('dyn', fn () => 1, fn () => 2);\n"
            "Feature::allAreActive(['dyn', 'extra']);\n"
        ),
        "resources/views/a.blade.php": "@feature('blade-flag')\n x\n@endfeature\n@featureany(['blade-flag', 'other'])\n@endfeatureany\n",
        "routes/web.php": "Route::get('/')->middleware(EnsureFeaturesAreActive::using('mw-a', 'mw-b'));\n",
    })
    assert len(flag(result, "dyn").sites) == 5
    assert {"extra", "blade-flag", "other", "mw-a", "mw-b"} <= {f.name for f in result.flags}
    assert definition(flag(result, "new-api")).const is True


def test_pennant_class_based_features_and_name_attribute(tmp_path):
    result = scan(tmp_path, {
        "app/Features/NewApi.php": "<?php\nclass NewApi {\n}\n",
        "app/Features/Renamed.php": "<?php\n#[Name('legacy-name')]\nclass Renamed {\n}\n",
        "app/Http/C.php": "Feature::active(NewApi::class);\nFeature::active(\\App\\Features\\Renamed::class);\n",
    })
    assert ops(flag(result, "NewApi")) == [("check", "active"), ("define", "class")]
    assert ops(flag(result, "legacy-name")) == [("check", "active"), ("define", "class")]


def test_pennant_purge_is_removal(tmp_path):
    result = scan(tmp_path, {"database/migrations/x.php": "Feature::purge('old');\nFeature::purge(['a', 'b']);\n"})
    assert {f.name for f in result.flags} == {"old", "a", "b"}
    assert flag(result, "old").sites[0].role == "remove"


def test_node_sdk_calls(tmp_path):
    result = scan(tmp_path, {
        "src/a.ts": (
            "const on = await ldClient.variation('ld-flag', ctx, false);\n"
            "client.boolVariation(\"ld-typed\", ctx, false);\n"
            "if (unleash.isEnabled('un-flag')) {}\n"
            "const v = unleash.getVariant('un-var');\n"
            "client.getBooleanValue('of-flag', false);\n"
            "client.getStringDetails('of-str', 'x');\n"
        ),
        "src/App.tsx": "const on = useFlag('un-hook'); const b = useBooleanFlagValue('of-hook', false);\n",
    })
    frameworks = {f.name: f.framework for f in result.flags}
    assert frameworks == {
        "ld-flag": "launchdarkly", "ld-typed": "launchdarkly", "un-flag": "unleash", "un-var": "unleash",
        "of-flag": "openfeature", "of-str": "openfeature", "un-hook": "unleash", "of-hook": "openfeature",
    }


def test_node_dynamic_launchdarkly_key(tmp_path):
    result = scan(tmp_path, {"src/a.js": "client.variation(key, ctx, false);\n"})
    assert result.flags == []
    assert [d.framework for d in result.dynamic] == ["launchdarkly"]


def test_same_name_in_two_frameworks_stays_separate(tmp_path):
    result = scan(tmp_path, {
        "a.rb": "Flipper.enabled?(:shared)\n",
        "b.js": "client.variation('shared', ctx, false)\n",
    })
    assert sorted(f.framework for f in result.flags if f.name == "shared") == ["flipper", "launchdarkly"]


def test_stale_defined_but_unused(tmp_path):
    result = scan(tmp_path, {"db/seeds.rb": "Flipper.add(:orphan)\n", "spec/a_spec.rb": "Flipper.enable(:orphan)\n"})
    assert "STALE-UNUSED" in codes(flag(result, "orphan"))


def test_stale_checked_but_undefined_only_where_code_can_define(tmp_path):
    result = scan(tmp_path, {
        "app/C.php": "Feature::active('ghost');\nFeature::active('ghost');\n",
        "web/a.js": "client.variation('remote', ctx, false);\nclient.variation('remote', ctx, false);\n",
    })
    assert "STALE-UNDEFINED" in codes(flag(result, "ghost"))
    assert "STALE-UNDEFINED" not in codes(flag(result, "remote"))


def test_undefined_for_flipper_only_when_project_registers_flags_in_code(tmp_path):
    files = {"app/a.rb": "Flipper.enabled?(:unregistered)\nFlipper.enabled?(:unregistered)\n"}
    assert "STALE-UNDEFINED" not in codes(flag(scan(tmp_path, files), "unregistered"))
    other = tmp_path / "other"
    files = {**files, "db/seeds.rb": "Flipper.add(:registered)\n", "app/b.rb": "Flipper.enabled?(:registered)\n"}
    assert "STALE-UNDEFINED" in codes(flag(scan(other, files), "unregistered"))


def test_stale_single_reference(tmp_path):
    result = scan(tmp_path, {
        "app/a.rb": "Flipper.enabled?(:lonely)\nFlipper.enabled?(:busy)\n",
        "app/b.rb": "Flipper.enabled?(:busy)\n",
        "spec/a_spec.rb": "Flipper.enable(:lonely)\n",
    })
    assert "STALE-SINGLE-REF" in codes(flag(result, "lonely"))
    assert "STALE-SINGLE-REF" not in codes(flag(result, "busy"))


def test_stale_constant_branch_flipper_enable_everyone_only(tmp_path):
    result = scan(tmp_path, {
        "db/migrate/1.rb": "Flipper.enable(:always_on)\nFlipper.enable(:partial, user)\nFlipper.enable(:flip)\nFlipper.disable(:flip)\n",
        "app/a.rb": "Flipper.enabled?(:always_on)\nFlipper.enabled?(:partial)\nFlipper.enabled?(:flip)\nFlipper.enabled?(:always_on)\n",
    })
    assert "STALE-CONSTANT" in codes(flag(result, "always_on"))
    assert "STALE-CONSTANT" not in codes(flag(result, "partial"))
    assert "STALE-CONSTANT" not in codes(flag(result, "flip"))


def test_stale_constant_branch_pennant(tmp_path):
    result = scan(tmp_path, {
        "app/P.php": "Feature::define('on', fn () => true);\nFeature::define('off', false);\nFeature::define('cond', fn ($u) => $u->x);\n",
        "app/C.php": "Feature::active('on');\nFeature::active('off');\nFeature::active('cond');\n",
    })
    assert definition(flag(result, "on")).const is True
    assert definition(flag(result, "off")).const is False
    assert "STALE-CONSTANT" in codes(flag(result, "off"))
    assert "STALE-CONSTANT" not in codes(flag(result, "cond"))


def test_healthy_flag_has_no_stale_codes(tmp_path):
    result = scan(tmp_path, {
        "app/a.rb": "Flipper.enabled?(:fine)\n",
        "app/b.rb": "Flipper.enabled?(:fine)\n",
        "db/seeds.rb": "Flipper.add(:fine)\n",
    })
    assert flag(result, "fine").stale == []


def test_test_paths_are_marked(tmp_path):
    result = scan(tmp_path, {
        "spec/models/u_spec.rb": "Flipper.enabled?(:t)\n",
        "src/__tests__/a.js": "client.variation('t2', c, false)\n",
        "src/a.test.ts": "client.variation('t3', c, false)\n",
        "tests/test_a.py": "waffle.switch_is_active('t4')\n",
        "app/real.rb": "Flipper.enabled?(:r)\n",
    })
    assert [flag(result, n).sites[0].test for n in ("t", "t2", "t3", "t4", "r")] == [True, True, True, True, False]


def test_secret_files_and_noise_dirs_are_never_read(tmp_path):
    result = scan(tmp_path, {
        ".hidden-config": "Flipper.enabled?(:from_hidden)\n",
        ".hidden.rb": "Flipper.enabled?(:from_hidden_rb)\n",
        "config/credentials.yml.enc": "Flipper.enabled?(:from_cred)\n",
        "config/database.yml": "Flipper.enabled?(:from_db)\n",
        "secrets.rb": "Flipper.enabled?(:from_secrets)\n",
        "node_modules/x/index.js": "client.variation('nm', c, false)\n",
        "vendor/y.rb": "Flipper.enabled?(:vendored)\n",
        "app/ok.rb": "Flipper.enabled?(:ok)\n",
    })
    assert [f.name for f in result.flags] == ["ok"]


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    write(outside, {"leak.rb": "Flipper.enabled?(:leaked)\n"})
    project = tmp_path / "project"
    write(project, {"app/a.rb": "Flipper.enabled?(:kept)\n"})
    (project / "app" / "link.rb").symlink_to(outside / "leak.rb")
    result = scanner.scan_project(project)
    assert [f.name for f in result.flags] == ["kept"]


def test_framework_filter(tmp_path):
    write(tmp_path, {"a.rb": "Flipper.enabled?(:a)\n", "b.js": "client.variation('b', c, false)\n"})
    result = scanner.scan_project(tmp_path, frameworks={"flipper"})
    assert [f.name for f in result.flags] == ["a"]


def test_paths_are_relative_and_sites_sorted(tmp_path):
    result = scan(tmp_path, {"z.rb": "Flipper.enabled?(:s)\n", "a.rb": "Flipper.enabled?(:s)\n\nFlipper.enabled?(:s)\n"})
    assert [(s.file, s.line) for s in flag(result, "s").sites] == [("a.rb", 1), ("a.rb", 3), ("z.rb", 1)]


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_cli_json_and_exit_code_when_stale(tmp_path):
    write(tmp_path, {"app/a.rb": "Flipper.enabled?(:lonely)\n"})
    proc = run_cli(str(tmp_path), "--json")
    assert proc.returncode == 1
    data = json.loads(proc.stdout)
    assert data["flags"][0]["name"] == "lonely"
    assert data["flags"][0]["stale"][0]["code"] == "STALE-SINGLE-REF"
    assert data["summary"] == {"flags": 1, "stale": 1}
    assert "dynamic_sites" in data


def test_cli_exit_zero_when_clean_and_text_output(tmp_path):
    write(tmp_path, {"a.rb": "Flipper.enabled?(:fine)\n", "b.rb": "Flipper.enabled?(:fine)\n", "s.rb": "Flipper.add(:fine)\n"})
    proc = run_cli(str(tmp_path))
    assert proc.returncode == 0
    assert "fine" in proc.stdout and "flipper" in proc.stdout


def test_cli_rejects_missing_directory(tmp_path):
    proc = run_cli(str(tmp_path / "nope"))
    assert proc.returncode == 2
    assert "not a directory" in proc.stderr


@pytest.mark.parametrize("name", ["scan_project", "main"])
def test_public_api_exists(name):
    assert callable(getattr(scanner, name))


def test_settings_and_connection_config_files_are_never_read(tmp_path):
    result = scan(tmp_path, {
        "app/settings.py": "waffle.switch_is_active('s1')\n",
        "app/local_settings.py": "waffle.switch_is_active('s2')\n",
        "config/database.php": "Feature::active('s3');\n",
        ".hidden.js": "client.variation('s4', c, false)\n",
        "app/ok.py": "waffle.switch_is_active('ok')\n",
    })
    assert [f.name for f in result.flags] == ["ok"]


def test_non_regular_files_are_skipped(tmp_path):
    import os
    write(tmp_path, {"app/ok.rb": "Flipper.enabled?(:ok)\n"})
    os.mkfifo(tmp_path / "app" / "pipe.rb")
    assert [f.name for f in scanner.scan_project(tmp_path).flags] == ["ok"]


def test_runtime_toggle_does_not_make_other_flipper_flags_undefined(tmp_path):
    result = scan(tmp_path, {
        "app/c.rb": "Flipper.enable_actor(:a, user)\nFlipper.enabled?(:b)\nFlipper.enabled?(:b)\n",
    })
    assert "STALE-UNDEFINED" not in codes(flag(result, "b"))


def test_interpolated_names_are_dynamic(tmp_path):
    result = scan(tmp_path, {
        "app/a.rb": 'Flipper.enabled?("dyn_#{x}")\n',
        "src/a.js": "client.variation(`ld-${env}`, c, false);\nclient.getBooleanValue(`plain`, false);\n",
    })
    assert [f.name for f in result.flags] == ["plain"]
    assert sorted(d.framework for d in result.dynamic) == ["flipper", "launchdarkly"]


def test_waffle_variable_names_are_dynamic(tmp_path):
    result = scan(tmp_path, {
        "a.py": "waffle.flag_is_active(request, name)\nwaffle.switch_is_active(name)\nwaffle.flag_is_active(request, 'lit')\n",
    })
    assert [f.name for f in result.flags] == ["lit"]
    assert [d.line for d in result.dynamic] == [1, 2]


def test_waffle_has_no_sample_decorator(tmp_path):
    assert scan(tmp_path, {"a.py": "@waffle_sample('x')\ndef v(): ...\n"}).flags == []


def test_django_settings_package_is_skipped_but_similar_names_are_not(tmp_path):
    result = scan(tmp_path, {
        "proj/settings/production.py": "waffle.switch_is_active('p1')\n",
        "app/views/user_settings.py": "waffle.switch_is_active('kept')\n",
    })
    assert [f.name for f in result.flags] == ["kept"]


def test_php_interpolated_names_are_dynamic(tmp_path):
    result = scan(tmp_path, {"app/C.php": 'Feature::active("beta-$x");\nFeature::active("b-{$x}");\nFeature::active(\'plain\');\n'})
    assert [f.name for f in result.flags] == ["plain"]
    assert len(result.dynamic) == 2


def test_settings_module_variants_are_skipped(tmp_path):
    files = {f"app/{n}.py": f"waffle.switch_is_active('{n}')\n" for n in
             ("settings", "local_settings", "test_settings", "prod_settings", "settings_local", "base")}
    assert [f.name for f in scan(tmp_path, files).flags] == ["base"]


def test_hidden_directories_and_virtualenvs_are_skipped(tmp_path):
    result = scan(tmp_path, {
        ".hidden-dir/x.rb": "Flipper.enabled?(:hid)\n",
        "venvdir/pyvenv.cfg": "home = x\n",
        "venvdir/lib/y.rb": "Flipper.enabled?(:venv)\n",
        "app/ok.rb": "Flipper.enabled?(:ok)\n",
    })
    assert [f.name for f in result.flags] == ["ok"]
