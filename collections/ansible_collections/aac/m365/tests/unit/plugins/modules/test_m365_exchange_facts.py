"""Unit tests for m365_exchange_facts.

Mocks GraphClient. Pins:

  - Initial .onmicrosoft.com domains are excluded from customer
    DNS-hygiene checks (CIS 4.5/4.6/4.7 apply to customer-owned
    domains).
  - DNS records are classified correctly: TXT v=spf1 → SPF;
    TXT v=DMARC1 at label `_dmarc` → DMARC; CNAME at
    `selectorN._domainkey` → DKIM.
  - Mailbox audit aggregate: distinguishes evaluable
    (mailboxAuditEnabled key present) from non-evaluable.
  - Per-user mailbox 4xx falls back to skipping the user, not
    failing the assessment (some users have no Exchange license).
  - Secure Score control rows are projected to just the relevant
    set.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
COLLECTIONS_PATH = REPO_ROOT / "collections"
if str(COLLECTIONS_PATH) not in sys.path:
    sys.path.insert(0, str(COLLECTIONS_PATH))


from ansible_collections.aac.m365.plugins.modules import m365_exchange_facts


class FakeGraphClient:
    """Stub matching the identity-facts test pattern."""

    def __init__(self, responses: dict, raises: set | None = None):
        self.responses = responses
        self.raises = raises or set()

    def _resolve(self, path: str):
        if path in self.raises:
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(403, "synthetic forbidden", path)
        if path not in self.responses:
            raise AssertionError(f"unexpected call: {path}")
        return self.responses[path]

    def get(self, path: str, params=None):
        if (
            path.startswith("/security/secureScoreControlProfiles/")
            and path not in self.responses
            and path not in self.raises
        ):
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(404, "not found", path)
        return self._resolve(path)

    def get_all(self, path: str, params=None):
        return self._resolve(path)


# Minimal response set — every test extends this with whatever the
# specific scenario needs.
def _baseline(domain_rows, domain_dns, user_rows, user_mailbox):
    responses = {
        "/domains": domain_rows,
        # /users is fetched with a single-page `get` (not get_all), so it
        # returns the real Graph page shape: {"value": [...]}.
        "/users": {"value": user_rows},
        "/organization": {"value": [{"displayName": "Acme", "tenantType": "AAD"}]},
    }
    for d_id, records in domain_dns.items():
        responses[f"/domains/{d_id}/serviceConfigurationRecords"] = records
    for uid, settings in user_mailbox.items():
        responses[f"/users/{uid}/mailboxSettings"] = settings
    return responses


# ── DNS classification ──────────────────────────────────────────────


def test_initial_domain_is_excluded_from_customer_set():
    """The default acme.onmicrosoft.com is is_initial=true; CIS DNS
    checks don't apply to it (Microsoft auto-publishes SPF for them)."""
    responses = _baseline(
        domain_rows=[
            {"id": "acme.onmicrosoft.com", "isVerified": True, "isInitial": True, "isDefault": True},
            {"id": "acme.com", "isVerified": True, "isInitial": False},
        ],
        domain_dns={
            "acme.onmicrosoft.com": [],
            "acme.com": [
                {"recordType": "TXT", "label": "@", "text": "v=spf1 -all"},
            ],
        },
        user_rows=[],
        user_mailbox={},
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    domain_ids = [d["id"] for d in facts["verified_domains"]]
    assert "acme.com" in domain_ids
    # The initial domain IS in the verified_domains list (we report
    # what we saw), but the Rego skips it via is_initial. The unit
    # test just confirms the flag is preserved.
    initial = next(d for d in facts["verified_domains"] if d["id"] == "acme.onmicrosoft.com")
    assert initial["is_initial"] is True


def test_spf_dmarc_dkim_classification():
    responses = _baseline(
        domain_rows=[
            {"id": "acme.com", "isVerified": True, "isInitial": False},
        ],
        domain_dns={
            "acme.com": [
                {"recordType": "TXT", "label": "@", "text": "v=spf1 include:spf.protection.outlook.com -all"},
                {"recordType": "TXT", "label": "_dmarc", "text": "v=DMARC1; p=reject; rua=mailto:dmarc@acme.com"},
                {"recordType": "CNAME", "label": "selector1._domainkey", "text": "selector1-acme-com._domainkey.acme.onmicrosoft.com"},
            ],
        },
        user_rows=[],
        user_mailbox={},
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    d = facts["verified_domains"][0]
    assert d["spf_present"] is True
    assert d["dmarc_present"] is True
    assert d["dkim_present"] is True


def test_dns_classification_handles_missing_records():
    responses = _baseline(
        domain_rows=[
            {"id": "acme.com", "isVerified": True, "isInitial": False},
        ],
        domain_dns={"acme.com": []},
        user_rows=[],
        user_mailbox={},
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    d = facts["verified_domains"][0]
    assert d["spf_present"] is False
    assert d["dmarc_present"] is False
    assert d["dkim_present"] is False


def test_dns_query_error_marks_custom_domain_unavailable_not_false():
    # M2: a custom domain whose serviceConfigurationRecords request errors
    # (e.g. 403) must be reported as dns_unavailable -- NOT spf/dkim/dmarc=false,
    # which defender_validation.rego would read as a definite violation.
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={},
        user_rows=[],
        user_mailbox={},
    )
    raises = {"/domains/acme.com/serviceConfigurationRecords"}
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses, raises))
    d = facts["verified_domains"][0]
    assert "dns_unavailable" in d
    assert "permission denied" in d["dns_unavailable"]     # sanitized 403 reason
    assert "synthetic forbidden" not in d["dns_unavailable"]  # raw body not leaked
    assert "spf_present" not in d
    assert "dkim_present" not in d
    assert "dmarc_present" not in d


