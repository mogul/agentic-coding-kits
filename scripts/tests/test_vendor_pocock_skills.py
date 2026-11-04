"""Tests for personal/scripts/vendor-pocock-skills using a synthetic upstream archive."""

import importlib.machinery
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def load():
    path = str(ROOT / "personal/scripts/vendor-pocock-skills")
    loader = importlib.machinery.SourceFileLoader("vendor_pocock_skills", path)
    spec = importlib.util.spec_from_loader("vendor_pocock_skills", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


vendor = load()


THIRD_PARTY_TEXT = "MIT License\n\nCopyright (c) 2026 HumanLayer\n"


def manifest(names=None, version="9.9.9"):
    names = sorted(vendor.SKILLS if names is None else names)
    return json.dumps({"version": version, "skills": [f"./skills/engineering/{name}" for name in names]})


def upstream_files():
    files = {"LICENSE": "MIT License\n", ".claude-plugin/plugin.json": manifest()}
    for name, directory in vendor.SKILLS.items():
        body = f"---\nname: {name}\n---\nbody\n"
        files[f"{directory}/SKILL.md"] = body
    files["skills/engineering/code-review/SKILL.md"] = "---\nname: code-review\n---\nbody\n"
    files["skills/engineering/code-review/agents/openai.yaml"] = 'display_name: "Code Review"\n'
    files["skills/engineering/ask-matt/SKILL.md"] = (
        "a `/code-review` b `/code-review` c `/code-review` d `/code-review`\n"
    )
    files["skills/engineering/implement/SKILL.md"] = 'Call the Skill tool with "code-review".\n'
    files["skills/engineering/implement-spec/SKILL.md"] = "Call the Skill tool with `code-review`.\n"
    files["skills/engineering/tdd/SKILL.md"] = "see the `code-review` skill\n"
    files["skills/engineering/not-shipped/SKILL.md"] = "ignored\n"
    return files


def archive(files, extra=None):
    buffer = io.BytesIO()
    root = f"skills-{SHA}"
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        top = tarfile.TarInfo(root)
        top.type = tarfile.DIRTYPE
        tar.addfile(top)
        for path, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"{root}/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if extra:
            extra(tar, root)
    return buffer.getvalue()


@pytest.fixture
def kit(tmp_path, monkeypatch):
    (tmp_path / "spec.yaml").write_text(f"files:\n  - path: /home/agent/x\n{vendor.BEGIN_MARK}\n{vendor.END_MARK}\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / vendor.DOC_PATH).write_text(f"# doc\n{vendor.DOC_BEGIN}\n{vendor.DOC_END}\ntail\n")
    licence = tmp_path / "files/home/.agents/licenses/humanlayer-skills-LICENSE"
    licence.parent.mkdir(parents=True)
    licence.write_text(THIRD_PARTY_TEXT)
    pinned = [dict(vendor.THIRD_PARTY[0], licenseSha256=vendor.hashlib.sha256(THIRD_PARTY_TEXT.encode()).hexdigest())]
    monkeypatch.setattr(vendor, "THIRD_PARTY", pinned)
    return tmp_path


def run(kit, data, *flags):
    tarball = kit / "in.tgz"
    tarball.write_bytes(data)
    return vendor.main(["--kit", str(kit), "--sha", SHA, "--tarball", str(tarball), *flags])


def test_vendors_renames_and_is_idempotent(kit):
    assert run(kit, archive(upstream_files())) == 0
    skills = kit / vendor.SKILLS_DIR
    assert not (skills / "code-review").exists()
    assert (skills / "pocock-code-review/SKILL.md").read_text().startswith("---\nname: pocock-code-review")
    assert "pocock-code-review" in (skills / "implement/SKILL.md").read_text()
    assert not (skills / "not-shipped").exists()
    assert 'display_name: "Pocock Code Review"' in (skills / "pocock-code-review/agents/openai.yaml").read_text()
    lock = json.loads((kit / vendor.LOCK_PATH).read_text())
    assert lock["ref"] == SHA
    assert (kit / vendor.LICENSE_PATH).read_text() == "MIT License\n"
    assert lock["upstreamVersion"] == "9.9.9"
    assert lock["attribution"]["author"] == "Matt Pocock"
    assert lock["thirdParty"][0]["author"] == "Dex Horthy"
    assert any(c["file"] == "implement/SKILL.md" for c in lock["localChanges"])
    doc = (kit / vendor.DOC_PATH).read_text()
    assert "| `implement/SKILL.md` | 1 reference to code-review rewritten to pocock-code-review |" in doc
    assert "Dex Horthy (HumanLayer)" in doc
    assert "| `pocock-code-review/agents/openai.yaml` | display_name:" in doc
    assert "| `pocock-code-review/` |" in doc
    assert doc.startswith("# doc\n") and doc.endswith("tail\n")
    assert doc.count(vendor.DOC_BEGIN) == 1 and doc.count(vendor.DOC_END) == 1
    spec = (kit / "spec.yaml").read_text()
    assert "source: files/home/.agents/skills/tdd/SKILL.md" in spec
    assert "path: /home/agent/x" in spec
    assert run(kit, archive(upstream_files()), "--check") == 0


def test_check_reports_drift_and_stale_files(kit, capsys):
    assert run(kit, archive(upstream_files())) == 0
    (kit / vendor.SKILLS_DIR / "tdd/SKILL.md").write_text("edited\n")
    assert run(kit, archive(upstream_files()), "--check") == 1
    assert "differs: files/home/.agents/skills/tdd/SKILL.md" in capsys.readouterr().err
    assert run(kit, archive(upstream_files())) == 0
    assert (kit / vendor.SKILLS_DIR / "tdd/SKILL.md").read_text() != "edited\n"
    assert run(kit, archive(upstream_files()), "--check") == 0


def test_rewrite_removes_files_upstream_dropped(kit):
    files = upstream_files()
    files["skills/engineering/tdd/extra.md"] = "extra\n"
    assert run(kit, archive(files)) == 0
    assert (kit / vendor.SKILLS_DIR / "tdd/extra.md").exists()
    del files["skills/engineering/tdd/extra.md"]
    assert run(kit, archive(files)) == 0
    assert not (kit / vendor.SKILLS_DIR / "tdd/extra.md").exists()


def test_unexpected_rename_count_fails_closed(kit, capsys):
    files = upstream_files()
    files["skills/engineering/tdd/SKILL.md"] += "and another `code-review` mention\n"
    assert run(kit, archive(files)) == 1
    assert "tdd/SKILL.md: expected 1 references" in capsys.readouterr().err
    assert not (kit / vendor.SKILLS_DIR).exists()


@pytest.mark.parametrize("sha", ["main", "ABC", "a" * 39, "g" * 40])
def test_requires_a_full_commit_sha(kit, sha, capsys):
    assert vendor.main(["--kit", str(kit), "--sha", sha, "--tarball", str(kit / "x")]) == 1
    assert "40-character" in capsys.readouterr().err


def test_refuses_links_and_binary_files(kit, capsys):
    def add_link(tar, root):
        info = tarfile.TarInfo(f"{root}/skills/engineering/tdd/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    assert run(kit, archive(upstream_files(), add_link)) == 1
    assert "not a regular file" in capsys.readouterr().err

    def add_binary(tar, root):
        info = tarfile.TarInfo(f"{root}/skills/engineering/tdd/blob")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"\xff\xfe"))

    assert run(kit, archive(upstream_files(), add_binary)) == 1
    assert "not UTF-8" in capsys.readouterr().err


def test_missing_markers_and_missing_skill_fail(kit, capsys):
    (kit / "spec.yaml").write_text("files: []\n")
    assert run(kit, archive(upstream_files())) == 1
    assert "markers not found" in capsys.readouterr().err
    (kit / "spec.yaml").write_text(f"{vendor.BEGIN_MARK}\n{vendor.END_MARK}\n")
    files = upstream_files()
    del files["skills/engineering/wizard/SKILL.md"]
    assert run(kit, archive(files)) == 1
    assert "wizard: SKILL.md missing" in capsys.readouterr().err


def test_tampered_lock_cannot_delete_outside_the_kit(kit, tmp_path):
    assert run(kit, archive(upstream_files())) == 0
    outside = tmp_path.parent / "victim.txt"
    outside.write_text("keep me\n")
    absolute = tmp_path.parent / "abs_victim.txt"
    absolute.write_text("keep me\n")
    lock = json.loads((kit / vendor.LOCK_PATH).read_text())
    lock["files"]["../victim.txt"] = "0"
    lock["files"][str(absolute)] = "0"
    traversal = tmp_path / "files" / ".." / ".." / "victim2.txt"
    traversal.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path.parent / "victim2.txt").write_text("keep me\n")
    lock["files"]["files/../../victim2.txt"] = "0"
    lock["files"]["not-under-files/x"] = "0"
    (kit / vendor.LOCK_PATH).write_text(json.dumps(lock))
    assert vendor.previous_files(kit) <= {p for p in lock["files"] if p.startswith("files/") and ".." not in p}
    assert run(kit, archive(upstream_files())) == 0
    assert outside.read_text() == "keep me\n"
    assert absolute.read_text() == "keep me\n"
    assert (tmp_path.parent / "victim2.txt").read_text() == "keep me\n"


