#!/usr/bin/env python3
"""Normalize stored compliance_results violations into first-class findings.

A violation as stored is a message inside an assessment row: re-emitted every
run, no identity, no state. A *finding* has identity — (framework, control_id,
subject) — which is what makes blast-radius questions ("which systems fail
control X?") and target lists ("which systems need this fix?") answerable, and
what lets mitigation be tracked and verified by rescan instead of asserted.

This is the deterministic, testable core: rows in → normalized findings out.
No database I/O here (the aac_findings_sync role owns that), mirroring the
scripts/openscap_xccdf_parse.py pattern.

Input (stdin): JSON array of compliance_results rows, each at least
  {"id", "hostname", "framework", "violations", "metadata",
   "evaluation_timestamp"}
Output (stdout): JSON array of findings, each
  {"subject", "framework", "control_id", "finding_type", "severity",
   "title", "refs", "result_id", "observed_at"}

Control-id extraction handles the message families this library actually
emits; anything unrecognized falls back to the message's leading clause so a
finding still gets a *stable* (if uglier) identity rather than being dropped.
Fail-closed sentinels become finding_type="evidence_gap" — an area with no
facts collected is a different actionable than an assessed control failure.
"""
from __future__ import annotations

import json
import re
import sys

# Ordered: first match wins. Each pattern's group(1) is the control id.
_PATTERNS = [
    # CIS M365 5.1.2.2 / CIS L2 M365 ...
    re.compile(r"^(CIS (?:L2 )?M365 \d+(?:\.\d+)*)"),
    # CIS 1.1.1 / CIS L2 3.3.3
    re.compile(r"^(CIS (?:L2 )?\d+(?:\.\d+)*)"),
    # Attestation families: "IRS 1075 [Area] RK-1:", "BSI C5 [Name] OIS-2:",
    # "CJIS [Media Protection] MP-1:", "Cyber Essentials [Firewalls] FW-4:"
    re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .]{0,40}\[[^\]]+\] ([A-Z]{2,4}-\d+):"),
    # DISA STIG rule ids
    re.compile(r"\b((?:RHEL|UBTU|WN\d\d|SLES|AMZN)-[0-9A-Z]{2,4}-\d{6})\b"),
    re.compile(r"\b(V-\d{5,6})\b"),
    # NERC-CIP: CIP-010 R1 / CIP-010-4
    re.compile(r"\b(CIP-\d{3}(?:-\d+)?(?:\s+R\d+(?:\.\d+)*)?)"),
    # NIST-style family ids, optionally prefixed: "NIST SC-28", "AC-6(2)"
    re.compile(r"^(?:NIST )?([A-Z]{2}-\d+(?:\(\d+\))?)[:\s]"),
    # ISO 27001 style: "A.5.1", "ISO 27001 A.8.16"
    re.compile(r"\b(A\.\d+(?:\.\d+)+)\b"),
]

_FAIL_CLOSED = re.compile(r"^FAIL-CLOSED\b[:\s]*", re.IGNORECASE)


def _control_from_message(msg: str) -> tuple[str, str]:
    """Return (control_id, finding_type) for a string violation message."""
    text = msg.strip()
    if _FAIL_CLOSED.match(text):
        # Identity for an evidence gap = the area named after the sentinel,
        # so the same gap on the same subject stays ONE finding across runs.
        rest = _FAIL_CLOSED.sub("", text)
        area = re.split(r"[—:]| - ", rest, maxsplit=1)[0].strip() or "unspecified"
        return f"EVIDENCE-GAP:{area[:80]}", "evidence_gap"
    for pat in _PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip(), "violation"
    # Fallback: the leading clause before the first colon/em-dash. Stable for
    # a given message family even when we can't parse a formal id.
    lead = re.split(r"[:—]", text, maxsplit=1)[0].strip()
    return (lead[:100] or text[:100]), "violation"


