"""The weekly update (scripts/weekly_update.py) and the request forms.

The update is what people with AAC installed read before they update, so the
window must not drop or repeat a pull request from one week to the next, a
breaking change must be raised to the top, and the forms the update links to
must exist and parse.
"""
import datetime as dt
import importlib.util
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("weekly_update", ROOT / "scripts" / "weekly_update.py")
weekly_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weekly_update)

D = dt.date.fromisoformat


def pr(number, title, merged, login="someone", labels=()):
    return {
        "number": number,
        "title": title,
        "mergedAt": f"{merged}T12:00:00Z",
        "author": {"login": login},
        "labels": [{"name": name} for name in labels],
    }


PRS = [
    pr(1, "feat(m365): shape capture", "2026-11-10"),
    pr(2, "fix: stored counts", "2026-11-17"),
    pr(3, "chore(policies): pin to abc123", "2026-11-18"),
    pr(4, "feat!: evidence table renamed", "2026-11-19"),
    pr(5, "chore(deps): bump x", "2026-11-20", login="app/dependabot"),
    pr(6, "Tidy the README", "2026-11-24"),
    pr(7, "docs: later", "2026-11-25"),
    pr(8, "bump y", "2026-11-21", labels=("dependencies",)),
]


def test_window_is_exclusive_at_the_start_and_inclusive_at_the_end():
    text = weekly_update.render(PRS, D("2026-11-17"), D("2026-11-24"))
    assert "#2]" not in text  # merged on the last day of the previous window
    assert "#6]" in text  # merged on the last day of this one
    assert "#1]" not in text and "#7]" not in text


def test_consecutive_windows_list_every_pull_request_exactly_once():
    weeks = [(D("2026-11-03"), D("2026-11-10")), (D("2026-11-10"), D("2026-11-17")), (D("2026-11-17"), D("2026-11-24")), (D("2026-11-24"), D("2026-12-01"))]
    seen = [p["number"] for since, until in weeks for p in PRS if weekly_update.in_window(p, since, until)]
    assert sorted(seen) == [p["number"] for p in PRS]


def test_headings_follow_the_title_prefix():
    text = weekly_update.render(PRS, D("2026-11-09"), D("2026-11-25"))
    section = {}
    heading = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:]
        elif line.startswith("- ") and heading:
            section.setdefault(heading, []).append(line)
    assert any("#1]" in line and "**m365:** Shape capture" in line for line in section["New"])
    assert any("#2]" in line for line in section["Fixed"])
    assert any("#3]" in line and "Pin to abc123" in line for line in section["Policy library"])
    assert any("#6]" in line for line in section["Other changes"])
    assert any("#7]" in line for line in section["Install and documentation"])


def test_breaking_change_is_raised_to_the_top():
    text = weekly_update.render(PRS, D("2026-11-17"), D("2026-11-24"))
    assert "## Needs action when you update" in text
    assert text.index("## Needs action when you update") < text.index("## New")
    top = text.split("## Needs action when you update")[1].split("## ")[0]
    assert "#4]" in top


def test_dependency_bumps_are_counted_not_listed_as_changes():
    text = weekly_update.render(PRS, D("2026-11-17"), D("2026-11-24"))
    assert "3 pull requests, 2 dependency updates" in text
    bumps = text.split("## Dependency updates")[1].split("## ")[0]
    assert "#5]" in bumps and "#8]" in bumps
    assert "bump x" not in text and "bump y" not in text


def test_a_week_with_nothing_merged_says_so():
    text = weekly_update.render(PRS, D("2026-12-01"), D("2026-12-08"))
    assert "0 pull requests, 0 dependency updates" in text
    assert "No feature or fix was merged" in text


def test_index_lists_updates_newest_first(tmp_path):
    index = tmp_path / "README.md"
    index.write_text(f"top\n{weekly_update.INDEX_BEGIN}\n- old\n{weekly_update.INDEX_END}\nbottom\n")
    for name in ("2026-11-17.md", "2026-11-24.md", "notes.md"):
        (tmp_path / name).write_text("x")
    weekly_update.update_index(index)
    body = index.read_text()
    assert body.startswith("top\n") and body.endswith("bottom\n")
    assert body.index("2026-11-24") < body.index("2026-11-17")
    assert "notes" not in body and "- old" not in body


