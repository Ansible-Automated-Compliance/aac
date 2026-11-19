# -*- coding: utf-8 -*-
"""Per-section control counts for persisting a CIS M365 v7 report.

A control that was not evaluated is never a pass. The stored
passed / failed counts therefore come from what the policy reports as
evaluated, never from "declared controls minus the ids named in a
violation": every fail-closed message ("could not be evaluated ... this
is not a pass") names ONE control id even when the gap blocks several, so
the old arithmetic stored the others as passed -- 129 "passed" controls
for a tenant where nothing was collected.

Two sources, in order of preference:

1. ``control_results`` -- one object per control with a ``status`` of
   pass | fail | evidence_missing | not_attested | not_applicable. Read
   from the section report (``sections_evaluated[].control_results``) or
   from the top-level report. The id key may be ``control_id`` or ``id``;
   the section is taken from a ``section`` field when present, otherwise
   from the control id's first component.

2. Fallback, when the report carries no ``control_results``:
   - a message containing a fail-closed marker ("this is not a pass",
     "could not be evaluated", "not collected", "evidence missing") marks
     every control id it names as NOT EVALUATED;
   - any other message marks the control id(s) in its ``CIS x.y.z:``
     prefix as FAILED (failed wins over not evaluated);
   - the remaining declared controls are PASSED only when the gaps in the
     section are fully enumerated: every fail-closed message lists the
     controls it blocks ("(blocks 2.1.2, 2.1.3, 2.1.11)" or a
     "CIS 2.1.8/2.1.9/2.1.10:" prefix), and the section reports no
     unavailable fact without a matching message. Otherwise which of them
     were really evaluated cannot be told from the report, and they are
     stored as not evaluated (count_basis "fallback_conservative").
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

DOCUMENTATION = r"""
name: m365_result_counts
short_description: Count passed, failed and not-evaluated CIS M365 v7 controls per section
description:
  - Takes the C(cis_m365_v7.main.compliance_report) document and returns
    per-section and attestation-ledger counts in which a control that was
    not evaluated is never counted as passed.
  - Prefers a per-control C(control_results) list when the report carries
    one and falls back to the violation messages otherwise.
options:
  _input:
    description: The compliance report.
    type: dict
    required: true
  sections:
    description: The section reports to count (after waivers). Defaults to the report's C(sections_evaluated).
    type: list
    elements: dict
  attestations:
    description: The attestations supplied as policy input, used to read C(observed).
    type: list
    elements: dict
