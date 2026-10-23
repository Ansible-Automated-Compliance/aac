#!/usr/bin/env python3
"""
Compute the deterministic fields of a Certifiable Audit Artifact (CAA).

Reads a JSON object from stdin with these keys:
    framework, framework_version, scope, scope_value,
    evaluator_aap_job_id, policy_library_sha,
    result, input, violations, compliance_status

Writes a JSON object to stdout with:
    certification_id, period_start, period_end,
    input_hash, signed_at, severity_summary, projection

`projection` is the canonical JSON of the CAA payload that gets signed.
The Ansible caller pipes this into `cosign sign-blob` to produce the real
signature; the helper no longer computes signature bytes itself.

Historical: the pre-2026-07-02 helper emitted `signature_hex` as a
sha256 of `projection` — tamper-evident under sha256 but not a
cryptographic signature. Item 4 (cosign signing) replaces that
placeholder with a real ECDSA-P256 signature via cosign.
"""

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


_SEV_KEYWORDS = ("critical", "high", "medium", "low")
# Match a severity keyword as a whole word (regex \b). Anchoring on word
# boundaries avoids false positives like "lowercase" → low or "5.2.15" → low.
_SEV_PATTERN = re.compile(
    r"\b(" + "|".join(_SEV_KEYWORDS) + r")\b", re.IGNORECASE
)


def _extract_severity(v):
    """Best-effort severity extraction. Returns one of the keys in
    _SEV_KEYWORDS or None."""
    if isinstance(v, dict):
        sev = (v.get("severity") or v.get("risk_level") or "").lower().strip()
        if sev in _SEV_KEYWORDS:
            return sev
        return None
    if isinstance(v, str):
        # Some frameworks embed a severity keyword in the message; extract it
        # if present. Take the first match — a violation with multiple severity
        # words is a policy-authoring problem, not a scoring one.
        m = _SEV_PATTERN.search(v)
        if m:
            return m.group(1).lower()
    return None


def severity_summary(result, violations):
    # "unclassified" holds violations we couldn't map to a severity — e.g.
    # CIS RHEL 9's OPA library returns violations as plain strings without a
    # severity field. Counting them under a dedicated bucket keeps the CAA
    # honest instead of silently reporting {critical:0, high:0, medium:0, low:0}
    # for a non_compliant row.
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unclassified": 0}
    items = []
    if isinstance(result, dict) and isinstance(result.get("violations"), list):
        items = result["violations"]
    elif isinstance(violations, list):
        items = violations

    for v in items:
        sev = _extract_severity(v)
        if sev in summary:
            summary[sev] += 1
        else:
            summary["unclassified"] += 1
    return summary


def main():
    payload = json.load(sys.stdin)

    cert_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    input_hash = hashlib.sha256(canonical(payload["input"]).encode()).hexdigest()

    projection = {
        "certification_id":     cert_id,
        "framework":            payload["framework"],
        "framework_version":    payload.get("framework_version", ""),
        "scope":                payload["scope"],
        "scope_value":          payload["scope_value"],
        "period_start":         now,
        "period_end":           now,
        "evaluator_aap_job_id": int(payload.get("evaluator_aap_job_id") or 0),
        "policy_library_sha":   payload["policy_library_sha"],
        "input_hash":           input_hash,
        "result":               payload["result"],
        "compliance_status":    payload["compliance_status"],
    }

    json.dump({
        "certification_id":  cert_id,
        "period_start":      now,
        "period_end":        now,
        "input_hash":        input_hash,
        "signed_at":         now,
        "severity_summary":  severity_summary(payload["result"], payload.get("violations", [])),
        # The canonical projection that cosign will sign. Emitted as a JSON
        # string (already canonicalized — sorted keys, no whitespace) so the
        # signer signs the exact same bytes the verifier will hash.
        "projection":        canonical(projection),
    }, sys.stdout)


if __name__ == "__main__":
    main()
