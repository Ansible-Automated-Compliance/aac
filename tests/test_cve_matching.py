"""CVE matching end to end, in a real PostgreSQL, with the SQL the playbooks run.

Nothing here re-implements the product: the schema comes from the shipped
files, the inventory rebuild and the match are the statements inside
refresh_inventory_catalog.yml and identify_affected_components.yml (read from
the YAML), and the CVE rows are the recorded Red Hat Security Data API response
for CVE-2026-98432 passed through the playbook's own filter.

Reference case: CVE-2026-98432, a kernel flaw fixed in
5.14.0-687.64.1.el9_8 (RHEL 9), 4.18.0-553.182.1.el8_10 (RHEL 8) and
6.12.0-211.72.1.el10_2 (RHEL 10).
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import yaml

from aac_pg_helpers import render_named, sql_literal

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ANSIBLE = os.path.join(_REPO, "ansible")
_FILES = os.path.join(_ANSIBLE, "files")
_PLAYBOOKS = os.path.join(_ANSIBLE, "playbooks")
_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

sys.path.insert(0, os.path.join(_PLAYBOOKS, "filter_plugins"))
from aac_redhat_cve import redhat_cve_rows  # noqa: E402

CVE = "CVE-2026-98432"
SCHEMA_FILES = ["rpm_evr_functions.sql", "inventory_catalog_schema.sql",
                "cve_cache_schema.sql", "patch_worklist_schema.sql"]
PG_QUERY = "community.postgresql.postgresql_query"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _tasks(playbook, play=0):
    return yaml.safe_load(_read(os.path.join(_PLAYBOOKS, playbook)))[play]["tasks"]


def _task(playbook, name, play=0):
    found = [t for t in _tasks(playbook, play) if t.get("name") == name]
    assert len(found) == 1, "task %r not found exactly once in %s" % (name, playbook)
    return found[0]


def _apply_schema(pg):
    for name in SCHEMA_FILES:
        pg.run(_read(os.path.join(_FILES, name)))


def _host_facts_sql():
    hosts = json.loads(_read(os.path.join(_FIXTURES, "cve_matching_hosts.json")))["hosts"]
    out = []
    for h in hosts:
        facts = {"host": {"hostname": h["hostname"], "kernel": h["kernel"]},
                 "packages": {"installed": h["packages"], "total_count": len(h["packages"])}}
        out.append(
            "INSERT INTO host_facts (host_id, hostname, os_family, os_distribution, os_version, facts) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb);"
            % tuple(sql_literal(v) for v in (h["hostname"], h["hostname"], h["os_family"],
                                             h["os_distribution"], h["os_version"], json.dumps(facts))))
    return "\n".join(out)


def _cve_sql(parsed):
    e = parsed["event"]
    out = ["INSERT INTO cve_events_received (cve_id, cvss_v3, severity, published_at, vendor, product, "
           "description, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"
           % tuple(sql_literal(v) for v in (e["cve_id"], e["cvss_v3"], e["severity"], e["published_at"],
                                            e["vendor"], e["product"], e["description"], e["source"]))]
    for r in parsed["fixed_builds"]:
        out.append(
            "INSERT INTO cve_fixed_builds (cve_id, package_name, fixed_evr, fix_state, stream, dist_tag, "
            "product_name, cpe, advisory_id, released_at, base_os, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
            % tuple(sql_literal(v) for v in (parsed["cve_id"], r["package_name"], r["fixed_evr"], r["fix_state"],
                                             r["stream"], r["dist_tag"], r["product_name"], r["cpe"],
                                             r["advisory_id"], r["released_at"], r["base_os"], e["source"])))
    return "\n".join(out)


def _identify(pg, cve_filter="", include_unaffected=False):
    task = _task("identify_affected_components.yml",
                 "Rebuild the catalog snapshot and record affected systems (one transaction)")
    pg.run(render_named(task[PG_QUERY]["query"],
                        {"filter": cve_filter, "include_unaffected": include_unaffected}))


@pytest.fixture(scope="module")
def pg(aac_pg):
    # host_facts is created inline by the database role, not from a file.
    role = yaml.safe_load(_read(os.path.join(_ANSIBLE, "roles", "aac_compliance_db", "tasks", "schema.yml")))
    for wanted in ("Create host_facts table", "Create host_facts_latest view"):
        task = [t for t in role if t.get("name") == wanted][0]
        aac_pg.run(task[PG_QUERY]["query"].rstrip().rstrip(";") + ";")

    _apply_schema(aac_pg)
    aac_pg.run(_host_facts_sql())

    # The inventory rebuild: the playbook's own statements, in its order.
    rebuild = _task("refresh_inventory_catalog.yml",
                    "Rebuild installed_inventory + refresh catalog from host_facts_latest")
    for statement in rebuild["loop"]:
        aac_pg.run(statement.rstrip().rstrip(";") + ";")

    parsed = redhat_cve_rows(json.loads(_read(os.path.join(_FIXTURES, "redhat_cve_%s.json" % CVE))))
    aac_pg.run(_cve_sql(parsed))
    # A CVE known only by an exact version list, one with no version data, and
    # one with a version-only vendor fix: the paths that existed before.
    aac_pg.run("""
        INSERT INTO cve_events_received (cve_id, severity, vendor, product, affected_versions, source) VALUES
          ('CVE-2026-00001', 'HIGH',   'bash', 'bash', ARRAY['5.1.8'], 'test'),
          ('CVE-2026-00002', 'MEDIUM', 'bash', 'bash', NULL,           'test'),
          ('CVE-2026-00003', 'HIGH',   'openssl', 'openssl', NULL,     'test');
        INSERT INTO cve_vendor_remediations (cve_id, vendor, vendor_advisory_id, fix_version)
          VALUES ('CVE-2026-00003', 'openssl', 'TEST-SA-3', '3.2.4');
        INSERT INTO cve_fixed_builds (cve_id, package_name, fixed_evr, stream, dist_tag, product_name, source)
          VALUES ('CVE-2026-00003', 'openssl', '1:3.2.2-7.el9_5', 'el9', 'el9_5', 'Test OS 9', 'test');
    """)
    return aac_pg


@pytest.fixture(scope="module")
def verdicts(pg):
    rows = pg.rows("SELECT hostname, product, verdict, COALESCE(installed_evr, ''), COALESCE(booted_evr, ''), "
                   "COALESCE(fixed_evr, ''), basis, detail FROM aac_cve_host_verdicts(%s)" % sql_literal(CVE))
    by_host = {}
    for hostname, product, verdict, installed, booted, fixed, basis, detail in rows:
        assert hostname not in by_host, "more than one row for %s: %s" % (hostname, product)
        by_host[hostname] = {"product": product, "verdict": verdict, "installed": installed,
                             "booted": booted, "fixed": fixed, "basis": basis, "detail": detail}
    return by_host


# ── A. the catalog keeps the whole build ───────────────────────────────────────

def test_catalog_stores_epoch_version_release(pg):
    assert pg.rows("SELECT package_version, COALESCE(package_epoch, ''), package_release, package_evr, package_format "
                   "FROM installed_inventory WHERE hostname = 'el9-vulnerable.example.com' "
                   "AND package_name IN ('kernel', 'openssl') ORDER BY package_name") == [
        ["5.14.0", "", "687.61.1.el9_8", "5.14.0-687.61.1.el9_8", "rpm"],
        ["3.2.2", "1", "6.el9_5", "1:3.2.2-6.el9_5", "rpm"],
    ]


def test_catalog_records_the_newest_installed_kernel_not_the_first_listed(pg):
    # package_facts lists 687.58 first on this host; main kept element 0.
    assert pg.rows("SELECT package_evr, array_to_string(installed_evrs, ' ') FROM installed_inventory "
                   "WHERE hostname = 'el9-vulnerable.example.com' AND package_name = 'kernel'") \
        == [["5.14.0-687.61.1.el9_8", "5.14.0-687.58.1.el9_8 5.14.0-687.61.1.el9_8"]]


def test_catalog_records_the_booted_kernel_separately(pg):
    assert pg.rows("SELECT package_evr, booted_evr FROM installed_inventory "
                   "WHERE hostname = 'el9-reboot-pending.example.com' AND package_name = 'kernel'") \
        == [["5.14.0-687.64.1.el9_8", "5.14.0-687.61.1.el9_8"]]
    # Only the packages that carry the running kernel image get a booted build.
    assert pg.value("SELECT count(*) FROM installed_inventory WHERE booted_evr IS NOT NULL "
                    "AND package_name !~ '^kernel(-rt)?(-core)?$'") == "0"
    assert pg.value("SELECT COALESCE(booted_evr, 'none') FROM installed_inventory "
                    "WHERE hostname = 'el9-vulnerable.example.com' AND package_name = 'kernel-tools'") == "none"


def test_catalog_keeps_the_debian_version_string(pg):
    assert pg.rows("SELECT package_version, package_evr, package_format, COALESCE(package_release, '') "
                   "FROM installed_inventory WHERE hostname = 'debian-host.example.com' "
                   "AND package_name = 'openssl'") == [["3.0.11-1~deb12u2", "3.0.11-1~deb12u2", "deb", ""]]


def test_schema_change_reaches_an_existing_install(pg):
    """Drop the new columns (an install that predates them), re-apply the files."""
    new = {"installed_inventory": ["package_format", "package_epoch", "package_release", "package_evr",
                                   "installed_evrs", "booted_evr"],
           "patch_worklist": ["installed_evr", "booted_evr", "version_verdict", "verdict_detail"]}
    saved = pg.value("SELECT count(*) FROM installed_inventory")
    pg.run("BEGIN; CREATE TABLE _keep AS SELECT * FROM installed_inventory; COMMIT;")
    for table, columns in new.items():
        pg.run("".join("ALTER TABLE %s DROP COLUMN %s;" % (table, c) for c in columns))
    _apply_schema(pg)
    _apply_schema(pg)  # and again: idempotent
    for table, columns in new.items():
        got = {r[0] for r in pg.rows("SELECT column_name FROM information_schema.columns "
                                     "WHERE table_name = %s" % sql_literal(table))}
        assert set(columns) <= got, table
    # Existing rows survive; put the build columns back for the tests that follow.
    assert pg.value("SELECT count(*) FROM installed_inventory") == saved
    pg.run("TRUNCATE installed_inventory; INSERT INTO installed_inventory SELECT * FROM _keep; DROP TABLE _keep;")


# ── C / D. the reference CVE ──────────────────────────────────────────────────

@pytest.mark.parametrize("host, verdict, fixed", [
    ("el9-vulnerable.example.com", "affected", "5.14.0-687.64.1.el9_8"),
    ("el9-fixed.example.com", "fixed", "5.14.0-687.64.1.el9_8"),
    ("el9-reboot-pending.example.com", "reboot_pending", "5.14.0-687.64.1.el9_8"),
    # an el8 host is judged against the el8 build, never the el9 one
    ("el8-vulnerable.example.com", "affected", "4.18.0-553.182.1.el8_10"),
    ("el8-fixed.example.com", "fixed", "4.18.0-553.182.1.el8_10"),
    # an extended-support branch is judged against its own build
    ("el9-eus-fixed.example.com", "fixed", "5.14.0-427.161.1.el9_4"),
    # kernel-core without the kernel meta package is still a kernel
    ("el9-minimal.example.com", "affected", "5.14.0-687.64.1.el9_8"),
    # RHEL 9 kernel-rt is built from the kernel source: judged against `kernel`
    ("el9-rt.example.com", "affected", "5.14.0-687.64.1.el9_8"),
    # the vendor states RHEL 7 is not affected
    ("el7-host.example.com", "not_affected", ""),
    # no fixed build for this stream: unknown, and no cross-stream comparison
    ("fedora-host.example.com", "unknown", ""),
    # no kernel package at all
    ("container-host.example.com", "not_installed", ""),
    ("debian-host.example.com", "not_installed", ""),
])
def test_reference_cve_verdict(verdicts, host, verdict, fixed):
    assert verdicts[host]["verdict"] == verdict, verdicts[host]["detail"]
    assert verdicts[host]["fixed"] == fixed


def test_every_host_gets_exactly_one_answer(pg, verdicts):
    assert len(verdicts) == int(pg.value("SELECT count(DISTINCT hostname) FROM installed_inventory"))


def test_reboot_pending_says_so_and_names_the_builds(verdicts):
    detail = verdicts["el9-reboot-pending.example.com"]["detail"]
    assert detail.startswith("fixed build installed, reboot pending")
    assert "booted 5.14.0-687.61.1.el9_8" in detail and "installed 5.14.0-687.64.1.el9_8" in detail


def test_not_installed_is_not_unknown(verdicts):
    row = verdicts["container-host.example.com"]
    assert row["verdict"] == "not_installed"
    assert row["detail"].startswith("not affected (not installed)")
    assert verdicts["fedora-host.example.com"]["detail"].startswith("no fixed build published for stream fc42")


def test_no_host_is_compared_with_another_streams_build(pg):
    rows = pg.rows("SELECT hostname, installed_evr, fixed_evr FROM aac_cve_host_verdicts(%s) "
                   "WHERE fixed_evr IS NOT NULL "
                   "AND aac_rpm_stream(installed_evr) IS DISTINCT FROM aac_rpm_stream(fixed_evr)" % sql_literal(CVE))
    assert rows == []


def test_layered_product_builds_are_not_matched(pg):
    # The NVIDIA kernel build (el10nv) and OpenShift rows are stored, not used.
    assert int(pg.value("SELECT count(*) FROM cve_fixed_builds WHERE cve_id = %s AND NOT base_os"
                        % sql_literal(CVE))) > 0
    assert pg.rows("SELECT verdict, fixed_evr FROM aac_cve_package_verdict(%s, 'kernel', 'rpm', "
                   "'6.12.0-124.8.1.el10_1', NULL, 'el10', '6.12.0', NULL)" % sql_literal(CVE)) \
        == [["affected", "6.12.0-264.14.1.el10_3"]]
    assert pg.rows("SELECT verdict FROM aac_cve_package_verdict(%s, 'skopeo', 'rpm', '2:1.9.0-1.el8', "
                   "NULL, 'el8', '1.9.0', NULL)" % sql_literal(CVE)) == [["unknown"]]


@pytest.mark.parametrize("installed, verdict, fixed", [
    ("6.12.0-211.70.1.el10_2", "affected", "6.12.0-211.72.1.el10_2"),
    ("6.12.0-211.72.1.el10_2", "fixed", "6.12.0-211.72.1.el10_2"),
    ("6.12.0-264.10.1.el10_3", "affected", "6.12.0-264.14.1.el10_3"),
    ("6.12.0-55.117.1.el10_0", "fixed", "6.12.0-55.117.1.el10_0"),
    ("4.18.0-553.182.1.rt7.523.el8_10", "fixed", "4.18.0-553.182.1.rt7.523.el8_10"),
])
def test_branch_of_the_installed_build_selects_the_fixed_build(pg, installed, verdict, fixed):
    package = "kernel-rt" if ".rt7." in installed else "kernel"
    assert pg.rows("SELECT verdict, fixed_evr FROM aac_cve_package_verdict(%s, %s, 'rpm', %s, NULL, NULL, 'x', NULL)"
                   % (sql_literal(CVE), sql_literal(package), sql_literal(installed))) == [[verdict, fixed]]


# ── the identify playbook's own statement ─────────────────────────────────────

def test_identify_writes_only_the_work_items(pg):
    _identify(pg, CVE)
    rows = pg.rows("SELECT hostname, product, installed_version, fixed_version, version_verdict, "
                   "COALESCE(booted_evr, ''), fix_match, advisory_id FROM patch_worklist "
                   "WHERE host_resolution = 'catalog_match' ORDER BY hostname")
    assert rows == [
        ["el8-vulnerable.example.com", "kernel", "4.18.0", "4.18.0-553.182.1.el8_10", "affected",
         "4.18.0-553.180.1.el8_10", "vendor_fix", "RHSA-2026:93414"],
        ["el9-minimal.example.com", "kernel-core", "5.14.0", "5.14.0-687.64.1.el9_8", "affected",
         "5.14.0-687.61.1.el9_8", "vendor_fix", "RHSA-2026:93412"],
        ["el9-reboot-pending.example.com", "kernel", "5.14.0", "5.14.0-687.64.1.el9_8", "reboot_pending",
         "5.14.0-687.61.1.el9_8", "vendor_fix", "RHSA-2026:93412"],
        ["el9-rt.example.com", "kernel-rt", "5.14.0", "5.14.0-687.64.1.el9_8", "affected",
         "5.14.0-687.61.1.el9_8", "vendor_fix", "RHSA-2026:93412"],
        ["el9-vulnerable.example.com", "kernel", "5.14.0", "5.14.0-687.64.1.el9_8", "affected",
         "5.14.0-687.61.1.el9_8", "vendor_fix", "RHSA-2026:93412"],
        ["fedora-host.example.com", "kernel", "6.14.5", "", "unknown", "6.14.5-300.fc42", "none", ""],
    ]


def test_identify_include_unaffected_adds_fixed_rows_but_never_not_installed(pg):
    _identify(pg, CVE, include_unaffected=True)
    got = dict(pg.rows("SELECT hostname, version_verdict FROM patch_worklist WHERE host_resolution = 'catalog_match'"))
    assert got["el9-fixed.example.com"] == "fixed"
    assert "container-host.example.com" not in got


def test_exact_list_fallback_is_unchanged(pg):
    """No fixed build: affected_versions decides, exactly as before."""
    rows = pg.rows("SELECT hostname, verdict, basis FROM aac_cve_host_verdicts('CVE-2026-00001') "
                   "WHERE verdict <> 'not_installed' ORDER BY hostname")
    assert ["el9-vulnerable.example.com", "affected", "affected_versions"] in rows
    assert ["el8-vulnerable.example.com", "not_listed", "affected_versions"] in rows
    assert ["debian-host.example.com", "not_listed", "affected_versions"] in rows
    # No version data at all: unknown, and still reported (fail closed).
    assert {r[1] for r in pg.rows("SELECT hostname, verdict FROM aac_cve_host_verdicts('CVE-2026-00002') "
                                  "WHERE verdict <> 'not_installed'")} == {"unknown"}
    _identify(pg, "CVE-2026-00001,CVE-2026-00002")
    assert pg.rows("SELECT cve_id, count(*) FROM patch_worklist WHERE host_resolution = 'catalog_match' "
                   "GROUP BY 1 ORDER BY 1") == [["CVE-2026-00001", "4"], ["CVE-2026-00002", "6"]]


def test_fixed_build_wins_over_the_vendor_remediation_and_dpkg_falls_back(pg):
    rows = {r[0]: r[1:] for r in pg.rows(
        "SELECT hostname, verdict, COALESCE(fixed_evr, ''), COALESCE(fix_version, ''), basis "
        "FROM aac_cve_host_verdicts('CVE-2026-00003') WHERE verdict <> 'not_installed'")}
    # epoch 1 on both sides; 6.el9_5 is lower than 7.el9_5
    assert rows["el9-vulnerable.example.com"] == ["affected", "1:3.2.2-7.el9_5", "3.2.4", "fixed_build"]
    # a dpkg host is never compared with an rpm build
    assert rows["debian-host.example.com"] == ["unknown", "", "3.2.4", "affected_versions"]
    _identify(pg, "CVE-2026-00003")
    assert pg.rows("SELECT hostname, fixed_version, package_manager FROM patch_worklist "
                   "WHERE host_resolution = 'catalog_match' ORDER BY hostname") == [
        ["debian-host.example.com", "3.2.4", "apt"],
        ["el9-vulnerable.example.com", "1:3.2.2-7.el9_5", "dnf"],
    ]


def test_filtered_run_rebuilds_the_whole_catalog_snapshot(pg):
    _identify(pg, CVE)
    assert pg.rows("SELECT DISTINCT cve_id FROM patch_worklist WHERE host_resolution = 'catalog_match'") == [[CVE]]


# ── F. what the cache holds ───────────────────────────────────────────────────

def _preflight(pg, cve_filter):
    task = _task("identify_affected_components.yml", "Check the CVE store and inventory freshness")
    sql = render_named(task[PG_QUERY]["query"], {"filter": cve_filter})
    names = ["cve_count", "cve_demo_count", "scope_count", "scope_real_count", "cves_not_in_cache",
             "cves_with_fixed_build", "rpm_build_rows", "inventory_rows", "hosts", "catalog_products",
             "inventory_age_hours"]
    row = pg.rows("SELECT %s FROM (%s) q" % (", ".join(names), sql.rstrip().rstrip(";")))[0]
    return dict(zip(names, row))


def test_preflight_tells_demo_rows_from_delivered_ones(pg):
    pg.run(_read(os.path.join(_FILES, "demo_cve_fixture.sql")))
    everything = _preflight(pg, "")
    assert int(everything["cve_demo_count"]) == 14
    assert int(everything["scope_real_count"]) == int(everything["cve_count"]) - 14
    demo_only = _preflight(pg, "CVE-2026-90001,CVE-2026-90003")
    assert (demo_only["scope_count"], demo_only["scope_real_count"]) == ("2", "0")
    real = _preflight(pg, CVE)
    assert (real["scope_count"], real["scope_real_count"], real["cves_not_in_cache"]) == ("1", "1", "")
    missing = _preflight(pg, CVE + ", CVE-1999-99999")
    assert missing["cves_not_in_cache"] == "CVE-1999-99999"
    assert int(real["rpm_build_rows"]) > 0 and int(real["cves_with_fixed_build"]) >= 1


def test_identify_playbook_reports_the_demo_only_case():
    text = _read(os.path.join(_PLAYBOOKS, "identify_affected_components.yml"))
    names = [t.get("name") for t in _tasks("identify_affected_components.yml")]
    assert "Say when the cache holds only demo rows" in names
    assert "Stop when none of the requested CVEs is in the cache" in names
    stats = _task("identify_affected_components.yml",
                  "Publish patch verdict as workflow stats (for AO agentic triage)")
    assert {"cve_cache_demo_only", "cves_not_in_cache", "reboot_pending_hosts"} \
        <= set(stats["ansible.builtin.set_stats"]["data"])
    assert "CVE CACHE HOLDS ONLY DEMO ROWS" in text


# ── E. patch_assurance A0 uses the same comparison ────────────────────────────

@pytest.mark.parametrize("evrs, product, uname, installed_ok, booted_ok", [
    ("5.14.0-687.61.1.el9_8", "kernel", "5.14.0-687.61.1.el9_8.x86_64", "f", "f"),
    ("5.14.0-687.61.1.el9_8 5.14.0-687.64.1.el9_8", "kernel", "5.14.0-687.61.1.el9_8.x86_64", "t", "f"),
    ("5.14.0-687.61.1.el9_8 5.14.0-687.64.1.el9_8", "kernel", "5.14.0-687.64.1.el9_8.x86_64", "t", "t"),
    # not a kernel image package: the booted kernel does not enter into it
    ("5.14.0-687.64.1.el9_8", "kernel-tools", "5.14.0-687.61.1.el9_8.x86_64", "t", "t"),
    ("", "kernel", "5.14.0-687.64.1.el9_8.x86_64", "f", "t"),
])
def test_patch_assurance_a0_query(pg, evrs, product, uname, installed_ok, booted_ok):
    task = _task("patch_assurance.yml",
                 "A0 — compare installed rpm builds with the fixed build (rpm ordering)", play=2)
    sql = render_named(task[PG_QUERY]["query"],
                       {"evrs": evrs, "product": product, "uname": uname, "fixed": "5.14.0-687.64.1.el9_8"})
    assert pg.rows("SELECT installed_ok, booted_ok FROM (%s) q" % sql.rstrip().rstrip(";")) \
        == [[installed_ok, booted_ok]]


def test_patch_assurance_has_a_reboot_pending_outcome():
    outcome = _task("patch_assurance.yml", "Determine the terminal outcome", play=2)
    assert "reboot_pending" in outcome["ansible.builtin.set_fact"]["assurance_outcome"]
    record = _read(os.path.join(_PLAYBOOKS, "patch_change_record.yml"))
    assert "'reboot_pending'" in record
