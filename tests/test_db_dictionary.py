"""The database dictionary page matches the table definitions in the tree."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("db_dictionary", ROOT / "scripts" / "db_dictionary.py")
dd = importlib.util.module_from_spec(spec)
sys.modules["db_dictionary"] = dd
spec.loader.exec_module(dd)


def test_page_is_current():
    assert dd.PAGE.read_text() == dd.render(dd.read()), "run: python3 scripts/db_dictionary.py --write"


def test_core_tables_are_found():
    tables = dd.read()["tables"]
    for name in ("compliance_results", "compliance_facts", "host_facts", "compliance_findings", "framework_catalog"):
        assert name in tables and tables[name]["columns"], name


def _schema(tmp_path, files):
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return dd.read(tmp_path)


def test_create_alter_view_and_types_are_read(tmp_path):
    schema = _schema(tmp_path, {
        "ansible/files/a.sql": (
            "CREATE TABLE IF NOT EXISTS widgets (\n"
            "  id BIGSERIAL PRIMARY KEY, -- the key\n"
            "  hostname varchar (255) NOT NULL,\n"
            "  score DECIMAL(5,2) DEFAULT 0,\n"
            "  seen_at TIMESTAMP WITH TIME ZONE,\n"
            "  UNIQUE (hostname)\n"
            ");\n"
            "ALTER TABLE widgets ADD COLUMN IF NOT EXISTS notes TEXT;\n"
            "CREATE OR REPLACE VIEW widgets_latest AS SELECT * FROM widgets;\n"
        ),
    })
    widgets = schema["tables"]["widgets"]
    assert list(widgets["columns"]) == ["id", "hostname", "score", "seen_at", "notes"]
    assert widgets["columns"]["hostname"][0]["type"] == "VARCHAR(255)"
    assert widgets["columns"]["score"][0]["type"] == "DECIMAL(5,2)"
    assert widgets["columns"]["seen_at"][0]["type"] == "TIMESTAMP WITH TIME ZONE"
    assert widgets["constraints"] == ["UNIQUE (hostname)"]
    assert "widgets_latest" in schema["views"]


def test_a_column_with_two_types_and_an_undefined_table_are_reported(tmp_path):
    schema = _schema(tmp_path, {
        "ansible/files/a.sql": "CREATE TABLE one (id SERIAL PRIMARY KEY, severity VARCHAR(20));",
        "ansible/files/b.sql": "CREATE TABLE two (id SERIAL PRIMARY KEY, severity VARCHAR(16));",
        "ansible/playbooks/p.yml": "query: INSERT INTO missing_table (a) VALUES (1)\n",
    })
    page = dd.render(schema)
    assert "| `severity` | `VARCHAR(16)` in two; `VARCHAR(20)` in one |" in page
    assert "| `missing_table` |" in page
