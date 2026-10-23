#!/usr/bin/env python3
"""
Parse OpenSCAP XCCDF result XML into AAC's compliance-result shape.

Input: the XML produced by `oscap xccdf eval --results <file> ...` (an XCCDF
document containing the Benchmark rules and a <TestResult>). Deterministic,
no network — the testable core of the OpenSCAP integration.

Design decisions (see docs / the integration playbook):
  - **Namespace-agnostic.** XCCDF ships as 1.1 (checklists.nist.gov/xccdf/1.1)
    or 1.2 (…/xccdf/1.2), and content varies. We match elements by *local*
    tag name so both parse without hard-coding a namespace.
  - **Result classification is the trap.** Only `fail` and `error` count as
    violations. `pass`/`fixed` count as passed. `notapplicable`, `notchecked`,
    `notselected`, `informational`, `unknown` are NEUTRAL — counting any of
    them as a failure is the classic way this ingestion produces garbage
    compliance percentages, so they are excluded from pass AND fail.
  - **Capture CCE/CCI idents now.** They are the hook for a later crosswalk to
    NIST 800-53 / other frameworks; we record them but do NOT map yet.

Emitted (see parse_xccdf_results): counts, compliance_pct, the OpenSCAP score,
benchmark/profile/test-result identity, and per-rule results (with titles
resolved from the Benchmark's <Rule> elements when present).
"""
from __future__ import annotations

import json
import re
import sys
from xml.etree import ElementTree as ET

# XML hardening: XCCDF results are attacker-influenceable, so guard against XXE
# and entity-expansion ("billion laughs"). Prefer defusedxml when the EE has it;
# otherwise fall back to stdlib + an explicit DTD/DOCTYPE rejection (OpenSCAP
# output never carries a DOCTYPE, and entity-expansion attacks require one).
try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring  # type: ignore
    _DEFUSED = True
except ImportError:  # pragma: no cover - depends on EE contents
    _xml_fromstring = ET.fromstring
    _DEFUSED = False

_DOCTYPE_RE = re.compile(r"<!DOCTYPE", re.IGNORECASE)

# Result strings that count as a violation vs. a pass vs. neither.
_FAIL = {"fail", "error"}
_PASS = {"pass", "fixed"}
# Everything else (notapplicable, notchecked, notselected, informational,
# unknown) is neutral and excluded from both — see module docstring.


def _local(tag: str) -> str:
    """Strip the XML namespace: '{ns}rule-result' -> 'rule-result'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(elem) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def parse_xccdf_results(xml_text: str) -> dict:
    """Parse XCCDF result XML into AAC's compliance-result shape.

    Returns a dict with: total_evaluated, passed, failed, by_status,
    compliance_pct, score, benchmark_id, profile, test_result_id,
    rule_results[], failed_rules[]. Raises ValueError on unparseable XML.
    """
    # Reject DTDs outright (defense-in-depth against entity-expansion / XXE).
    if _DOCTYPE_RE.search(xml_text):
        raise ValueError("refusing to parse XML containing a DOCTYPE/DTD")
    try:
        root = _xml_fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from exc

    # Title lookup: Benchmark <Rule id="..."><title>…</title>. Present when the
    # results file carries the full benchmark (oscap --results does). Absent for
    # a bare TestResult — then we fall back to the rule id.
    titles: dict[str, str] = {}
    benchmark_id = ""
    for elem in root.iter():
        lt = _local(elem.tag)
        if lt == "Benchmark" and not benchmark_id:
            benchmark_id = elem.get("id", "")
        elif lt == "Rule":
            rid = elem.get("id", "")
            if not rid:
                continue
            for child in elem:
                if _local(child.tag) == "title":
                    titles[rid] = _text(child)
                    break

    # Find the TestResult (there may be more than one; take the last, which is
    # the most recent run for oscap output).
    test_result = None
    for elem in root.iter():
        if _local(elem.tag) == "TestResult":
            test_result = elem
    if test_result is None:
        raise ValueError("no <TestResult> found — not an oscap results file?")

    profile = ""
    score = None
    test_result_id = test_result.get("id", "")
    for child in test_result:
        lt = _local(child.tag)
        if lt == "profile":
            profile = child.get("idref", "")
        elif lt == "score" and score is None:
            try:
                score = round(float(_text(child)), 2)
            except (TypeError, ValueError):
                score = None

    rule_results: list[dict] = []
    by_status: dict[str, int] = {}
    for rr in test_result.iter():
        if _local(rr.tag) != "rule-result":
            continue
        idref = rr.get("idref", "")
        severity = rr.get("severity", "") or "unknown"
        result = ""
        idents: list[dict] = []
        for child in rr:
            lt = _local(child.tag)
            if lt == "result":
                result = _text(child).lower()
            elif lt == "ident":
                idents.append({"system": child.get("system", ""), "value": _text(child)})
        by_status[result] = by_status.get(result, 0) + 1
        rule_results.append({
            "rule_id": idref,
            "title": titles.get(idref, idref),
            "result": result,
            "severity": severity.lower(),
            "idents": idents,   # CCE/CCI captured for a future control crosswalk
        })

    passed = sum(1 for r in rule_results if r["result"] in _PASS)
    failed_rules = [r for r in rule_results if r["result"] in _FAIL]
    failed = len(failed_rules)
    total_evaluated = passed + failed   # neutral statuses excluded by design
    compliance_pct = round(passed / total_evaluated * 100, 2) if total_evaluated else 0.0

    return {
        "benchmark_id": benchmark_id,
        "profile": profile,
        "test_result_id": test_result_id,
        "score": score,                 # oscap's own default-model score (0-100) if present
        "total_evaluated": total_evaluated,
        "passed": passed,
        "failed": failed,
        "compliance_pct": compliance_pct,
        "compliant": failed == 0,
        "by_status": by_status,         # raw counts incl. notapplicable/notchecked/etc.
        "rule_results": rule_results,
        "failed_rules": failed_rules,   # what goes into the violations column
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: openscap_xccdf_parse.py <xccdf-results.xml>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        parsed = parse_xccdf_results(fh.read())
    json.dump(parsed, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