def _finding_from_dict(v: dict) -> tuple[str, str, str | None, str, dict]:
    """(control_id, finding_type, severity, title, refs) for dict violations
    (the OpenSCAP ingest shape and any future structured emitters)."""
    refs = {}
    for key in ("cce", "cci", "nist_800_53", "rule_id", "xccdf_id"):
        if v.get(key):
            refs[key] = v[key]
    for ident in v.get("idents") or []:
        system = str(ident.get("system", "")).lower()
        value = ident.get("value")
        if value and "cce" in system:
            refs.setdefault("cce", value)
        elif value and "cci" in system:
            cci = refs.setdefault("cci", [])
            if not isinstance(cci, list):
                cci = refs["cci"] = [cci]
            if value not in cci:
                cci.append(value)
    control = (
        v.get("rule_id")
        or v.get("rule")          # older ingest rows use bare "rule"
        or v.get("control_id")
        or v.get("control")
        or refs.get("cce")
        or v.get("title")
        or "unknown"
    )
    title = v.get("title") or v.get("rule_id") or json.dumps(v)[:200]
    severity = v.get("severity") or None
    ftype = "evidence_gap" if str(v.get("result", "")).lower() == "notchecked" else "violation"
    return str(control)[:120], ftype, severity, title, refs


def _invalid_subject(subject: str) -> bool:
    """Execution-context names are not assets (mirrors aac_store_results'
    provenance rule): an EE pod or localhost as subject would fabricate
    blast radius — 27 'systems' that are really 27 job runs."""
    s = subject.lower()
    return s in ("localhost", "127.0.0.1") or s.startswith("automation-job-")


def _collect(rows: list[dict], source: str) -> list[dict]:
    """Normalize one violation source ('violations' column, or the
    waived messages in metadata.waivers_applied) into keyed findings."""
    findings: dict[tuple, dict] = {}
    for row in rows:
        subject = (row.get("hostname") or "").strip()
        framework = (row.get("framework") or "").strip()
        if not subject or not framework or _invalid_subject(subject):
            # An unattributable violation cannot be a target; skip rather than
            # invent identity (evidence-quality doctrine: no fake subjects).
            continue
        observed = row.get("evaluation_timestamp") or ""
        if source == "violations":
            items = row.get("violations") or []
        else:
            items = (row.get("metadata") or {}).get("waivers_applied") or []
        for v in items:
            if isinstance(v, dict):
                control, ftype, severity, title, refs = _finding_from_dict(v)
            else:
                control, ftype = _control_from_message(str(v))
                severity, title, refs = None, str(v)[:500], {}
            key = (framework, control, subject, ftype)
            f = findings.get(key)
            if f is None or observed > f["observed_at"]:
                findings[key] = {
                    "subject": subject,
                    "framework": framework,
                    "control_id": control,
                    "finding_type": ftype,
                    "severity": severity,
                    "title": title,
                    "refs": refs,
                    "result_id": row.get("id"),
                    "observed_at": observed,
                }
    return sorted(
        findings.values(),
        key=lambda f: (f["framework"], f["subject"], f["control_id"]),
    )


def extract(rows: list[dict]) -> dict:
    """rows → {"findings": [...], "waived": [...], "scanned": [...]}.

    `scanned` lists every (framework, subject) pair with the timestamp of the
    assessment that observed it — the resolution step may only close findings
    for pairs a NEWER scan actually covered (verified by rescan, never by
    absence of data).
    """
    scanned = []
    seen = set()
    for row in rows:
        subject = (row.get("hostname") or "").strip()
        framework = (row.get("framework") or "").strip()
        if not subject or not framework or _invalid_subject(subject) \
                or (framework, subject) in seen:
            continue
        seen.add((framework, subject))
        scanned.append({
            "framework": framework,
            "subject": subject,
            "ts": row.get("evaluation_timestamp") or "",
        })
    return {
        "findings": _collect(rows, "violations"),
        "waived": _collect(rows, "waivers"),
        "scanned": sorted(scanned, key=lambda s: (s["framework"], s["subject"])),
    }


if __name__ == "__main__":
    json.dump(extract(json.load(sys.stdin)), sys.stdout, indent=2, default=str)
    print()
