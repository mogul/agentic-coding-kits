"""Regression tests for shared dispatch, staging, and fail-closed validation."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_script("validate-kits")
runner = load_script("run-kit-tests")


@pytest.fixture
def kits(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in runner.KIT_NAMES:
        kit = root / name
        kit.mkdir()
        (kit / "spec.yaml").write_text(yaml.safe_dump({"name": name}), encoding="utf-8")
        (kit / "files/.hidden").mkdir(parents=True)
        (kit / "files/.hidden/payload").write_text("payload", encoding="utf-8")
    return root


def test_stages_every_root_kit_and_hidden_payload(kits, tmp_path):
    extra = kits / "another-kit"
    extra.mkdir()
    (extra / "spec.yaml").write_text("name: another-kit\n", encoding="utf-8")
    patterns = tmp_path / "patterns"
    (patterns / "schemas").mkdir(parents=True)
    (patterns / "schemas/kit-hybrid-v1.schema.json").write_text("{}", encoding="utf-8")
    work = tmp_path / "stage"
    validator.stage_kits(kits, patterns, work)
    staged = work / "integrations/isolation/acq-kits"
    registry = yaml.safe_load((staged / "kits.yaml").read_text())
    assert set(registry["kits"]) == {*runner.KIT_NAMES, "another-kit"}
    assert (staged / "claude-code/files/.hidden/payload").read_text() == "payload"


def test_missing_required_kit_fails(kits):
    (kits / "claude-code/spec.yaml").unlink()
    with pytest.raises(ValueError, match="claude-code"):
        validator.discover_kits(kits)


def test_broken_local_doc_link_fails(kits):
    kit = kits / "claude-code"
    (kit / "README.md").write_text("[Missing](missing.md)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken local link"):
        validator.validate_local_docs_and_modes(kit)


def test_provider_normalizer_requires_executable_mode(kits):
    kit = kits / "opencode-go-provider"
    (kit / "provider-input.json").write_text('{"normalizerPath":"normalizer"}', encoding="utf-8")
    normalizer = kit / "normalizer"
    normalizer.write_text("test", encoding="utf-8")
    normalizer.chmod(0o644)
    with pytest.raises(ValueError, match="executable on disk"):
        validator.validate_local_docs_and_modes(kit)
    normalizer.chmod(0o755)
    validator.validate_local_docs_and_modes(kit)


def test_spec_name_mismatch_fails(kits, tmp_path):
    (kits / "claude-code/spec.yaml").write_text("name: wrong\n", encoding="utf-8")
    patterns = tmp_path / "patterns"
    (patterns / "schemas").mkdir(parents=True)
    (patterns / "schemas/kit-hybrid-v1.schema.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="spec name"):
        validator.stage_kits(kits, patterns, tmp_path / "stage")


@pytest.mark.parametrize("name", runner.KIT_NAMES)
def test_dispatch_commands(kits, name):
    cwd, commands = runner.test_commands(kits, name, install=True)
    assert cwd == kits / name
    if name in ("opencode-go-provider", "pi-coding-agent"):
        assert commands[:2] == [["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], ["npm", "test"]]
    elif name == "claude-code":
        assert commands == [[sys.executable, "scripts/test"]]
    else:
        assert commands == [["bash", "scripts/verify"]]


def test_ci_matrix_and_dispatch_cover_every_repository_kit():
    actual = {kit.name for kit in validator.discover_kits(ROOT)}
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["kits"]["strategy"]["matrix"]
    assert set(matrix["kit"]) == set(runner.KIT_NAMES) == actual
    assert actual == validator.REQUIRED_KITS
    assert {"kit": "claude-code", "python": "3.12"} in matrix["include"]


@pytest.mark.parametrize("name", ["../claude-code", "/outside-project", "unknown", "claude-code;echo bad"])
def test_rejects_unrecognized_kit(kits, name):
    with pytest.raises(ValueError, match="unknown kit"):
        runner.test_commands(kits, name)


def test_rejects_symlinked_kit(kits, tmp_path):
    target = tmp_path / "linked"
    (kits / "claude-code").rename(target)
    (kits / "claude-code").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="actual root directory"):
        runner.test_commands(kits, "claude-code")


def test_live_checks_disabled_and_failure_propagates(kits, monkeypatch):
    monkeypatch.setenv("RUN_ACQ", "1")
    monkeypatch.setenv("RUN_CLAUDE_LIVE", "1")
    calls = []
    monkeypatch.setattr(runner.shutil, "which", lambda name: f"/usr/bin/{name}")

    def failed(command, **kwargs):
        calls.append(kwargs)
        raise subprocess.CalledProcessError(7, command)

    monkeypatch.setattr(runner.subprocess, "run", failed)
    assert runner.main(["pi-coding-agent", "--root", str(kits)]) == 1
    assert calls[0]["env"]["RUN_ACQ"] == "0"
    assert calls[0]["env"]["RUN_LIVE"] == "0"
    assert calls[0]["env"]["RUN_CLAUDE_LIVE"] == "0"
    assert calls[0]["check"] is True


def test_claude_test_bootstrap_uses_requested_python_and_locked_tools(monkeypatch):
    monkeypatch.delenv("RUN_CLAUDE_LIVE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    commands = []
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: commands.append(command) or subprocess.CompletedProcess(command, 0)
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(ROOT / "claude-code/scripts/test"), run_name="__main__")
    assert result.value.code == 0
    assert commands[0][commands[0].index("--python") + 1] == sys.executable
    assert all("--require-hashes" in command for command in commands[1:3])
    assert commands[2][-1].endswith("tests/requirements.lock")


def test_missing_patterns_fails_without_fetch(kits, capsys):
    assert validator.main(["--root", str(kits)]) == 1
    assert "kit validation failed" in capsys.readouterr().err


def test_wrong_patterns_pin_fails(kits, monkeypatch):
    monkeypatch.setattr(
        validator.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "wrong\n")
    )
    with pytest.raises(ValueError, match="must be pinned"):
        validator.validate(kits, kits / ".patterns")


@pytest.mark.parametrize("missing", ["validator", "schema", "provider"])
def test_missing_upstream_inputs_fail(kits, tmp_path, monkeypatch, missing):
    monkeypatch.setattr(validator, "validate_git_executable_modes", lambda root: None)
    patterns = tmp_path / "patterns"
    paths = {
        "validator": "integrations/isolation/acq-kits/validate-kits.py",
        "schema": "schemas/kit-hybrid-v1.schema.json",
        "provider": "scripts/validate_provider_input_contract.py",
        "bindings": "integrations/isolation/schemas/provider-credential-bindings.json",
    }
    for key, path in paths.items():
        if key != missing:
            target = patterns / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{"providers": {}}', encoding="utf-8")
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, validator.PATTERNS_REF + "\n"),
    )
    with pytest.raises(ValueError, match="required validation input missing"):
        validator.validate(kits, patterns)


def test_provider_binding_patch_is_local_and_upstream_validation_is_strict(kits, tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "validate_git_executable_modes", lambda root: None)
    patterns = tmp_path / "patterns"
    inputs = [
        "integrations/isolation/acq-kits/validate-kits.py",
        "scripts/validate_provider_input_contract.py",
        "schemas/kit-hybrid-v1.schema.json",
    ]
    for path in inputs:
        target = patterns / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    binding = patterns / "integrations/isolation/schemas/provider-credential-bindings.json"
    binding.parent.mkdir(parents=True)
    binding.write_text('{"providers": {"usai": "USAI_API_KEY"}}', encoding="utf-8")
    (kits / "opencode-go-provider/provider-input.json").write_text('{"normalizerPath":"normalizer"}', encoding="utf-8")
    normalizer = kits / "opencode-go-provider/normalizer"
    normalizer.write_text("test", encoding="utf-8")
    normalizer.chmod(0o755)
    calls = []

    def capture(command, **kwargs):
        calls.append(command)
        if "--credential-bindings" in command:
            patched = Path(command[command.index("--credential-bindings") + 1])
            assert json.loads(patched.read_text())["providers"] == {
                "usai": "USAI_API_KEY",
                "opencode-go": "OPENCODE_GO_API_KEY",
            }
        return subprocess.CompletedProcess(command, 0, validator.PATTERNS_REF + "\n")

    monkeypatch.setattr(validator.subprocess, "run", capture)
    validator.validate(kits, patterns)
    assert "--strict" in calls[1]
    assert calls[2][-2:] == ["--bundle", str(kits / "opencode-go-provider/provider-input.json")]
    assert json.loads(binding.read_text()) == {"providers": {"usai": "USAI_API_KEY"}}


@pytest.mark.parametrize("index_mode, disk_mode, passes", [("100644", 0o755, False), ("100755", 0o644, True)])
def test_git_mode_check_is_independent_of_shared_mount(kits, monkeypatch, index_mode, disk_mode, passes):
    target = kits / "claude-code/files/.hidden/payload"
    target.chmod(disk_mode)
    (kits / "claude-code/spec.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "claude-code",
                "files": [{"source": "files/.hidden/payload", "mode": "0755"}],
            }
        )
    )
    entries = [
        ("100755", "scripts/validate-kits.py"),
        ("100755", "scripts/run-kit-tests.py"),
        (index_mode, "claude-code/files/.hidden/payload"),
    ]
    output = "".join(f"{mode} {'a' * 40} 0\t{name}\0" for mode, name in entries)
    monkeypatch.setattr(validator.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, output))
    if passes:
        validator.validate_git_executable_modes(kits)
    else:
        with pytest.raises(ValueError, match="Git index must record"):
            validator.validate_git_executable_modes(kits)


def test_git_mode_check_rejects_untracked_or_unmerged_scripts(kits, monkeypatch):
    for output in ("", f"100755 {'a' * 40} 2\tscripts/validate-kits.py\0"):
        monkeypatch.setattr(
            validator.subprocess, "run", lambda *a, output=output, **kw: subprocess.CompletedProcess(a, 0, output)
        )
        with pytest.raises(ValueError, match="stage 0"):
            validator.validate_git_executable_modes(kits)
