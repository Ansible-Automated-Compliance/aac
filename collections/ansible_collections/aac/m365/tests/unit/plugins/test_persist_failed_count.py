"""Regression test for the persist.yml failed-control derivation.

The original pipeline was
    map('regex_search', 'CIS (...)', '\\1') | select('string')
which silently produced ZERO failed controls for every section: Ansible's
regex_search returns a LIST of captured groups when group references are
passed, and select('string') discards lists. Result: rows stored
failed=0 / 100% while the violations column held the full finding list —
a report that says clean while listing dozens of violations.

This pins the fixed pipeline's semantics at the filter level:
    map(regex_search, pattern, '\\1') | select() | map(first) | unique
"""
import pathlib
import sys

# The repo root's ansible/ playbook tree shadows the ansible PACKAGE as a
# namespace package when pytest inserts the rootdir on sys.path. Drop any
# such entry and any already-imported namespace stub before importing.
sys.path[:] = [
    p for p in sys.path
    if not (pathlib.Path(p or ".") / "ansible" / "playbooks").is_dir()
]
if "ansible" in sys.modules and getattr(sys.modules["ansible"], "__file__", None) is None:
    del sys.modules["ansible"]

import pytest

try:
    from ansible.plugins.filter.core import regex_search
except ImportError:  # missing OR locally broken ansible install
    pytest.skip("ansible filter plugins unavailable", allow_module_level=True)

PATTERN = r"CIS ([0-9]+(?:\.[0-9]+)*)"

VIOLATIONS = [
    "CIS 1.1.1: administrative accounts were not collected",
    "CIS 2.1.4: no Safe Attachments policy is enabled",
    "CIS 2.1.4: duplicate control, second entity",
    "some message with no control id",
]


def _pipeline(messages):
    matched = [regex_search(m, PATTERN, "\\1") for m in messages]
    truthy = [m for m in matched if m]          # select()
    firsts = [m[0] for m in truthy]             # map('first')
    return sorted(set(firsts))                  # unique


def test_regex_search_with_group_arg_returns_list_not_string():
    """The trap the original code fell into: this is a list."""
    result = regex_search(VIOLATIONS[0], PATTERN, "\\1")
    assert isinstance(result, list)
    assert result == ["1.1.1"]


def test_fixed_pipeline_counts_unique_failed_controls():
    ids = _pipeline(VIOLATIONS)
    assert ids == ["1.1.1", "2.1.4"]
    assert len(ids) == 2  # per-entity duplicates collapse to control count


def test_original_pipeline_was_always_zero():
    """Documents the defect: select('string') dropped every match."""
    matched = [regex_search(m, PATTERN, "\\1") for m in VIOLATIONS]
    strings = [m for m in matched if isinstance(m, str)]
    assert strings == []


def test_no_matches_yields_zero_not_error():
    assert _pipeline(["no ids here", "still none"]) == []
