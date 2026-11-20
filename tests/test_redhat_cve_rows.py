"""The Red Hat Security Data API puller (fetch_redhat_cve_data.yml).

tests/fixtures/redhat_cve_CVE-2026-98432.json is the response of
https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-98432.json
recorded on 2026-11-19, unmodified. The parser is tested against it; the
playbook is checked for what it is allowed to send.
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import yaml

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAYBOOKS = os.path.join(_REPO, "ansible", "playbooks")
_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "redhat_cve_CVE-2026-98432.json")

sys.path.insert(0, os.path.join(_PLAYBOOKS, "filter_plugins"))
import aac_redhat_cve as plugin  # noqa: E402


@pytest.fixture(scope="module")
def doc() -> dict:
    with open(_FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def parsed(doc) -> dict:
    return plugin.redhat_cve_rows(doc)


def _builds(parsed, **want):
    return [r for r in parsed["fixed_builds"] if all(r[k] == v for k, v in want.items())]


def test_event_row(parsed):
    event = parsed["event"]
    assert event["cve_id"] == "CVE-2026-98432"
    assert event["source"] == "redhat_security_data_api"
    assert event["vendor"] == "redhat" and event["product"] == "kernel"
    assert event["severity"] == "CRITICAL" and event["cvss_v3"] == 9.8
    assert event["published_at"] == "2026-10-15T00:00:00Z"
    assert "https://www.cve.org/CVERecord?id=CVE-2026-98432" in event["references"]
    assert all("\n" not in ref for ref in event["references"])


@pytest.mark.parametrize("product, evr, stream, tag, advisory", [
    ("Red Hat Enterprise Linux 9", "5.14.0-687.64.1.el9_8", "el9", "el9_8", "RHSA-2026:93412"),
    ("Red Hat Enterprise Linux 8", "4.18.0-553.182.1.el8_10", "el8", "el8_10", "RHSA-2026:93414"),
    ("Red Hat Enterprise Linux 10", "6.12.0-211.72.1.el10_2", "el10", "el10_2", "RHSA-2026:93413"),
    ("Red Hat Enterprise Linux 9.4 Update Services for SAP Solutions", "5.14.0-427.161.1.el9_4", "el9", "el9_4",
     "RHSA-2026:94109"),
])
def test_fixed_build_per_stream(parsed, product, evr, stream, tag, advisory):
    rows = _builds(parsed, package_name="kernel", product_name=product, fixed_evr=evr)
    assert len(rows) == 1
    row = rows[0]
    assert (row["stream"], row["dist_tag"], row["advisory_id"], row["fix_state"], row["base_os"]) \
        == (stream, tag, advisory, "fixed", True)


def test_zero_epoch_is_dropped_and_a_real_epoch_is_kept():
    assert plugin.parse_nevr("kernel-0:5.14.0-687.64.1.el9_8") == ("kernel", "5.14.0-687.64.1.el9_8")
    assert plugin.parse_nevr("skopeo-2:1.11.3-10.rhaos4.15.el8") == ("skopeo", "2:1.11.3-10.rhaos4.15.el8")
    assert plugin.parse_nevr("kernel-rt-0:4.18.0-553.182.1.rt7.523.el8_10") \
        == ("kernel-rt", "4.18.0-553.182.1.rt7.523.el8_10")


def test_entries_without_a_package_build_are_listed_not_recorded(parsed):
    assert plugin.parse_nevr("kpatch-patch") is None
    # an image reference looks like name-<digits>:<tag>; it is not an rpm
    assert plugin.parse_nevr("openshift/ose-rhel-coreos-9:413.92.202611041925-0") is None
    reasons = {s["reason"] for s in parsed["skipped"]}
    assert reasons == {"container image reference", "no version in the package field"}
    assert not [r for r in parsed["fixed_builds"] if "/" in r["package_name"]]
    assert not _builds(parsed, package_name="kpatch-patch")


def test_layered_products_are_marked_not_base_os(parsed):
    nvidia = _builds(parsed, product_name="NVIDIA for RHEL 10")
    assert len(nvidia) == 1 and nvidia[0]["base_os"] is False
    assert all(not r["base_os"] for r in parsed["fixed_builds"] if "OpenShift" in r["product_name"])
    assert all(r["base_os"] for r in parsed["fixed_builds"]
               if r["product_name"].startswith("Red Hat Enterprise Linux") and "AI" not in r["product_name"])


def test_package_state_rows(parsed):
    el7 = _builds(parsed, product_name="Red Hat Enterprise Linux 7", package_name="kernel")
    assert len(el7) == 1
    assert (el7[0]["fix_state"], el7[0]["fixed_evr"], el7[0]["stream"], el7[0]["base_os"]) \
        == ("not_affected", None, "el7", True)
    rhel_ai = _builds(parsed, product_name="Red Hat Enterprise Linux AI (RHEL AI) 3")
    assert (rhel_ai[0]["fix_state"], rhel_ai[0]["base_os"], rhel_ai[0]["stream"]) == ("affected", False, None)


def test_rows_are_unique_on_the_table_key(parsed):
    keys = [(r["product_name"], r["package_name"], r["fixed_evr"] or "") for r in parsed["fixed_builds"]]
    assert len(keys) == len(set(keys))


def test_every_affected_release_and_state_is_accounted_for(doc, parsed):
    distinct = {(r["product_name"], r.get("package", "")) for r in doc["affected_release"]} \
        | {(s["product_name"], s["package_name"]) for s in doc["package_state"]}
    skipped = {(s["product_name"], s["package"]) for s in parsed["skipped"]}
    assert len(parsed["fixed_builds"]) + len(skipped) == len(distinct)


def test_documented_shape_without_optional_fields():
    parsed = plugin.redhat_cve_rows({
        "name": "CVE-2025-00001", "threat_severity": "Moderate",
        "affected_release": [{"product_name": "Red Hat Enterprise Linux 9", "advisory": "RHSA-2025:0001",
                              "cpe": "cpe:/a:redhat:enterprise_linux:9::appstream",
                              "package": "example-pkg-1:2.0-3.el9_6"}],
    })
    assert parsed["event"]["severity"] == "MEDIUM" and parsed["event"]["cvss_v3"] is None
    assert parsed["event"]["product"] == "example-pkg"
    assert parsed["fixed_builds"][0]["fixed_evr"] == "1:2.0-3.el9_6"
    assert parsed["fixed_builds"][0]["stream"] == "el9"


def test_not_a_cve_document_is_rejected():
    with pytest.raises(ValueError):
        plugin.redhat_cve_rows({"message": "Not Found"})


def test_cve_ids_are_validated_before_they_reach_a_url():
    assert plugin.valid_cve_ids("CVE-2026-98432, cve-2024-1086\nCVE-2026-98432") \
        == ["CVE-2026-98432", "CVE-2024-1086"]
    assert plugin.valid_cve_ids(["CVE-2026-98432"]) == ["CVE-2026-98432"]
    assert plugin.valid_cve_ids("") == []
    for bad in ("CVE-2026-98432/../../x", "kernel", "CVE-2026-98432?host=web01", "CVE-26-1", "RHSA-2026:93412"):
        with pytest.raises(ValueError):
            plugin.valid_cve_ids(bad)


# ── the playbook: opt-in, and nothing but the CVE id leaves ───────────────────

@pytest.fixture(scope="module")
def play() -> dict:
    with open(os.path.join(_PLAYBOOKS, "fetch_redhat_cve_data.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)[0]


def test_playbook_refuses_to_run_without_confirmation(play):
    names = [t["name"] for t in play["tasks"]]
    gate = names.index("Refuse to contact the Red Hat API without an explicit confirmation")
    request = names.index("Read each CVE from the Red Hat Security Data API")
    assert gate < request
    assert play["tasks"][gate]["ansible.builtin.assert"]["that"] == ["confirm_redhat_cve_fetch | default(false) | bool"]
    assert names.index("Validate the requested CVE ids") < request


def test_playbook_sends_only_the_cve_id(play):
    requests = [t for t in play["tasks"] if "ansible.builtin.uri" in t]
    assert len(requests) == 1, "exactly one task may talk to the network"
    uri = requests[0]["ansible.builtin.uri"]
    assert uri["url"] == "{{ redhat_cve_api_base }}/{{ item }}.json"
    assert play["vars"]["redhat_cve_api_base"] == "https://access.redhat.com/hydra/rest/securitydata/cve"
    assert requests[0]["loop"] == "{{ fetch_ids }}"
    assert uri["method"] == "GET"
    assert uri["use_netrc"] is False and uri["force_basic_auth"] is False
    assert uri["validate_certs"] is True
    assert uri["headers"] == {"Accept": "application/json"}
    for forbidden in ("body", "src", "url_username", "url_password", "client_cert", "client_key"):
        assert forbidden not in uri


def test_playbook_marks_its_rows_with_their_source(play):
    assert play["vars"]["redhat_cve_source"] == plugin.SOURCE == "redhat_security_data_api"
    record = [t for t in play["tasks"] if t["name"] == "Record the CVE"][0]
    query = record["community.postgresql.postgresql_query"]["query"]
    # a row another source delivered is not overwritten
    assert "WHERE cve_events_received.source = %(src)s" in query


def test_fetch_playbook_is_in_no_workflow_or_pack():
    """Opt-in means nothing else launches it."""
    hits = []
    for root in ("ansible", "install", "scripts"):
        for base, _dirs, files in os.walk(os.path.join(_REPO, root)):
            for name in files:
                path = os.path.join(base, name)
                if path.endswith("fetch_redhat_cve_data.yml") or not name.endswith((".yml", ".yaml", ".py", ".json")):
                    continue
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
                # The identify playbook names it in a message and the filter
                # plugin in its docstring; neither is a launch.
                if "fetch_redhat_cve_data" in text and not path.endswith(
                        ("identify_affected_components.yml", "aac_redhat_cve.py")):
                    hits.append(os.path.relpath(path, _REPO))
    assert hits == []