@pytest.mark.parametrize(
    "name",
    [
        'evil\n  - path: /home/agent/.bashrc\n    mode: "0755"\n    source: files/x',
        "q'uo\"te#.md",
        "sp ace.md",
        "dollar$.md",
    ],
)
def test_unsafe_member_names_are_refused_before_anything_is_written(kit, name, capsys):
    files = upstream_files()
    files[f"skills/engineering/tdd/{name}"] = "x\n"
    assert run(kit, archive(files)) == 1
    assert "unsafe file name" in capsys.readouterr().err
    assert not (kit / vendor.SKILLS_DIR).exists()
    assert "/home/agent/.bashrc" not in (kit / "spec.yaml").read_text()


def test_total_size_cap(kit, monkeypatch, capsys):
    monkeypatch.setattr(vendor, "MAX_TOTAL_BYTES", 100)
    assert run(kit, archive(upstream_files())) == 1
    assert "exceed" in capsys.readouterr().err


def test_crlf_in_an_upstream_file_round_trips(kit):
    files = upstream_files()
    files["skills/engineering/tdd/SKILL.md"] = "---\r\nname: tdd\r\n---\r\nsee `code-review`\r\n"
    assert run(kit, archive(files)) == 0
    shipped = (kit / vendor.SKILLS_DIR / "tdd/SKILL.md").read_bytes()
    assert shipped == b"---\r\nname: tdd\r\n---\r\nsee `pocock-code-review`\r\n"
    assert run(kit, archive(files), "--check") == 0


