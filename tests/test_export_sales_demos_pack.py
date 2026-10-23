"""Tests for scripts/export_sales_demos_pack.py — the sales.demos pack exporter.

Pins the two guarantees the sync relies on: the forbidden sweep is fail-closed
over every exported file and over the generated metadata (unknown file types,
allowed binaries, MANIFEST.yml, README.md), and two exports of the same source
commit are byte-identical so the sync's no-change check can stop.
"""
import hashlib
import importlib.util
import os
import pathlib
import subprocess

import pytest
import yaml

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("export_pack", _root / "scripts" / "export_sales_demos_pack.py")
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)

FORBIDDEN = [r"192\.168\.", r"(?i)\bnetflix\b"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_repo(tmp_path, branch="main", git=True):
    """A tiny compliance-shaped checkout committed on ``branch`` (or, with
    ``git=False``, a plain directory like an AAP project checkout)."""
    repo = tmp_path / "repo"
    (repo / "ansible" / "playbooks").mkdir(parents=True)
    (repo / "ansible" / "files").mkdir()
    (repo / "ansible" / "vars").mkdir()
    (repo / "ansible" / "ao").mkdir()
    (repo / "ansible" / "playbooks" / "demo.yml").write_text(
        "- hosts: localhost\n  tasks:\n    - name: schema\n      script: ../files/schema.sql\n"
    )
    (repo / "ansible" / "files" / "schema.sql").write_text("CREATE TABLE t (id int);\n")
    (repo / "ansible" / "vars" / "empty_fallback.yml").write_text("---\n")
    (repo / "ansible" / "ao" / "sales_demos_pack.yml").write_text(yaml.safe_dump({
        "pack_version": 1,
        "playbooks": ["ansible/playbooks/demo.yml"],
        "vars": ["ansible/vars/empty_fallback.yml"],
        "trees": [{"src": "ansible/tree", "dest": "tree"}],
        "forbidden_patterns": FORBIDDEN,
    }))
    (repo / "ansible" / "tree").mkdir()
    (repo / "ansible" / "tree" / "ok.md").write_text("# fine\n")
    if git:
        _git(repo, "init", "-q", "-b", branch)
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return repo


def _tree_digest(out):
    digest = {}
    for root, _, names in os.walk(out):
        for n in names:
            p = pathlib.Path(root) / n
            digest[str(p.relative_to(out))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return digest


def _set_manifest(repo, **extra):
    path = repo / "ansible" / "ao" / "sales_demos_pack.yml"
    m = yaml.safe_load(path.read_text())
    m.update(extra)
    path.write_text(yaml.safe_dump(m))


def test_clean_export_succeeds_and_is_deterministic(tmp_path):
    repo = _make_repo(tmp_path)
    out1, out2 = tmp_path / "out1", tmp_path / "out2"
    assert ex.main(["--repo", str(repo), "--out", str(out1)]) == 0
    assert ex.main(["--repo", str(repo), "--out", str(out2)]) == 0
    assert _tree_digest(out1) == _tree_digest(out2)
    manifest = yaml.safe_load((out1 / "MANIFEST.yml").read_text())
    assert "generated_at" not in manifest
    assert manifest["source"]["committed_at"]          # deterministic per commit
    assert "forbidden_pattern_violations" not in manifest
    # the ../files reference was followed and the layout preserved
    assert (out1 / "files" / "schema.sql").is_file()
    assert set(manifest["files"]) >= {"playbooks/demo.yml", "files/schema.sql", "vars/empty_fallback.yml", "tree/ok.md"}


def test_forbidden_text_is_refused(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "ansible" / "tree" / "notes.md").write_text("gateway 192.168.100.1\n")
    assert ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")]) == 2


def test_unsupported_file_type_fails_closed(tmp_path, capsys):
    repo = _make_repo(tmp_path)
    (repo / "ansible" / "tree" / "legacy.ini").write_text("[db]\nhost = 192.168.100.26\n")
    assert ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert "tree/legacy.ini" in err and "unsupported file type" in err


def test_extensionless_file_fails_closed(tmp_path, capsys):
    repo = _make_repo(tmp_path)
    (repo / "ansible" / "tree" / "LICENSE").write_text("clean text, unknown type\n")
    assert ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")]) == 2
    assert "tree/LICENSE" in capsys.readouterr().err


def test_allowed_binary_is_scanned(tmp_path, capsys):
    repo = _make_repo(tmp_path)
    (repo / "ansible" / "tree" / "blob.bin").write_bytes(b"\x00\x01token for netflix demo\x00")
    _set_manifest(repo, allowed_binary=["tree/blob.bin"])
    assert ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")]) == 2
    assert "tree/blob.bin" in capsys.readouterr().err


def test_allowed_clean_binary_ships(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "ansible" / "tree" / "blob.bin").write_bytes(b"\x00\x01\x02clean\x00")
    _set_manifest(repo, allowed_binary=["tree/blob.bin"])
    out = tmp_path / "out"
    assert ex.main(["--repo", str(repo), "--out", str(out)]) == 0
    assert (out / "tree" / "blob.bin").read_bytes() == b"\x00\x01\x02clean\x00"


def test_generated_metadata_is_scanned(tmp_path, capsys):
    # A private branch name lands in MANIFEST.yml via the provenance block;
    # the sweep must catch it there like anywhere else.
    repo = _make_repo(tmp_path, branch="feature/netflix")
    assert ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert "MANIFEST.yml" in err and "netflix" in err


def test_missing_source_is_reported_not_fatal(tmp_path, capsys):
    repo = _make_repo(tmp_path)
    _set_manifest(repo, files=["ansible/files/does_not_exist.sql"])
    out = tmp_path / "out"
    assert ex.main(["--repo", str(repo), "--out", str(out)]) == 0
    manifest = yaml.safe_load((out / "MANIFEST.yml").read_text())
    assert manifest["missing"] == ["ansible/files/does_not_exist.sql"]
    assert "MISSING" in capsys.readouterr().out


def test_source_commit_override_when_not_a_checkout(tmp_path):
    """An AAP project directory has no .git: provenance comes from the arguments."""
    repo = _make_repo(tmp_path, git=False)
    out = tmp_path / "out"
    rc = ex.main(["--repo", str(repo), "--out", str(out),
                      "--source-commit", "abc123def4567890", "--source-committed-at",
                      "2026-10-08T21:00:00Z", "--source-branch", "main"])
    assert rc == 0
    manifest = yaml.safe_load((out / "MANIFEST.yml").read_text())
    assert manifest["source"] == {"repository": "ansible-automated-compliance/aac", "commit": "abc123def4567890",
                                  "committed_at": "2026-10-08T21:00:00Z", "branch": "main"}
    assert "`abc123def456`" in (out / "README.md").read_text()


def test_no_source_commit_at_all_is_refused(tmp_path, capsys):
    repo = _make_repo(tmp_path, git=False)
    rc = ex.main(["--repo", str(repo), "--out", str(tmp_path / "out")])
    assert rc == 3
    assert "source commit unknown" in capsys.readouterr().err