def test_dns_query_error_on_initial_domain_preserves_is_initial():
    # The Microsoft-managed initial domain is excluded from the DNS controls
    # policy-side (defender skips is_initial); on error the collector still
    # marks it dns_unavailable and preserves the flag so the policy can exclude it.
    responses = _baseline(
        domain_rows=[
            {"id": "acme.onmicrosoft.com", "isVerified": True, "isInitial": True, "isDefault": True},
        ],
        domain_dns={},
        user_rows=[],
        user_mailbox={},
    )
    raises = {"/domains/acme.onmicrosoft.com/serviceConfigurationRecords"}
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses, raises))
    d = facts["verified_domains"][0]
    assert d["is_initial"] is True
    assert "dns_unavailable" in d
    assert "spf_present" not in d


# ── Mailbox audit aggregate ─────────────────────────────────────────


def test_mailbox_audit_summary_counts_enabled_and_disabled():
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
            {"id": "u-2", "userPrincipalName": "bob@example.com"},
            {"id": "u-3", "userPrincipalName": "carol@example.com"},
        ],
        user_mailbox={
            "u-1": {"mailboxAuditEnabled": True},
            "u-2": {"mailboxAuditEnabled": False},
            "u-3": {"mailboxAuditEnabled": True},
        },
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    s = facts["mailbox_audit_summary"]
    assert s["audit_enabled"] == 2
    assert s["audit_disabled"] == 1
    assert s["sampled"] == 3
    assert s["evaluable"] is True


def test_mailbox_audit_evaluable_false_when_no_key_present():
    """If the mailboxAuditEnabled key isn't surfaced by Graph for
    any user, mark the result not-evaluable so Rego can emit the
    right message."""
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
        ],
        user_mailbox={
            "u-1": {"archiveFolder": "Archive"},     # no audit key
        },
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    s = facts["mailbox_audit_summary"]
    assert s["evaluable"] is False
    assert s["sampled"] == 1


def test_user_without_exchange_license_is_skipped():
    """A user whose mailboxSettings returns 403/404 just gets
    skipped — the assessment continues for everyone else."""
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
            {"id": "u-2", "userPrincipalName": "bob@example.com"},
        ],
        user_mailbox={
            "u-1": {"mailboxAuditEnabled": True},
            # u-2 has no mailboxSettings entry — Graph 403
        },
    )
    raises = {"/users/u-2/mailboxSettings"}
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses, raises=raises))
    assert facts["mailbox_audit_summary"]["sampled"] == 1
    assert facts["mailbox_audit_summary"]["audit_enabled"] == 1


# ── Secure Score projection ─────────────────────────────────────────


def test_secure_score_projects_only_relevant_controls():
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[],
        user_mailbox={},
    )
    for row in (
        {"id": "MFARegistrationV2", "title": "MFA reg", "implementationStatus": "Implemented"},
        {"id": "SMTPAuthDisabled", "title": "SMTP AUTH disabled", "implementationStatus": "Implemented"},
        {"id": "ExternalSenderTagging", "title": "Ext tag", "implementationStatus": "NotImplemented"},
        {"id": "SomethingUnrelated", "title": "noise", "implementationStatus": "Implemented"},
    ):
        responses[f"/security/secureScoreControlProfiles/{row['id']}"] = row
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    ids = {c["id"] for c in facts["secure_score_controls"]}
    assert ids == {"MFARegistrationV2", "SMTPAuthDisabled", "ExternalSenderTagging"}
    assert "SomethingUnrelated" not in ids