def test_published_updates_are_all_in_the_index():
    index = (weekly_update.UPDATES_DIR / "README.md").read_text()
    for page in weekly_update.UPDATES_DIR.glob("20??-??-??.md"):
        assert f"]({page.name})" in index, f"{page.name} is not listed in docs/updates/README.md"


def test_email_version_keeps_every_line_and_uses_full_addresses():
    text = weekly_update.render(PRS, D("2026-11-09"), D("2026-11-25"))
    mail = weekly_update.to_email_html(text)
    for number in (1, 2, 3, 4, 6, 7):
        assert f"/pull/{number}\"" in mail
    assert mail.count("<li") == sum(1 for line in text.splitlines() if line.startswith("- "))
    assert "](" not in mail and "**" not in mail and "`" not in mail  # no Markdown left for the reader to see
    hrefs = __import__("re").findall(r'href="([^"]+)"', mail)
    assert hrefs and all(h.startswith("https://github.com/Ansible-Automated-Compliance/aac/") for h in hrefs)
    assert any(h.endswith("/blob/main/CHANGELOG.md") for h in hrefs)
    assert any(h.endswith("/blob/main/docs/updates/README.md") for h in hrefs)


def test_email_version_escapes_markup_in_titles():
    prs = [pr(9, 'fix: <aac-host> placeholder & "quoting"', "2026-11-20")]
    mail = weekly_update.to_email_html(weekly_update.render(prs, D("2026-11-17"), D("2026-11-24")))
    assert "<aac-host>" not in mail
    assert "placeholder &amp; &quot;quoting&quot;" in mail


def test_a_pull_request_title_cannot_place_a_link_or_an_attribute():
    import re

    hostile = [
        pr(10, 'fix: see [here](https://evil.example/x" onmouseover="alert(1))', "2026-11-20"),
        pr(11, "feat: [docs](javascript:alert(1)) updated", "2026-11-20"),
        pr(12, "fix: [x](https://github.com/Ansible-Automated-Compliance/aac.evil.example/)", "2026-11-20"),
        pr(13, 'docs: <img src=x onerror="alert(1)">', "2026-11-20"),
    ]
    text = weekly_update.render(hostile, D("2026-11-17"), D("2026-11-24"))
    assert "](https://evil" not in text and "](javascript" not in text
    mail = weekly_update.to_email_html(text)
    hrefs = re.findall(r'href="([^"]*)"', mail)
    assert len(hrefs) == 4 + 3  # one per pull request, plus the three footer links
    assert all(h.startswith("https://github.com/Ansible-Automated-Compliance/aac/") for h in hrefs)
    assert "<img" not in mail and "javascript:alert" not in "".join(hrefs)
    for tag in re.findall(r"<[^>]+>", mail):  # no attribute other than the ones the script writes
        assert set(re.findall(r'\s([a-z-]+)="', tag)) <= {"href", "style"}, tag


FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"


def test_request_forms_parse_and_ask_not_to_post_private_details():
    forms = sorted(p for p in FORMS.glob("*.yml") if p.name != "config.yml")
    assert {p.name for p in forms} >= {"feature_request.yml", "change_request.yml", "report_request.yml", "problem.yml"}
    for path in forms:
        form = yaml.safe_load(path.read_text())
        assert form["name"] and form["description"] and form["body"], path.name
        ids = [item["id"] for item in form["body"] if "id" in item]
        assert len(ids) == len(set(ids)), f"{path.name}: duplicate field id"
        text = path.read_text().lower()
        assert "public" in text and "password" in text, f"{path.name} must warn that the request is public"


def test_form_chooser_points_security_reports_away_from_public_issues():
    config = yaml.safe_load((FORMS / "config.yml").read_text())
    urls = [link["url"] for link in config["contact_links"]]
    assert any("security/advisories/new" in url for url in urls)