"""

PASS, FAIL, MISSING, NOT_ATTESTED, NOT_APPLICABLE = (
    "pass", "fail", "evidence_missing", "not_attested", "not_applicable")
STATUSES = (PASS, FAIL, MISSING, NOT_ATTESTED, NOT_APPLICABLE)

FAIL_CLOSED_MARKERS = (
    "this is not a pass",
    "could not be evaluated",
    "not collected",
    "evidence missing",
    "not yet evaluated",
)

_ID = re.compile(r"(?<![\d.])\d+(?:\.\d+){1,4}(?![\d.])")
_PREFIX = re.compile(r"^\s*CIS\s+([0-9][0-9./]*)\s*:")
_BLOCKS = re.compile(r"\(blocks ([^)]*)\)")


def _ids_in(text):
    return set(_ID.findall(text or ""))


def _prefix_ids(text):
    m = _PREFIX.match(text or "")
    return set(_ID.findall(m.group(1))) if m else set()


def _is_fail_closed(text):
    low = (text or "").lower()
    return any(marker in low for marker in FAIL_CLOSED_MARKERS)


def _enumerated(text):
    """True when a fail-closed message names every control it blocks."""
    if _BLOCKS.search(text or ""):
        return True
    return len(_prefix_ids(text)) > 1


def _result_id(row):
    return str(row.get("control_id") or row.get("id") or "")


def _control_results(report, section):
    rows = section.get("control_results")
    if isinstance(rows, list):
        return rows
    rows = report.get("control_results")
    if not isinstance(rows, list):
        return None
    sid = str(section.get("section"))
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rsec = row.get("section")
        if rsec is not None:
            if str(rsec) == sid:
                out.append(row)
        elif _result_id(row).split(".")[0] == sid:
            out.append(row)
    return out


def _finish(section, passed, failed, not_eval, not_app, basis, waived=()):
    declared = [str(c) for c in section.get("controls") or []]
    denominator = len(declared) - len(not_app)
    pct = round(len(passed) * 100.0 / denominator, 1) if denominator > 0 else 0
    return {
        "section": str(section.get("section")),
        "total": int(section.get("section_total_controls") or len(declared)),
        "declared_evaluated": len(declared),
        "passed": len(passed),
        "failed": len(failed),
        "not_evaluated": len(not_eval),
        "not_applicable": len(not_app),
        "waived": len(waived),
        "compliance_percentage": pct,
        "passed_control_ids": sorted(passed),
        "failed_control_ids": sorted(failed),
        "not_evaluated_control_ids": sorted(not_eval),
        "not_applicable_control_ids": sorted(not_app),
        "waived_control_ids": sorted(waived),
        "count_basis": basis,
    }


def _from_control_results(section, rows):
    active = section.get("violations") or []
    by_status = {s: set() for s in STATUSES}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        cid = _result_id(row)
        if not cid:
            continue
        # An unknown status is not evidence of a pass.
        by_status[status if status in by_status else MISSING].add(cid)
    failed = by_status[FAIL]
    waived = set()
    if section.get("waivers_applied"):
        # A failed control none of whose findings survive the waiver step
        # is waived -- stored as such, never as passed.
        still = set()
        for msg in active:
            still |= _prefix_ids(msg)
        waived = {c for c in failed if c not in still}
        failed = failed - waived
    declared = {str(c) for c in section.get("controls") or []}
    reported = set().union(*by_status.values())
    # A declared control the list does not mention was not evaluated.
    not_eval = (by_status[MISSING] | by_status[NOT_ATTESTED] | (declared - reported)) - failed - waived
    passed = by_status[PASS] - failed - not_eval - waived
    return _finish(section, passed, failed, not_eval, by_status[NOT_APPLICABLE],
                   "control_results", waived)


def _from_messages(section):
    declared = [str(c) for c in section.get("controls") or []]
    declared_set = set(declared)
    failed, not_eval = set(), set()
    exact = True
    for msg in section.get("violations") or []:
        if _is_fail_closed(msg):
            not_eval |= (_ids_in(msg) & declared_set)
            if not _enumerated(msg):
                exact = False
        else:
            failed |= (_prefix_ids(msg) & declared_set)
    if section.get("facts_present") is False:
        exact = False
    unavailable = section.get("unavailable_facts") or {}
    if unavailable and not not_eval:
        # The section says facts were missing but no message names what
        # they block: nothing in it can be counted as evaluated.
        exact = False
    not_eval -= failed
    if exact:
        passed = declared_set - failed - not_eval
        basis = "fallback_exact"
    else:
        not_eval = declared_set - failed
        passed = set()
        basis = "fallback_conservative"
    return _finish(section, passed, failed, not_eval, set(), basis)


def section_counts(report, section):
    rows = _control_results(report, section)
    if rows is not None:
        return _from_control_results(section, rows)
    return _from_messages(section)


def _truthy_observed(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "pass", "passed", "compliant", "yes")
    return False


def ledger_counts(report, attestations=None):
    ledger = report.get("no_collector_path") or {}
    ids = set()
    for key in ("requires_attestation", "unresolved", "not_implemented"):
        ids |= {str(k) for k in (ledger.get(key) or {})}
    rows = report.get("control_results")
    passed, failed, not_attested, not_app = set(), set(), set(), set()
    if isinstance(rows, list):
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or _result_id(row) not in ids:
                continue
            cid, status = _result_id(row), str(row.get("status") or "").lower()
            seen.add(cid)
            {PASS: passed, FAIL: failed, NOT_APPLICABLE: not_app}.get(status, not_attested).add(cid)
        not_attested |= ids - seen
        basis = "control_results"
    else:
        attested = {str(c) for c in ledger.get("attested_control_ids") or []} & ids
        observed = {}
        for a in attestations or []:
            if isinstance(a, dict) and a.get("control_id") is not None:
                observed[str(a["control_id"])] = _truthy_observed(a.get("observed"))
        for cid in ids:
            if cid not in attested:
                not_attested.add(cid)
            elif observed.get(cid):
                passed.add(cid)
            else:
                # Attested, but not as observed-compliant: an attestation
                # that says the control is not met is a failure.
                failed.add(cid)
        basis = "fallback"
    return {
        "total": len(ids),
        "passed": len(passed),
        "failed": len(failed),
        "not_attested": len(not_attested),
        "not_applicable": len(not_app),
        "passed_control_ids": sorted(passed),
        "failed_control_ids": sorted(failed),
        "not_attested_control_ids": sorted(not_attested),
        "count_basis": basis,
    }


def m365_result_counts(report, sections=None, attestations=None):
    report = report or {}
    if sections is None:
        sections = report.get("sections_evaluated") or []
    out = {}
    for sec in sections:
        if isinstance(sec, dict):
            out[str(sec.get("section"))] = section_counts(report, sec)
    return {"sections": out, "ledger": ledger_counts(report, attestations)}


class FilterModule(object):
    def filters(self):
        return {"m365_result_counts": m365_result_counts}