def test_write_refuses_to_follow_a_symlink_out_of_the_kit(kit, tmp_path):
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir()
    home = kit / "files/home"
    for child in list(home.rglob("*"))[::-1]:
        child.unlink() if child.is_file() else child.rmdir()
    home.rmdir()
    home.symlink_to(outside, target_is_directory=True)
    third_party = outside / ".agents/licenses"
    third_party.mkdir(parents=True)
    (third_party / "humanlayer-skills-LICENSE").write_text(THIRD_PARTY_TEXT)
    before = sorted(str(p) for p in outside.rglob("*"))
    assert run(kit, archive(upstream_files())) == 1
    assert sorted(str(p) for p in outside.rglob("*")) == before


@pytest.mark.parametrize("document", ["[]", "null", '{"files": 5}', '{"files": [1, 2]}'])
def test_malformed_lock_fails_closed(kit, document, capsys):
    (kit / "vendor").mkdir()
    (kit / vendor.LOCK_PATH).write_text(document)
    assert run(kit, archive(upstream_files())) == 1
    assert "expected an object" in capsys.readouterr().err
    assert not (kit / vendor.SKILLS_DIR).exists()


def test_a_changed_promoted_set_stops_the_run(kit, capsys):
    names = set(vendor.SKILLS) - {"wizard"} | {"brand-new-skill"}
    files = upstream_files()
    files[".claude-plugin/plugin.json"] = manifest(names)
    assert run(kit, archive(files)) == 1
    err = capsys.readouterr().err
    assert "promoted skills changed" in err and "brand-new-skill" in err and "wizard" in err
    assert not (kit / vendor.SKILLS_DIR).exists()


