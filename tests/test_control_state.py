"""Per-control results: the schema file and the places that write through it.

Static and SQL-shape checks. The function's behaviour (first run, unchanged
run, one change, a control that disappears, an out-of-order run, the writer's
privileges) was exercised against PostgreSQL 16 in the pull request that added
it.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "ansible/files/control_state_schema.sql").read_text()
ROLE = ROOT / "ansible/roles/aac_store_results/tasks/main.yml"
SIGNATURE = "control_state_record(bigint,text,text,jsonb)"

CALLERS = [
    "ansible/playbooks/cis_rhel9_assessment.yml",
    "ansible/playbooks/cis_rhel8_assessment.yml",
    "ansible/playbooks/cis_windows_server_2022_assessment.yml",
]


def _code(sql):
    return re.sub(r"--[^\n]*", "", sql)


def test_schema_is_idempotent():
    code = _code(SQL)
    assert not re.search(r"CREATE TABLE (?!IF NOT EXISTS)", code)
    assert not re.search(r"CREATE INDEX (?!IF NOT EXISTS)", code)
    assert not re.search(r"CREATE VIEW", code), "views must be CREATE OR REPLACE"
    assert not re.search(r"CREATE FUNCTION", code), "functions must be CREATE OR REPLACE"
    for trig in re.findall(r"CREATE TRIGGER (\w+)", code):
        assert f"DROP TRIGGER IF EXISTS {trig}" in code


def test_schema_changes_no_existing_table():
    code = _code(SQL)
    assert "ALTER TABLE" not in code
    assert not re.search(r"DROP (TABLE|VIEW|FUNCTION|INDEX)", code)


def test_state_is_one_row_per_host_framework_control():
    assert re.search(r"PRIMARY KEY \(hostname, framework, control_id\)", SQL)
    assert "ON CONFLICT (hostname, framework, control_id) DO UPDATE" in SQL


def test_history_is_written_only_on_a_change_and_is_append_only():
    assert "WHERE u.old_status IS DISTINCT FROM u.status" in SQL
    assert re.search(r"BEFORE UPDATE OR DELETE ON control_state_history", SQL)
    assert re.search(r"BEFORE TRUNCATE ON control_state_history", SQL)


def test_a_control_missing_from_a_later_run_is_marked_not_reported():
    assert "'not_reported'::text AS status" in SQL
    assert "NOT EXISTS (SELECT 1 FROM incoming i WHERE i.control_id = s.control_id)" in SQL


def test_write_function_is_the_only_write_path_for_the_writer():
    assert re.search(r"SECURITY DEFINER SET search_path = public, pg_temp", SQL)
    assert "REVOKE ALL ON FUNCTION control_state_record(bigint, text, text, jsonb) FROM PUBLIC" in SQL
    grants = re.findall(r"GRANT ([A-Z, ]+) ON ([^;]+?) TO\s+(\w+)", _code(SQL), flags=re.S)
    assert grants
    for privilege, _target, _role in grants:
        assert privilege.strip() in {"SELECT", "EXECUTE"}, privilege
    users = (ROOT / "ansible/roles/aac_compliance_db/tasks/users.yml").read_text()
    assert "GRANT EXECUTE ON FUNCTION control_state_record(bigint, text, text, jsonb) TO {{ aac_db_writer_user }}" in users
    assert not re.search(r"GRANT[^;]*(INSERT|UPDATE)[^;]*control_state", users)


def test_function_refuses_a_result_it_cannot_tie_to_a_stored_row():
    assert "r.id = p_result_id AND r.framework = p_framework" in SQL
    assert "old_result_id <= p_result_id" in SQL


def test_database_role_creates_the_schema():
    tasks = yaml.safe_load((ROOT / "ansible/roles/aac_compliance_db/tasks/schema.yml").read_text())
    mine = [t for t in tasks if "control_state_schema.sql" in str(t.get("community.postgresql.postgresql_script", {}).get("path", ""))]
    assert len(mine) == 1
    assert "when" not in mine[0] and "loop" not in mine[0], "the schema tasks are parsed by other installers: no loop, no when"


def test_store_role_records_state_after_the_summary_row():
    tasks = yaml.safe_load(ROLE.read_text())
    names = [t.get("name", "") for t in tasks]
    expose = names.index("Expose result ID")
    check = names.index("Check that the per-control tables are installed")
    record = names.index("Record per-control state and status changes")
    assert expose < check < record
    query = tasks[record]["community.postgresql.postgresql_query"]
    assert query["query"].count("control_state_record(") == 1
    assert len(query["positional_args"]) == 4
    conditions = " ".join(tasks[check]["when"])
    assert "aac_result_control_results" in conditions and "length > 0" in conditions
    assert SIGNATURE in tasks[check]["community.postgresql.postgresql_query"]["query"]


def test_default_is_an_empty_list():
    defaults = yaml.safe_load((ROOT / "ansible/roles/aac_store_results/defaults/main.yml").read_text())
    assert defaults["aac_result_control_results"] == []


def test_callers_pass_the_reports_control_results():
    for rel in CALLERS:
        text = (ROOT / rel).read_text()
        assert 'aac_result_control_results: "{{ compliance_result.control_results | default([]) }}"' in text, rel
    stored = (ROOT / "ansible/playbooks/evaluate_stored_facts.yml").read_text()
    assert "control_state_record(%s::bigint, %s, %s, %s::jsonb)" in stored
    m365 = (ROOT / "collections/ansible_collections/aac/m365/roles/m365_assessment/tasks/persist.yml").read_text()
    assert "control_state_record(" in m365 and "m365_report.control_results" in m365


def test_reference_page_names_every_status_the_schema_sets():
    doc = (ROOT / "docs/reference/PER_CONTROL_RESULTS.md").read_text()
    for status in ("pass", "fail", "evidence_missing", "not_attested", "not_applicable", "not_reported", "invalid"):
        assert f"`{status}`" in doc
    assert "honest" not in doc.lower()