def test_missing_plugin_manifest_stops_the_run(kit, capsys):
    files = upstream_files()
    del files[".claude-plugin/plugin.json"]
    assert run(kit, archive(files)) == 1
    assert "plugin.json not found" in capsys.readouterr().err


def test_third_party_licence_must_match_its_pin(kit, capsys):
    (kit / "files/home/.agents/licenses/humanlayer-skills-LICENSE").write_text("tampered\n")
    assert run(kit, archive(upstream_files())) == 1
    assert "does not match the pinned sha256" in capsys.readouterr().err
    (kit / "files/home/.agents/licenses/humanlayer-skills-LICENSE").unlink()
    assert run(kit, archive(upstream_files())) == 1
    assert "missing third-party licence" in capsys.readouterr().err


def test_doc_markers_are_required(kit, capsys):
    (kit / vendor.DOC_PATH).write_text("# no markers\n")
    assert run(kit, archive(upstream_files())) == 1
    assert "generated block markers not found" in capsys.readouterr().err


def test_pinned_third_party_hash_matches_the_committed_licence():
    module = load()
    for item in module.THIRD_PARTY:
        licence = (ROOT / "personal" / item["licenseFile"]).read_bytes()
        assert module.hashlib.sha256(licence).hexdigest() == item["licenseSha256"]


@pytest.mark.parametrize(
    "version",
    ["1.0.0\n<!-- END generated:local-differences -->\n# pwned", "`x`", "a b", "x" * 41, "", 7, None],
)
def test_untrusted_version_text_cannot_reach_the_doc_or_lock(kit, version):
    files = upstream_files()
    files[".claude-plugin/plugin.json"] = json.dumps(
        {"version": version, "skills": [f"./skills/engineering/{n}" for n in vendor.SKILLS]}
    )
    assert run(kit, archive(files)) == 0
    assert json.loads((kit / vendor.LOCK_PATH).read_text())["upstreamVersion"] == "unknown"
    doc = (kit / vendor.DOC_PATH).read_text()
    assert "pwned" not in doc and doc.count(vendor.DOC_END) == 1


@pytest.mark.parametrize("document", ["[1]", "[1, 2]", "7", '"x"', "null"])
def test_plugin_manifest_must_be_an_object(kit, document, capsys):
    files = upstream_files()
    files[".claude-plugin/plugin.json"] = document
    assert run(kit, archive(files)) == 1
    assert "expected a JSON object" in capsys.readouterr().err
    assert not (kit / vendor.SKILLS_DIR).exists()


def test_committed_files_carry_the_markers_the_script_looks_for():
    module = load()
    doc = (ROOT / "personal" / module.DOC_PATH).read_text(encoding="utf-8")
    spec = (ROOT / "personal/spec.yaml").read_text(encoding="utf-8")
    assert doc.count(module.DOC_BEGIN) == 1 and doc.count(module.DOC_END) == 1
    assert spec.count(module.BEGIN_MARK) == 1 and spec.count(module.END_MARK) == 1
